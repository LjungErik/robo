"""A plugin using your keyboard and mouse on Linux: GNOME's RemoteDesktop portal.

    1. A plugin asks (plugin.input.start()); GNOME shows its own dialog
       ("Allow remote interaction?"). Robo can't answer it for you, and nothing
       is remembered for next time (persist_mode 0).
    2. While it's on, GNOME shows its indicator in the top bar and Robo shows
       an orange banner at the top of the screen: "Robo is using your keyboard
       and mouse  [Stop]".
    3. Keys go in as keysyms (NotifyKeyboardKeysym), the mouse as relative
       motion (NotifyPointerMotion: what games use to look around), buttons
       and the wheel. No screen picture is needed for any of these.
    4. Stop (the banner, saying "stop", clicking Robo, his menu, GNOME's
       indicator) closes the portal session, which ends it for real.
"""
import logging
import math
import random

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402
import cairo  # noqa: E402

from robo.platform.base import InputControl  # noqa: E402

log = logging.getLogger(__name__)

PORTAL = 'org.freedesktop.portal.Desktop'
PORTAL_PATH = '/org/freedesktop/portal/desktop'
REMOTE = 'org.freedesktop.portal.RemoteDesktop'
KEYBOARD, POINTER = 1, 2
BUTTONS = {'left': 0x110, 'right': 0x111, 'middle': 0x112}     # linux/input-event-codes.h
ALIASES = {'ctrl': 'Control_L', 'control': 'Control_L', 'shift': 'Shift_L', 'alt': 'Alt_L',
           'super': 'Super_L', 'win': 'Super_L', 'meta': 'Super_L', 'altgr': 'ISO_Level3_Shift',
           'enter': 'Return', 'return': 'Return', 'esc': 'Escape', 'escape': 'Escape',
           'space': 'space', 'tab': 'Tab', 'backspace': 'BackSpace', 'delete': 'Delete',
           'del': 'Delete', 'insert': 'Insert', 'home': 'Home', 'end': 'End',
           'pageup': 'Page_Up', 'pagedown': 'Page_Down', 'up': 'Up', 'down': 'Down',
           'left': 'Left', 'right': 'Right', 'capslock': 'Caps_Lock', 'plus': 'plus',
           'minus': 'minus', 'menu': 'Menu', 'printscreen': 'Print'}
ORANGE = (0.96, 0.52, 0.12)


def keysym(name):
    """A key name ('w', 'ctrl', 'F5', 'Return', 'é') -> X keysym, or None."""
    name = str(name or '')
    if not name:
        return None
    alias = ALIASES.get(name.lower())
    if alias:
        name = alias
    if len(name) == 1:                     # a character (Unicode keysyms are fine too)
        return Gdk.unicode_to_keyval(ord(name)) or None
    sym = Gdk.keyval_from_name(name)
    if sym in (0, 0xffffff):
        sym = Gdk.keyval_from_name(name.capitalize())
    return None if sym in (0, 0xffffff) else sym


