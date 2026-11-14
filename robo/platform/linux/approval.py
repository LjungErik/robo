"""GTK popups that ask you before a task gets anything (an Approver), and show
you what it made when it's done.

Every popup has the same shape, so it's easy to read at a glance:

    ┌──────────────────────────────────────────┐
    │  [Robo + badge]  Big heading             │   banner (lock / magnifier / tick)
    │                  Task: what you asked    │
    ├──────────────────────────────────────────┤
    │  📝 The task         (a card per topic)  │
    │  👀 He may look at   report.pdf  ~/Docs  │
    │  ...                                     │
    │  small print                             │
    │                         [ No ] [ Allow ] │
    └──────────────────────────────────────────┘

Closing a question, or pressing Escape, counts as "no".
"""
import logging
import os
import subprocess

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('Pango', '1.0')
from gi.repository import Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

from robo.render.popup_art import popup_art_surface  # noqa: E402
from robo.sandbox import Approver  # noqa: E402
from robo.sandbox.approval import group_lines  # noqa: E402

log = logging.getLogger(__name__)

ART_SIZE = 104
MAX_LIST_HEIGHT = 420            # how tall the cards are when they scroll
SCROLL_AFTER_ROWS = 12           # more lines than this in the cards: they scroll

CSS = b"""
.robo-popup-banner { padding: 14px 18px 12px 12px; }
.robo-popup-banner.lock   { background-color: alpha(#FFC93C, 0.20); }
.robo-popup-banner.review { background-color: alpha(#4DA8FF, 0.16); }
.robo-popup-banner.done   { background-color: alpha(#43D17A, 0.18); }
.robo-popup-banner.ask    { background-color: alpha(#9B87FF, 0.16); }
.robo-popup-heading { font-size: 15pt; font-weight: bold; }
.robo-popup-card {
    border: 1px solid alpha(@theme_fg_color, 0.14);
    border-radius: 10px;
    padding: 8px 12px 10px 12px;
    background-color: alpha(@theme_fg_color, 0.035);
}
.robo-popup-card-title { font-weight: bold; }
.robo-popup-path-dir { font-size: smaller; }
.robo-popup-small { font-size: smaller; }
"""
_css_installed = False


def _install_css():
    global _css_installed
    if not _css_installed:
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        _css_installed = True


def _style(widget, *classes):
    ctx = widget.get_style_context()
    for c in classes:
        ctx.add_class(c)
    return widget


def _art(badge, size=ART_SIZE):
    surface = popup_art_surface(size, badge)
    return Gdk.pixbuf_get_from_surface(surface, 0, 0, size, size)


def _tilde(path):
    home = os.path.expanduser('~')
    return '~' + path[len(home):] if path == home or path.startswith(home + os.sep) else path


def _label(text='', markup=None, wrap=True, *classes):
    lab = Gtk.Label(xalign=0)
    if markup is not None:
        lab.set_markup(markup)
    else:
        lab.set_text(text)
    if wrap:
        lab.set_line_wrap(True)
        lab.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        lab.set_max_width_chars(60)
    lab.set_selectable(False)
    return _style(lab, *classes)


def open_path(path):
    """Open a file or folder in your usual app. True if it worked."""
    try:
        Gio.AppInfo.launch_default_for_uri(Gio.File.new_for_path(path).get_uri(), None)
        return True
    except GLib.Error as e:
        log.info('Gio could not open %s (%s); trying xdg-open', path, e.message)
    try:
        subprocess.Popen(['xdg-open', path], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
        return True
    except OSError as e:
        log.warning('could not open %s: %s', path, e)
        return False


def _file_icon(path, size=Gtk.IconSize.LARGE_TOOLBAR):
    try:
        if os.path.isdir(path):
            return Gtk.Image.new_from_icon_name('folder', size)
        ctype, _ = Gio.content_type_guess(path, None)
        return Gtk.Image.new_from_gicon(Gio.content_type_get_icon(ctype), size)
    except Exception:
        return Gtk.Image.new_from_icon_name('text-x-generic', size)


def _path_row(path, button=None):
    """   [icon]  name.pdf               [Open]
                  ~/Documents/folder                 """
    row = Gtk.Box(spacing=10)
    row.pack_start(_file_icon(path), False, False, 0)
    text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    if path.startswith('... and '):
        text.pack_start(_label(path, None, True, 'dim-label'), False, False, 0)
    else:
        name = os.path.basename(path.rstrip(os.sep)) or path
        where = _tilde(os.path.dirname(path.rstrip(os.sep)))
        text.pack_start(_label(markup=f'<b>{GLib.markup_escape_text(name)}</b>'),
                        False, False, 0)
        text.pack_start(_label(where, None, True, 'dim-label', 'robo-popup-path-dir'),
                        False, False, 0)
        row.set_tooltip_text(path)
    row.pack_start(text, True, True, 0)
    if button is not None:
        button.set_valign(Gtk.Align.CENTER)
        row.pack_end(button, False, False, 0)
    return row


def _card(heading, emoji='', rows=()):
    card = _style(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6), 'robo-popup-card')
    title = f'{emoji}  {heading}' if emoji else heading
    card.pack_start(_label(title, None, True, 'robo-popup-card-title'), False, False, 0)
    for r in rows:
        card.pack_start(r, False, False, 0)
    return card


