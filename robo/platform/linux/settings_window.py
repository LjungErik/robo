"""Robo's settings window (GTK 3), styled like Robo himself.

The form is generated from robo.config.FIELDS, so adding a setting there
adds it here automatically: each field's section is a card, and the cards
are grouped into tabs by robo.config.TABS. Nothing changes until Apply is pressed; Apply
calls on_apply(settings), which saves them and updates the running robot.

The header shows Robo (in the look you picked) in his mechanic outfit
tinkering with himself; he glows while there are unapplied changes and
cheers when you apply them. Characters are listed from their files.
"""
import math
import os
import random
import threading
import time

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_foreign('cairo')
from gi.repository import Gdk, GLib, Gtk  # noqa: E402
import cairo  # noqa: E402

from robo.config import FIELDS, FIELDS_BY_KEY, SECTIONS, TABS, Settings  # noqa: E402
from robo.core import layout  # noqa: E402
from robo.core.bubble import Bubble  # noqa: E402
from robo.core import characters  # noqa: E402
from robo.core.effects import Effects  # noqa: E402
from robo.core.pose import Pose  # noqa: E402
from robo.render.robot import draw_robot  # noqa: E402
from robo.render.scene import draw_frame  # noqa: E402
from robo.render.settings_icon import draw_gear, settings_icon_surface  # noqa: E402
from robo.render.shapes import hexc  # noqa: E402

HEADER_HEIGHT = 150
CHIP_W, CHIP_H = 80, 92
FRAME_MS = 33

CSS = b"""
.robo-settings { background-color: #EEF1F8; }
.robo-settings label { color: #3B4060; }
.robo-settings headerbar {
    background-image: none; background-color: #8EE3CF;
    border: none; border-bottom: 2px solid #3B4060; box-shadow: none;
}
.robo-settings headerbar .title { color: #3B4060; font-weight: 800; }
.robo-settings headerbar .subtitle { color: #3B4060; opacity: 0.75; }
.robo-card {
    background-color: #FFFFFF; border: 2px solid #3B4060; border-radius: 20px;
    padding: 14px 18px 16px 18px;
}
.robo-card-title { font-weight: 800; font-size: 13pt; }
.robo-row-label { font-weight: 700; }
.robo-help { color: #7A80A0; font-size: 9pt; }
.robo-value {
    background-color: #DCE4F0; border-radius: 10px; padding: 2px 10px;
    font-weight: 800; color: #3B4060;
}
.robo-settings scale trough {
    background-image: none; background-color: #DCE4F0; border: none;
    border-radius: 6px; min-height: 10px;
}
.robo-settings scale highlight {
    background-image: none; background-color: #8EE3CF; border: none; border-radius: 6px;
}
.robo-settings scale slider {
    background-image: none; background-color: #FFFFFF; border: 2px solid #3B4060;
    border-radius: 50%; min-width: 20px; min-height: 20px; box-shadow: none;
}
.robo-settings scale slider:hover { background-color: #FFD54F; }
.robo-settings switch {
    background-image: none; background-color: #DCE4F0; border: 2px solid #3B4060;
    border-radius: 16px; color: transparent; font-size: 0;
}
.robo-settings switch:checked { background-color: #8EE3CF; }
.robo-settings switch slider {
    background-image: none; background-color: #FFFFFF; border: 2px solid #3B4060;
    border-radius: 50%; min-width: 22px; min-height: 22px; box-shadow: none;
}
.robo-chip {
    background-image: none; background-color: #F4F7FB; border: 2px solid #C9D1E3;
    border-radius: 16px; padding: 4px 4px 6px 4px; box-shadow: none;
}
.robo-chip:hover { border-color: #3B4060; }
.robo-chip:checked { background-color: #FFF1B8; border-color: #3B4060; }
.robo-chip label { font-weight: 700; font-size: 9pt; }
.robo-actions {
    background-color: #FFFFFF; border-top: 2px solid #3B4060; padding: 10px 16px;
}
.robo-primary, .robo-secondary {
    background-image: none; border: 2px solid #3B4060; border-radius: 16px;
    padding: 6px 16px; box-shadow: none; text-shadow: none;
}
.robo-primary { background-color: #8EE3CF; }
.robo-primary label { font-weight: 800; }
.robo-primary:hover { background-color: #A8F0DE; }
.robo-primary:disabled { background-color: #E3E8F2; border-color: #B7BFD3; }
.robo-primary:disabled label { color: #9AA2B8; }
.robo-secondary { background-color: #FFFFFF; }
.robo-secondary:hover { background-color: #F4F7FB; }
.robo-status { font-weight: 700; }
.robo-tabs {
    background-color: #EEF1F8; border-bottom: 2px solid #3B4060; padding: 8px 12px;
}
.robo-tab {
    background-image: none; background-color: #F4F7FB; border: 2px solid #C9D1E3;
    border-radius: 14px; padding: 4px 6px; box-shadow: none; text-shadow: none;
}
.robo-tab:hover { border-color: #3B4060; }
.robo-tab:checked { background-color: #FFF1B8; border-color: #3B4060; }
.robo-tab-emoji { font-size: 15pt; }
.robo-tab-label { font-weight: 800; font-size: 9pt; }
"""