class PortalInput(InputControl):
    def __init__(self):
        self.active = False
        self._bus = None
        self._session = None
        self._subs = []
        self._on_ended = None
        self._banner = None
        self._token = random.randrange(1 << 30)

    def problem(self):
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            v = bus.call_sync(PORTAL, PORTAL_PATH, 'org.freedesktop.DBus.Properties', 'Get',
                              GLib.Variant('(ss)', (REMOTE, 'AvailableDeviceTypes')),
                              None, Gio.DBusCallFlags.NONE, 3000, None)
            if v.unpack()[0] & (KEYBOARD | POINTER) != KEYBOARD | POINTER:
                return "this desktop doesn't let apps use the keyboard and mouse"
        except GLib.Error as e:
            return f'the remote-desktop portal is not available ({e.message})'
        return None

    def start(self, on_started, on_ended):
        if self._session is not None:
            on_ended('already asking')
            return
        self._on_ended = on_ended
        try:
            self._bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except GLib.Error as e:
            self._end(f'no session bus: {e.message}')
            return

        def created(results):
            self._session = results.get('session_handle')
            self._subs.append(self._bus.signal_subscribe(
                PORTAL, 'org.freedesktop.portal.Session', 'Closed', self._session, None,
                Gio.DBusSignalFlags.NONE, lambda *_: self._end('stopped from the desktop')))
            self._request('SelectDevices', [GLib.Variant('o', self._session)], {
                'types': GLib.Variant('u', KEYBOARD | POINTER),
                'persist_mode': GLib.Variant('u', 0)}, selected)

        def selected(_results):
            self._request('Start', [GLib.Variant('o', self._session), GLib.Variant('s', '')],
                          {}, started)

        def started(results):
            if not (results.get('devices', 0) & KEYBOARD):
                self._end('the keyboard was not allowed')
                return
            self.active = True
            self._banner = _Banner(self.stop)
            log.info('using the keyboard and mouse')
            on_started()

        self._request('CreateSession', [], {
            'session_handle_token': GLib.Variant('s', self._next_token('robo_input'))}, created)

    # ------------------------------------------------------------ input
    def _notify(self, method, fmt, *values):
        if not self.active:
            return
        self._bus.call(PORTAL, PORTAL_PATH, REMOTE, method,
                       GLib.Variant(fmt, (self._session, {}) + values), None,
                       Gio.DBusCallFlags.NONE, -1, None, None)

    def key(self, name, down):
        sym = keysym(name)
        if sym is None:
            return False
        self._notify('NotifyKeyboardKeysym', '(oa{sv}iu)', sym, 1 if down else 0)
        return True

    def button(self, name, down):
        code = BUTTONS.get(str(name).lower())
        if code is None:
            return False
        self._notify('NotifyPointerButton', '(oa{sv}iu)', code, 1 if down else 0)
        return True

    def move(self, dx, dy):
        self._notify('NotifyPointerMotion', '(oa{sv}dd)', float(dx), float(dy))

    def scroll(self, steps):
        self._notify('NotifyPointerAxisDiscrete', '(oa{sv}ui)', 0, int(steps))

    def stop(self):
        self._end('you took the controls back')

    # ------------------------------------------------------------ portal plumbing
    def _next_token(self, prefix):
        self._token += 1
        return f'{prefix}_{self._token}'

    def _request(self, method, args, options, on_response):
        token = self._next_token('robo')
        sender = self._bus.get_unique_name()[1:].replace('.', '_')
        path = f'/org/freedesktop/portal/desktop/request/{sender}/{token}'
        sub = None

        def response(_conn, _sender, _path, _iface, _signal, params):
            self._bus.signal_unsubscribe(sub)
            code, results = params.unpack()
            if code != 0:
                self._end('you said no' if code == 1 else 'the portal said no')
                return
            on_response(results)
        sub = self._bus.signal_subscribe(PORTAL, 'org.freedesktop.portal.Request', 'Response',
                                         path, None, Gio.DBusSignalFlags.NONE, response)
        options = dict(options, handle_token=GLib.Variant('s', token))
        params = GLib.Variant.new_tuple(*args, GLib.Variant('a{sv}', options))

        def done(bus, result):
            try:
                bus.call_finish(result)
            except GLib.Error as e:
                self._bus.signal_unsubscribe(sub)
                self._end(f'the remote-desktop portal failed: {e.message}')
        self._bus.call(PORTAL, PORTAL_PATH, REMOTE, method, params, None,
                       Gio.DBusCallFlags.NONE, -1, None, done)

    def _end(self, reason):
        self.active = False
        if self._banner is not None:
            self._banner.hide()
            self._banner = None
        if self._bus is not None:
            for sub in self._subs:
                self._bus.signal_unsubscribe(sub)
            self._subs = []
            if self._session:
                self._bus.call(PORTAL, self._session, 'org.freedesktop.portal.Session', 'Close',
                               None, None, Gio.DBusCallFlags.NONE, -1, None, None)
        self._session = None
        on_ended, self._on_ended = self._on_ended, None
        if on_ended is not None:
            log.info('keyboard and mouse given back: %s', reason)
            on_ended(reason)


class _Banner:
    """An orange pill at the top of the screen with a Stop button."""

    def __init__(self, on_stop):
        self._t = 0.0
        w = self.window = Gtk.Window(type=Gtk.WindowType.POPUP)
        w.set_title('Robo is using your keyboard and mouse')
        visual = w.get_screen().get_rgba_visual()
        if visual is not None:
            w.set_visual(visual)
        w.set_app_paintable(True)
        w.set_keep_above(True)
        bw, bh = 470, 44
        g = Gdk.Display.get_default().get_primary_monitor() or \
            Gdk.Display.get_default().get_monitor(0)
        area = g.get_geometry()
        w.move(area.x + (area.width - bw) // 2, area.y + 14 + 52)   # below a screen banner
        w.set_default_size(bw, bh)
        box = Gtk.Box(spacing=10)
        box.set_margin_start(16)
        box.set_margin_end(8)
        label = Gtk.Label()
        label.set_markup('<b><span foreground="white">🎮  Robo is using your keyboard and '
                         'mouse</span></b>')
        box.pack_start(label, True, True, 0)
        stop = Gtk.Button(label='Stop')
        stop.set_valign(Gtk.Align.CENTER)
        stop.connect('clicked', lambda *_: on_stop())
        provider = Gtk.CssProvider()
        provider.load_from_data(b'button { background-image: none; background-color: white;'
                                b' color: #B4520A; font-weight: 800; border-radius: 14px;'
                                b' border: none; padding: 3px 14px; box-shadow: none; }')
        stop.get_style_context().add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        box.pack_end(stop, False, False, 0)
        w.add(box)
        w.connect('draw', self._draw)
        w.show_all()
        self._timer = GLib.timeout_add(1000, self._raise)

    def _draw(self, widget, cr):
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        w, h = widget.get_allocated_width(), widget.get_allocated_height()
        r = h / 2
        cr.new_path()
        cr.arc(r, r, r, math.pi / 2, 3 * math.pi / 2)
        cr.arc(w - r, r, r, -math.pi / 2, math.pi / 2)
        cr.close_path()
        cr.set_source_rgba(*ORANGE, 0.96)
        cr.fill()
        return False

    def _raise(self):
        if self.window.get_window() is not None:
            self.window.get_window().raise_()
        return True

    def hide(self):
        GLib.source_remove(self._timer)
        self.window.destroy()