def _section_card(section):
    if section.paths:
        rows = [_path_row(p) for p in section.items]
    else:
        rows = [_label(item) for item in section.items]
    return _card(section.heading, section.emoji, rows)


class _Popup:
    """A Robo popup window. Its contents can be swapped (fill()), so the review
    question can turn into the "here are your files" view in the same place."""

    def __init__(self):
        _install_css()
        w = self.win = Gtk.Window(title='Robo')
        w.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        w.set_keep_above(True)
        w.set_position(Gtk.WindowPosition.CENTER)
        w.set_default_size(500, -1)
        w.set_resizable(True)
        w.set_icon_list([_art('', s) for s in (32, 48, 64)])
        w.connect('delete-event', self._on_delete)
        w.connect('key-press-event', self._on_key)
        self.root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        w.add(self.root)
        self.on_close = None             # called when closed without a button
        self.closed = False

    def fill(self, badge, heading, subtitle, cards, small_print='', buttons=(), default=None,
             tone=None, extra=None):
        """buttons: [(label, callback, style)] left to right; style '' / 'suggested' /
        'destructive'. `default` is the label Enter presses."""
        for child in self.root.get_children():
            self.root.remove(child)
        banner = _style(Gtk.Box(spacing=14), 'robo-popup-banner', tone or badge or 'ask')
        banner.pack_start(Gtk.Image.new_from_pixbuf(_art(badge)), False, False, 0)
        words = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, valign=Gtk.Align.CENTER)
        words.pack_start(_label(heading, None, True, 'robo-popup-heading'), False, False, 0)
        if subtitle:
            words.pack_start(_label(subtitle, None, True, 'dim-label'), False, False, 0)
        banner.pack_start(words, True, True, 0)
        self.root.pack_start(banner, False, False, 0)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for side in ('top', 'start', 'end'):
            getattr(body, f'set_margin_{side}')(14)
        body.set_margin_bottom(4)
        for c in cards:
            body.pack_start(c, False, False, 0)
        if extra is not None:
            body.pack_start(extra, True, True, 0)
        rows = sum(len(c.get_children()) - 1 for c in cards)     # not counting titles
        if rows > SCROLL_AFTER_ROWS:             # a long list: let it scroll
            scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,
                                        min_content_height=MAX_LIST_HEIGHT)
            scroll.add(body)
            self.root.pack_start(scroll, True, True, 0)
        else:
            self.root.pack_start(body, True, True, 0)

        foot = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for side in ('top', 'bottom', 'start', 'end'):
            getattr(foot, f'set_margin_{side}')(14)
        if small_print:
            foot.pack_start(_label(small_print, None, True, 'dim-label', 'robo-popup-small'),
                            False, False, 0)
        bar = Gtk.Box(spacing=8)
        right = Gtk.Box(spacing=8)           # the main buttons, on the right in order
        default_button = None
        for i, (label, callback, style) in enumerate(buttons):
            b = Gtk.Button(label=label)
            if style == 'suggested':
                _style(b, 'suggested-action')
            elif style == 'destructive':
                _style(b, 'destructive-action')
            b.connect('clicked', lambda _b, cb=callback: cb())
            if label == default:
                default_button = b
            if i == 0 and len(buttons) > 2:  # e.g. "Open folder", on its own on the left
                bar.pack_start(b, False, False, 0)
            else:
                right.pack_start(b, False, False, 0)
        bar.pack_end(right, False, False, 0)
        foot.pack_start(bar, False, False, 0)
        self.root.pack_start(foot, False, False, 0)
        self.root.show_all()
        if default_button is not None:
            default_button.set_can_default(True)
            self.win.set_default(default_button)
            default_button.grab_focus()

    def show(self):
        self.win.show_all()
        self.win.present()

    def close(self):
        if not self.closed:
            self.closed = True
            self.win.destroy()

    def _on_delete(self, *_):
        cb, self.on_close = self.on_close, None
        self.close()
        if cb:
            cb()
        return True

    def _on_key(self, _w, ev):
        if ev.keyval == Gdk.KEY_Escape:
            return self._on_delete()
        return False