BG_TOP = hexc('#D9F6EE')
BG_BOTTOM = hexc('#EEF1F8')
GEAR = hexc('#DCE4F0')
GEAR_ACCENT = hexc('#FFD54F')
_css_installed = False


def _install_css():
    global _css_installed
    if _css_installed:
        return
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


def _pass_scroll_to_page(widget, _event):
    """Mouse wheel over a slider scrolls the page instead of changing the value.

    Stopping the emission skips GtkScale's own scroll handler; returning
    False lets the event continue up to the ScrolledWindow."""
    widget.stop_emission_by_name('scroll-event')
    return False


def _gear(cr, cx, cy, r, teeth, angle, color):
    draw_gear(cr, cx, cy, r, teeth, angle, color, hole=BG_BOTTOM)


def _window_icons():
    """Robo's face with a gear, at the sizes window managers like."""
    icons = []
    for size in (16, 24, 32, 48, 64, 128):
        surface = settings_icon_surface(size)
        icons.append(Gdk.pixbuf_get_from_surface(surface, 0, 0, size, size))
    return icons


class _Control:
    """One setting's widgets: how to read it, write it, and its row."""

    def __init__(self, row, get, set_):
        self.row, self.get, self.set = row, get, set_


class SettingsWindow:
    def __init__(self):
        self.win = None
        self.on_apply = None
        self.applied = None
        self.snapshot = None         # form values right after loading (for "dirty")
        self.controls = {}
        self._loading = False
        self._timer = None
        self._hover = None
        self.memory = None
        self._memory_box = None
        self._picking = False
        self._chip_art = []
        self._apply_time = -10.0
        self._status_timer = None
        self.t0 = self._last = time.monotonic()
        self.effects = Effects(random.Random())

    # ------------------------------------------------------------ public
    def open(self, settings, on_apply, memory=None):
        self.on_apply = on_apply
        self.memory = memory
        if self.win is None:
            self._build()
        self._show_memory()
        self.applied = settings
        self._load(settings)
        self.snapshot = self._read()
        self._refresh()
        self.win.show_all()
        self.win.present()
        if self._timer is None:
            self._timer = GLib.timeout_add(FRAME_MS, self._animate)

    # ------------------------------------------------------------ building
    def _build(self):
        _install_css()
        w = self.win = Gtk.Window(title="Robo's Settings")
        w.set_default_size(540, 760)
        w.set_position(Gtk.WindowPosition.CENTER)
        icons = _window_icons()
        w.set_icon_list(icons)
        _style(w, 'robo-settings')
        w.connect('delete-event', self._on_close)

        hb = Gtk.HeaderBar()
        hb.set_show_close_button(True)
        hb.set_title("Robo's Settings")
        hb.set_subtitle('Tune your little robot')
        hb.pack_start(Gtk.Image.new_from_pixbuf(icons[1]))
        w.set_titlebar(hb)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.header = Gtk.DrawingArea()
        self.header.set_size_request(-1, HEADER_HEIGHT)
        self.header.connect('draw', self._draw_header)
        root.pack_start(self.header, False, False, 0)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(150)
        self.tabs = {}
        tab_bar = _style(Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6), 'robo-tabs')
        tab_bar.set_homogeneous(True)
        group = None
        for tid, title, emoji, section_ids in TABS:
            page = self._tab_page(section_ids)
            if page is None:
                continue
            self.stack.add_named(page, tid)
            group = btn = self._tab_button(tid, title, emoji, group)
            tab_bar.pack_start(btn, True, True, 0)
        root.pack_start(tab_bar, False, False, 0)
        root.pack_start(self.stack, True, True, 0)
        root.pack_start(self._action_bar(), False, False, 0)
        w.add(root)

    def _tab_page(self, section_ids):
        """One tab: its sections' cards (scrolling only if a tab is very tall)."""
        titles = {sid: (title, emoji) for sid, title, emoji in SECTIONS}
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        for side in ('top', 'bottom', 'start', 'end'):
            getattr(content, f'set_margin_{side}')(18)
        empty = True
        for sid in section_ids:
            fields = [f for f in FIELDS if f.section == sid]
            if fields:
                empty = False
                content.pack_start(self._card(*titles[sid], fields), False, False, 0)
        if empty:
            return None
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.add(content)
        return scroller

    def _tab_button(self, tid, title, emoji, group):
        btn = _style(Gtk.RadioButton.new_from_widget(group), 'robo-tab')
        btn.set_mode(False)                    # a button, not a radio circle
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.pack_start(_style(Gtk.Label(label=emoji), 'robo-tab-emoji'), False, False, 0)
        box.pack_start(_style(Gtk.Label(label=title), 'robo-tab-label'), False, False, 0)
        btn.add(box)
        btn.connect('toggled', lambda b: b.get_active() and self.stack.set_visible_child_name(tid))
        self.tabs[tid] = btn
        return btn

    def show_tab(self, tid):
        if tid in self.tabs:
            self.tabs[tid].set_active(True)
            self.stack.set_visible_child_name(tid)

    def _card(self, title, emoji, fields):
        card = _style(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12), 'robo-card')
        head = _style(Gtk.Label(label=f'{emoji}  {title}', xalign=0), 'robo-card-title')
        card.pack_start(head, False, False, 0)
        for f in fields:
            card.pack_start(self._row(f), False, False, 0)
        return card

    def _row(self, f):
        row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        top.pack_start(_style(Gtk.Label(label=f.label, xalign=0), 'robo-row-label'), True, True, 0)
        row.pack_start(top, False, False, 0)

        if f.kind in ('bool', 'memory'):
            sw = Gtk.Switch(valign=Gtk.Align.CENTER)
            sw.connect('notify::active', self._changed)
            top.pack_end(sw, False, False, 0)
            control = _Control(row, sw.get_active, sw.set_active)
            if f.kind == 'memory':                # ...and what he remembers, to erase
                self._memory_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
                row.pack_end(self._memory_box, False, False, 0)
        elif f.kind in ('float', 'seconds'):
            control = self._slider(f, row, top)
        elif f.kind == 'characters':
            control = self._character_chips(row)
        elif f.kind == 'look':
            control = self._look_chips(row)
        elif f.kind == 'choice':
            control = self._choice(f, row, top)
        else:
            raise ValueError(f'unknown setting kind {f.kind!r}')

        if f.help:
            hint = _style(Gtk.Label(label=f.help, xalign=0), 'robo-help')
            hint.set_line_wrap(True)
            row.pack_start(hint, False, False, 0)
        self.controls[f.key] = control
        return row

    def _slider(self, f, row, top):
        value_label = _style(Gtk.Label(), 'robo-value')
        top.pack_end(value_label, False, False, 0)
        if f.kind == 'float':
            scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, f.min, f.max, f.step)
            digits = 0 if f.step >= 1 else 1

            def get():
                return round(scale.get_value(), digits)

            def set_(v):
                scale.set_value(v)
        else:   # 'seconds': slide over a list of friendly presets
            opts = f.options
            scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, len(opts) - 1, 1)

            def get():
                return float(opts[int(round(scale.get_value()))])

            def set_(v):
                scale.set_value(min(range(len(opts)), key=lambda i: abs(opts[i] - v)))
        scale.set_draw_value(False)
        scale.connect('scroll-event', _pass_scroll_to_page)

        def on_value(*_):
            if f.kind == 'seconds':                 # snap to a preset
                i = round(scale.get_value())
                if abs(scale.get_value() - i) > 1e-6:
                    scale.set_value(i)
                    return
            value_label.set_text(f.fmt(get()))
            self._changed()
        scale.connect('value-changed', on_value)
        row.pack_start(scale, False, False, 0)

        def set_and_label(v):
            set_(v)
            value_label.set_text(f.fmt(get()))
        return _Control(row, get, set_and_label)

    def _choice(self, f, row, top):
        combo = Gtk.ComboBoxText(valign=Gtk.Align.CENTER)
        for value, label in f.choices:
            combo.append(value, label)
        top.pack_end(combo, False, False, 0)
        status = _style(Gtk.Label(xalign=0), 'robo-help')
        status.set_line_wrap(True)
        status.set_selectable(True)            # so you can copy the install / login command
        if f.key == 'agent':                   # only the AI brain has a status to show
            row.pack_start(status, False, False, 0)

        def changed(*_):
            if f.key == 'agent':
                self._show_agent_status(combo.get_active_id(), status)
            self._changed()
        combo.connect('changed', changed)

        def get():
            return combo.get_active_id() or f.choices[0][0]

        def set_(value):
            combo.set_active_id(value if any(v == value for v, _l in f.choices)
                                else f.choices[0][0])
        return _Control(row, get, set_)

    def _show_agent_status(self, agent_id, label):
        """Is that agent's CLI installed and logged in? (checked in the background)"""
        from robo.agents import make_backend
        backend = make_backend(agent_id, os.path.expanduser('~'))
        if backend is None:
            label.set_text('Robo answers with his own little rule book, fully offline.')
            return
        label.set_text(f'Checking {backend.name}…')

        def check():
            st = backend.status()
            text = ('✓ ' if st.ready and st.logged_in else '✗ ' if not st.ready else '') + st.detail
            if st.fix:
                text += f'\n{st.fix}'
            GLib.idle_add(lambda: label.get_text().startswith('Checking ' + backend.name)
                          and label.set_text(text) and False)
        threading.Thread(target=check, daemon=True).start()

    def _show_memory(self):
        """List what he remembers, with a ✕ per fact and Forget everything."""
        box, mem = self._memory_box, self.memory
        if box is None:
            return
        for child in box.get_children():
            box.remove(child)
        if mem is None:
            box.show_all()
            return
        facts = ([f'Your name: {mem.name}'] if mem.name else []) + \
            [f['text'] for f in mem.facts]
        if not facts:
            box.pack_start(_style(Gtk.Label(label="He doesn't remember anything about you yet.",
                                            xalign=0), 'robo-help'), False, False, 0)
        for i, text in enumerate(facts):
            line = Gtk.Box(spacing=6)
            label = Gtk.Label(label='• ' + text, xalign=0)
            label.set_line_wrap(True)
            line.pack_start(label, True, True, 0)
            x = Gtk.Button(label='✕')
            x.set_relief(Gtk.ReliefStyle.NONE)
            x.set_tooltip_text('Forget this')
            if mem.name and i == 0:
                x.connect('clicked', lambda *_: (setattr(mem, 'name', ''), mem.save(),
                                                 self._show_memory()))
            else:
                k = i - (1 if mem.name else 0)
                x.connect('clicked', lambda *_a, k=k: (mem.forget_fact(k), self._show_memory()))
            line.pack_end(x, False, False, 0)
            box.pack_start(line, False, False, 0)
        if facts or mem.tasks:
            forget = _style(Gtk.Button(label='Forget everything'), 'robo-secondary')
            forget.set_halign(Gtk.Align.START)
            forget.connect('clicked', lambda *_: (mem.forget('all'), self._show_memory()))
            box.pack_start(forget, False, False, 0)
        box.show_all()

    def _chip_flow(self):
        flow = Gtk.FlowBox()
        flow.set_selection_mode(Gtk.SelectionMode.NONE)
        flow.set_min_children_per_line(3)
        flow.set_max_children_per_line(3)
        flow.set_homogeneous(True)
        flow.set_column_spacing(8)
        flow.set_row_spacing(8)
        return flow

    def _chip(self, flow, cid, tooltip, as_look=False):
        """One toggle button with the character drawn on it (it acts on hover)."""
        character = characters.get(cid)
        btn = _style(Gtk.ToggleButton(), 'robo-chip')
        btn.set_tooltip_text(tooltip)
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        art = Gtk.DrawingArea()
        art.set_size_request(CHIP_W, CHIP_H)
        art.connect('draw', self._draw_chip, cid, btn, as_look)
        inner.pack_start(art, False, False, 0)
        inner.pack_start(Gtk.Label(label=character.title), False, False, 0)
        btn.add(inner)
        key = ('look', cid) if as_look else cid
        btn.connect('enter-notify-event', lambda *_a, k=key: setattr(self, '_hover', k))
        btn.connect('leave-notify-event', lambda *_a: setattr(self, '_hover', None))
        flow.add(btn)
        self._chip_art.append(art)
        return btn

    def _character_chips(self, row):
        flow = self._chip_flow()
        chips = {}
        for cid in characters.costume_ids():
            title = characters.title(cid).lower()
            btn = self._chip(flow, cid, f'Hover to see the {title} in action')
            btn.connect('toggled', self._changed)
            chips[cid] = btn
        row.pack_start(flow, False, False, 0)

        def get():
            return tuple(c for c, b in chips.items() if b.get_active())

        def set_(value):
            for c, b in chips.items():
                b.set_active(c in value)
        return _Control(row, get, set_)

    def _look_chips(self, row):
        """Pick exactly one: what Robo looks like the rest of the time."""
        flow = self._chip_flow()
        chips, chosen = {}, {'id': characters.DEFAULT_LOOK}

        def toggled(btn, cid):
            if self._picking:
                return
            self._picking = True
            try:
                if btn.get_active():
                    chosen['id'] = cid
                for c, b in chips.items():
                    b.set_active(c == chosen['id'])
            finally:
                self._picking = False
            self._changed()

        for cid in characters.look_ids():
            c = characters.get(cid)
            can = ', '.join({'fly': 'flies around the screen', 'hang': 'swings up on a web',
                             'teleport': 'teleports'}[a.kind] for a in c.travel)
            tip = c.title + (f' ({can})' if can else '')
            btn = self._chip(flow, cid, tip, as_look=True)
            btn.connect('toggled', toggled, cid)
            chips[cid] = btn
        row.pack_start(flow, False, False, 0)

        def get():
            return chosen['id']

        def set_(value):
            chosen['id'] = value if value in chips else characters.DEFAULT_LOOK
            self._picking = True
            try:
                for c, b in chips.items():
                    b.set_active(c == chosen['id'])
            finally:
                self._picking = False
        return _Control(row, get, set_)

    def _action_bar(self):
        bar = _style(Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8), 'robo-actions')
        reset = _style(Gtk.Button(label='↺  Defaults'), 'robo-secondary')
        reset.set_tooltip_text('Fill in the default values (press Apply to use them)')
        reset.connect('clicked', lambda *_: self._load(Settings()))
        self.status = _style(Gtk.Label(xalign=0.5), 'robo-status')
        close = _style(Gtk.Button(label='Close'), 'robo-secondary')
        close.connect('clicked', lambda *_: self._on_close())
        self.apply_btn = _style(Gtk.Button(label='✓  Apply'), 'robo-primary')
        self.apply_btn.connect('clicked', lambda *_: self._apply())
        bar.pack_start(reset, False, False, 0)
        bar.pack_start(self.status, True, True, 0)
        bar.pack_end(self.apply_btn, False, False, 0)
        bar.pack_end(close, False, False, 0)
        return bar

    # ------------------------------------------------------------ values
    def _load(self, settings):
        self._loading = True
        try:
            for key, control in self.controls.items():
                control.set(getattr(settings, key))
        finally:
            self._loading = False
        self._refresh()

    def _read(self):
        return self.applied.with_changes(**{k: c.get() for k, c in self.controls.items()})

    @property
    def dirty(self):
        return self.snapshot is not None and self._read() != self.snapshot

    def _changed(self, *_):
        if not self._loading:
            self._refresh()

    def _refresh(self):
        for key, control in self.controls.items():
            dep = FIELDS_BY_KEY[key].depends
            if dep:
                control.row.set_sensitive(bool(self.controls[dep].get()))
        dirty = self.dirty
        self.apply_btn.set_sensitive(dirty)
        if dirty:
            self._set_status('Unapplied changes…')
        elif self._status_timer is None:
            self._set_status('')

    def _set_status(self, text):
        self.status.set_text(text)

    def _apply(self):
        settings = self._read()
        self.on_apply(settings)
        self.applied = settings
        self.snapshot = self._read()
        self._apply_time = time.monotonic()
        self._refresh()
        self._set_status('Applied! ✓')
        if self._status_timer:
            GLib.source_remove(self._status_timer)
        self._status_timer = GLib.timeout_add(2500, self._clear_status)

    def _clear_status(self):
        self._status_timer = None
        self._refresh()
        return False

    def _on_close(self, *_):
        self.win.hide()
        if self._timer is not None:
            GLib.source_remove(self._timer)
            self._timer = None
        return True                  # keep the window around for next time

    # ------------------------------------------------------------ animation
    def _animate(self):
        now = time.monotonic()
        dt, self._last = min(0.1, now - self._last), now
        if self._fixing(now):
            self.effects.emit('sparks', now, dt, 1)
        self.effects.update(now)
        self.header.queue_draw()
        if self._hover:
            for art in self._chip_art:
                art.queue_draw()
        return True

    def _fixing(self, now):
        cycle = (now - self.t0) % 7.0
        return 4.6 < cycle < 6.8 and now - self._apply_time > 1.8

    def _draw_header(self, widget, cr):
        now = time.monotonic()
        t = now - self.t0
        w, h = widget.get_allocated_width(), widget.get_allocated_height()
        grad = cairo.LinearGradient(0, 0, 0, h)
        grad.add_color_stop_rgba(0, *BG_TOP)
        grad.add_color_stop_rgba(1, *BG_BOTTOM)
        cr.set_source(grad)
        cr.paint()
        _gear(cr, w * 0.14, h * 0.45, 34, 10, t * 0.4, GEAR)
        _gear(cr, w * 0.14 + 44, h * 0.45 + 34, 18, 8, -t * 0.75, GEAR_ACCENT)
        _gear(cr, w * 0.86, h * 0.5, 28, 9, -t * 0.5, GEAR_ACCENT)
        _gear(cr, w * 0.86 - 36, h * 0.5 - 30, 15, 7, t * 0.95, GEAR)

        cheering = now - self._apply_time < 1.8
        fixing = self._fixing(now)
        hop = abs(math.sin((now - self._apply_time) / 0.6 * 2 * math.pi)) * 10 \
            if now - self._apply_time < 0.6 else 0.0
        blink = 0.1 if (t % 4.0) < 0.14 else 1.0
        look = self.controls['look'].get() if 'look' in self.controls else ''
        pose = Pose(t=t, costume='mechanic', skin=look, lift=hop, openness=blink,
                    mood='happy' if cheering else ('wince' if fixing else 'normal'),
                    arms='up' if cheering else ('fix' if fixing else 'rest'),
                    antenna='alert' if self.dirty else 'normal', alert_kind='warning',
                    glow=(0.5 + 0.5 * math.sin(t * 6)) if self.dirty else 0.25,
                    particles=self.effects.particles)
        bubble = None
        if now - self._apply_time < 1.8:
            bubble = Bubble('heart', start=self._apply_time, until=self._apply_time + 1.6)
            if now > bubble.until:
                bubble.hide = bubble.until
        scale = (h - 6) / layout.WINDOW_H
        cr.save()
        cr.translate(w / 2 - layout.WINDOW_W * scale / 2, 2)
        cr.push_group()
        draw_frame(cr, scale, pose, bubble, now)
        cr.pop_group_to_source()
        cr.paint()
        cr.restore()
        return False

    def _draw_chip(self, widget, cr, cid, btn, as_look=False):
        now = time.monotonic()
        t = now - self.t0
        character = characters.get(cid)
        if character is None:
            return False
        hovered = self._hover == (('look', cid) if as_look else cid)
        move = character.move
        acting = hovered and move is not None
        pose = Pose(t=t if hovered else 0.3,
                    costume='' if as_look else cid, skin=cid if as_look else '',
                    arms=move.gesture if acting else ('wave' if hovered else 'rest'),
                    mood=move.mood if acting else ('happy' if hovered else 'normal'))
        w, h = widget.get_allocated_width(), widget.get_allocated_height()
        s = (h - 4) / 165
        cr.save()
        cr.translate(w / 2, h - 3)
        cr.scale(s, s)
        cr.push_group()
        draw_robot(cr, pose)
        cr.pop_group_to_source()
        cr.paint_with_alpha(1.0 if btn.get_active() else 0.35)
        cr.restore()
        return False
