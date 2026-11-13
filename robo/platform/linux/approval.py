"""GTK dialogs that ask you before a task gets anything (an Approver).

Closing a dialog, or pressing Escape, counts as "no".
"""
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk  # noqa: E402

from robo.sandbox import Approver  # noqa: E402


def _ask(heading, title, lines, yes_label, on_answer):
    dialog = Gtk.MessageDialog(message_type=Gtk.MessageType.QUESTION,
                               buttons=Gtk.ButtonsType.NONE, text=heading)
    dialog.set_title('Robo')
    dialog.set_keep_above(True)
    dialog.format_secondary_text(f'Task: {title}\n\n' + '\n'.join('• ' + l for l in lines))
    dialog.add_button('No', Gtk.ResponseType.REJECT)
    dialog.add_button(yes_label, Gtk.ResponseType.ACCEPT)
    dialog.set_default_response(Gtk.ResponseType.REJECT)     # Enter = the safe answer

    answered = []

    def respond(d, response):
        if not answered:
            answered.append(True)
            d.destroy()
            on_answer(response == Gtk.ResponseType.ACCEPT)
    dialog.connect('response', respond)
    dialog.show_all()
    dialog.present()


def _path_list(title, select_folders_too):
    """A small list of chosen paths with Add file / Add folder / Remove buttons."""
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    box.pack_start(Gtk.Label(label=title, xalign=0), False, False, 0)
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
    return box, lambda: [row[0] for row in store]


class GtkApprover(Approver):
    def ask_task(self, agent_name, on_answer):
        d = Gtk.Dialog(title='Give Robo a task')
        d.set_keep_above(True)
        d.set_default_size(520, 520)
        d.add_button('Cancel', Gtk.ResponseType.CANCEL)
        d.add_button('Start', Gtk.ResponseType.OK)
        area = d.get_content_area()
        area.set_spacing(8)
        for side in ('top', 'bottom', 'start', 'end'):
            getattr(area, f'set_margin_{side}')(12)
        area.pack_start(Gtk.Label(label='What should he do?', xalign=0), False, False, 0)
        text = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR)
        frame = Gtk.ScrolledWindow(min_content_height=90)
        frame.add(text)
        area.pack_start(frame, True, True, 0)
        read_box, get_read = _path_list('Files / folders he may look at:', True)
        write_box, get_write = _path_list('Files / folders he may change (you review first):', True)
        area.pack_start(read_box, True, True, 0)
        area.pack_start(write_box, True, True, 0)
        note = Gtk.Label(xalign=0)
        note.set_line_wrap(True)
        note.set_markup(f'<small>{agent_name} works only in Robo\'s sandbox: no internet, and '
                        'nothing but what you choose here. What he reads is sent to '
                        f'{agent_name}. New files go to ~/Robo. Nothing of yours changes until '
                        'you approve it at the end.</small>')
        area.pack_start(note, False, False, 0)

        def respond(dialog, response):
            buf = text.get_buffer()
            goal = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False).strip()
            read, write = get_read(), get_write()
            dialog.destroy()
            if response == Gtk.ResponseType.OK and goal:
                on_answer({'goal': goal, 'read': read, 'write': write, 'approved': True})
        d.connect('response', respond)
        d.show_all()
        d.present()
        return True

    def ask_permissions(self, title, lines, on_answer):
        _ask('Robo would like permission for a task', title, lines, 'Allow', on_answer)

    def review_changes(self, title, lines, on_answer):
        _ask('Robo changed some of your files. Apply the changes?', title,
             lines + ['', 'Nothing has been changed yet. "No" throws the changes away.'],
             'Apply changes', on_answer)