def _ask(popup, badge, heading, title, lines, yes_label, no_label, on_answer,
         small_print='', yes_style='suggested'):
    """A yes / no question. Closing it, Escape and Enter all mean the safe answer."""
    sections, notes = group_lines(lines)
    answered = []

    def answer(ok, keep_open=False):
        if answered:
            return
        answered.append(ok)
        popup.on_close = None
        if not keep_open:
            popup.close()
        on_answer(ok)

    popup.on_close = lambda: answer(False)
    note = '\n'.join(notes + ([small_print] if small_print else []))
    popup.fill(badge, heading, f'Task: {title}', [_section_card(s) for s in sections], note,
               [(no_label, lambda: answer(False), ''),
                (yes_label, lambda: answer(True, keep_open=badge == 'review'), yes_style)],
               default=no_label)
    popup.show()
    return answer


def _path_list(title, select_folders_too):
    """A small list of chosen paths with Add file / Add folder / Remove buttons."""
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    box.pack_start(_label(title, None, True, 'robo-popup-card-title'), False, False, 0)
    store = Gtk.ListStore(str)
    view = Gtk.TreeView(model=store, headers_visible=False)
    view.append_column(Gtk.TreeViewColumn('', Gtk.CellRendererText(), text=0))
    scroll = Gtk.ScrolledWindow(min_content_height=56)
    scroll.add(view)
    box.pack_start(scroll, True, True, 0)
    buttons = Gtk.Box(spacing=6)

    def pick(action):
        chooser = Gtk.FileChooserDialog(title='Choose', action=action)
        chooser.add_buttons('Cancel', Gtk.ResponseType.CANCEL, 'Add', Gtk.ResponseType.OK)
        chooser.set_select_multiple(True)
        if action == Gtk.FileChooserAction.OPEN:
            for name, patterns in (('All files', ['*']),
                                   ('PDF documents', ['*.pdf', '*.PDF'])):
                f = Gtk.FileFilter()
                f.set_name(name)
                for pat in patterns:
                    f.add_pattern(pat)
                chooser.add_filter(f)
        if chooser.run() == Gtk.ResponseType.OK:
            for f in chooser.get_filenames():
                if f not in [row[0] for row in store]:
                    store.append([f])
        chooser.destroy()

    for label, action in (('Add file…', Gtk.FileChooserAction.OPEN),
                          ('Add folder…', Gtk.FileChooserAction.SELECT_FOLDER)):
        b = Gtk.Button(label=label)
        b.connect('clicked', lambda _b, a=action: pick(a))
        buttons.pack_start(b, False, False, 0)
    remove = Gtk.Button(label='Remove')

    def drop(_b):
        model, it = view.get_selection().get_selected()
        if it is not None:
            model.remove(it)
    remove.connect('clicked', drop)
    buttons.pack_end(remove, False, False, 0)
    box.pack_start(buttons, False, False, 0)
    return _style(box, 'robo-popup-card'), lambda: [row[0] for row in store]


class GtkApprover(Approver):
    def __init__(self):
        self._handoff = None         # a review popup waiting to show the results

    def open_path(self, path):
        return open_path(path)

    def ask_task(self, agent_name, on_answer):
        popup = _Popup()
        popup.win.set_title('Give Robo a task')
        popup.win.set_default_size(540, 600)
        goal_card = _style(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6),
                           'robo-popup-card')
        goal_card.pack_start(_label('📝  What should I do?', None, True, 'robo-popup-card-title'),
                             False, False, 0)
        text = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR)
        for side in ('top', 'bottom', 'left', 'right'):
            getattr(text, f'set_{side}_margin')(6)
        frame = Gtk.ScrolledWindow(min_content_height=90)
        frame.add(text)
        goal_card.pack_start(frame, True, True, 0)
        read_box, get_read = _path_list('👀  Files / folders I may look at (PDFs too):', True)
        write_box, get_write = _path_list('✏️  Files / folders I may change (you check first):',
                                          True)
        extra = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for w in (goal_card, read_box, write_box):
            extra.pack_start(w, True, True, 0)

        def cancel():
            popup.on_close = None
            popup.close()

        def start():
            buf = text.get_buffer()
            goal = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False).strip()
            if not goal:
                text.grab_focus()
                return
            read, write = get_read(), get_write()
            popup.on_close = None
            popup.close()
            on_answer({'goal': goal, 'read': read, 'write': write, 'approved': True})

        popup.on_close = lambda: None
        popup.fill('', 'Give me a task!', f'{agent_name} does the thinking, I do the work.',
                   [], f'I work only in my sandbox: no internet, and nothing but what you choose '
                   f'here. What I read is sent to {agent_name}. New files go to '
                   f'{_tilde(os.path.expanduser("~/Robo"))}, and nothing of yours changes '
                   'until you say so at the end.',
                   [('Cancel', cancel, ''), ('Start', start, 'suggested')], default=None,
                   tone='ask', extra=extra)
        popup.show()
        text.grab_focus()
        return True

    def ask_permissions(self, title, lines, on_answer):
        _ask(_Popup(), 'lock', 'May I have permission?', title, lines, 'Allow', 'No',
             on_answer, small_print='Nothing happens unless you press "Allow".')

    def review_changes(self, title, lines, on_answer):
        sections, _ = group_lines(lines)
        only_new = all(s.heading == 'New files' for s in sections if s.paths)
        popup = _Popup()

        def answered(ok):
            if ok:
                self._handoff = popup        # show_results() may reuse this window
            try:
                on_answer(ok)
            finally:
                if self._handoff is popup:   # nothing to show: just close
                    self._handoff = None
                    popup.close()
        _ask(popup, 'review', "I'm done! Keep what I made?" if only_new else
             "I'm done! Apply my changes?", title, lines,
             'Save files' if only_new else 'Apply changes', 'Throw away', answered,
             small_print='Nothing has been saved or changed yet. "Throw away" deletes my work.')

    def show_results(self, title, summary, files, folder):
        popup, self._handoff = self._handoff, None
        if popup is None or popup.closed:
            popup = _Popup()
        cards = []
        if summary:
            cards.append(_card('What I did', '💬', [_label(' '.join(summary.split()))]))
        rows = []
        for f in files[:30]:
            b = Gtk.Button(label='Open')
            b.connect('clicked', lambda _b, p=f: open_path(p))
            rows.append(_path_row(f, b))
        if len(files) > 30:
            rows.append(_label(f'... and {len(files) - 30} more (in the folder)', None, True,
                               'dim-label'))
        cards.append(_card('Your files' if len(files) != 1 else 'Your file', '📄', rows))

        def close():
            popup.on_close = None
            popup.close()

        def open_main():
            open_path(files[0])
            close()

        def open_folder():
            open_path(folder)
            close()

        popup.on_close = lambda: None
        folder_button = ('📂  Open folder', open_folder, '')
        if len(files) == 1:
            name = os.path.basename(files[0])
            buttons = ([folder_button] if folder else []) + [
                ('Close', close, ''),
                (f'Open {name if len(name) <= 28 else name[:27] + "…"}', open_main, 'suggested')]
        else:
            buttons = [('Close', close, '')] + (
                [(folder_button[0], open_folder, 'suggested')] if folder else [])
        popup.fill('done', 'All done! Here you go', f'Task: {title}', cards,
                   f'Saved in {_tilde(folder)}' if folder else '', buttons,
                   default=buttons[-1][0])
        popup.show()
