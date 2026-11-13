"""Showing Robo your screen on Linux: the ScreenCast portal, PipeWire, a red border.

    1. You pick "Show Robo my screen" in his menu.
    2. GNOME's own screen-sharing dialog asks which screen or window to show
       (org.freedesktop.portal.ScreenCast). Robo can't choose, and nothing is
       remembered for next time (persist_mode 0): every share starts with you.
    3. While it's on, GNOME shows its own screen-sharing icon in the top bar,
       and Robo draws a pulsing red border around the screen you shared, with
       a banner at the top: "Robo can see this screen  [Stop]".
    4. When you ask him something, he takes the latest frame from the stream.
       No banner on screen, no frame: grab() checks.
    5. Stop (the banner, his menu, clicking him, or GNOME's top-bar icon) closes
       the portal session, the stream and the border together.

Robo's own window is an X11 one (GDK_BACKEND=x11, see __init__.py), which
can't see other windows under Wayland at all, so the portal is the only way.
"""
import io
import logging
import math
import os
import random

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402
import cairo  # noqa: E402

from robo.core.geometry import Rect  # noqa: E402
from robo.platform.base import ScreenShare, ShareInfo  # noqa: E402

log = logging.getLogger(__name__)

PORTAL = 'org.freedesktop.portal.Desktop'
PORTAL_PATH = '/org/freedesktop/portal/desktop'
SCREENCAST = 'org.freedesktop.portal.ScreenCast'
MONITOR, WINDOW = 1, 2
CURSOR_EMBEDDED = 2
MAX_SIDE = 1568                  # pictures are scaled down to this (what Claude reads best)
BORDER = 7
RED = (0.93, 0.16, 0.22)


def _gst():
    try:
        gi.require_version('Gst', '1.0')
        from gi.repository import Gst
        Gst.init(None)
        return Gst if Gst.ElementFactory.find('pipewiresrc') else None
    except (ValueError, ImportError):
        return None


class PortalScreenShare(ScreenShare):
    def __init__(self):
        self._bus = None
        self._session = None
        self._pipeline = None
        self._sink = None
        self._fd = None
        self._subs = []
        self._on_ended = None
        self._indicator = None
        self._token = random.randrange(1 << 30)
        self.info = None

    # ------------------------------------------------------------ ScreenShare
    def problem(self):
        if _gst() is None:
            return 'GStreamer with the PipeWire plugin is needed (gstreamer1.0-pipewire)'
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            v = bus.call_sync(PORTAL, PORTAL_PATH, 'org.freedesktop.DBus.Properties', 'Get',
                              GLib.Variant('(ss)', (SCREENCAST, 'AvailableSourceTypes')),
                              None, Gio.DBusCallFlags.NONE, 3000, None)
            if not v.unpack()[0] & MONITOR:
                return "this desktop can't share a screen"
        except GLib.Error as e:
            return f'the screen-sharing portal is not available ({e.message})'
        return None

    @property
    def active(self):
        return self._pipeline is not None

    def start(self, on_started, on_ended):
        if self._session is not None:
            return
        self._on_ended = on_ended
        try:
            self._bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except GLib.Error as e:
            on_ended(f'no session bus: {e.message}')
            return

        def created(results):
            self._session = results.get('session_handle')
            self._subs.append(self._bus.signal_subscribe(
                PORTAL, 'org.freedesktop.portal.Session', 'Closed', self._session, None,
                Gio.DBusSignalFlags.NONE, lambda *_: self._end('the sharing was stopped')))
            self._request('SelectSources', [GLib.Variant('o', self._session)], {
                'types': GLib.Variant('u', MONITOR | WINDOW),
                'multiple': GLib.Variant('b', False),
                'cursor_mode': GLib.Variant('u', CURSOR_EMBEDDED),
                'persist_mode': GLib.Variant('u', 0)}, selected)

        def selected(_results):
            self._request('Start', [GLib.Variant('o', self._session), GLib.Variant('s', '')],
                          {}, started)

        def started(results):
            streams = results.get('streams') or []
            if not streams:
                self._end('nothing was picked')
                return
            node, props = streams[0]
            kind = 'window' if props.get('source_type') == WINDOW else 'monitor'
            rect = None
            if kind == 'monitor' and 'position' in props and 'size' in props:
                (x, y), (w, h) = props['position'], props['size']
                rect = Rect(x, y, w, h)
            try:
                self._open_stream(node)
            except Exception as e:          # noqa: BLE001
                log.exception('could not open the screen stream')
                self._end(f'could not open the stream: {e}')
                return
            self.info = ShareInfo(kind, rect)
            self._indicator = ShareIndicator(self.info, on_stop=self.stop)
            self._indicator.show()
            log.info('sharing a %s with Robo (%s)', kind, rect)
            on_started(self.info)

        self._request('CreateSession', [], {
            'session_handle_token': GLib.Variant('s', self._next_token('robo_session'))}, created)

    def grab(self):
        """The latest frame as PNG bytes, only while the indicator is up."""
        if self._sink is None or self._indicator is None or not self._indicator.visible:
            return None
        sample = self._sink.get_property('last-sample')
        if sample is None:
            return None
        caps = sample.get_caps().get_structure(0)
        width, height = caps.get_value('width'), caps.get_value('height')
        buf = sample.get_buffer()
        ok, info = buf.map(_gst().MapFlags.READ)
        if not ok:
            return None
        try:
            stride = len(info.data) // height
            data = bytearray(info.data)
        finally:
            buf.unmap(info)
        src = cairo.ImageSurface.create_for_data(data, cairo.FORMAT_RGB24, width, height, stride)
        k = min(1.0, MAX_SIDE / max(width, height))
        out = cairo.ImageSurface(cairo.FORMAT_RGB24, max(1, int(width * k)), max(1, int(height * k)))
        cr = cairo.Context(out)
        cr.scale(k, k)
        cr.set_source_surface(src, 0, 0)
        cr.get_source().set_filter(cairo.FILTER_GOOD)
        cr.paint()
        png = io.BytesIO()
        out.write_to_png(png)
        return png.getvalue()

    def stop(self):
        self._end('you stopped sharing')

    # ------------------------------------------------------------ portal plumbing
    def _next_token(self, prefix):
        self._token += 1
        return f'{prefix}_{self._token}'

    def _request(self, method, args, options, on_response):
        """Call a portal method that answers with a Request 'Response' signal."""
        token = self._next_token('robo')
        sender = self._bus.get_unique_name()[1:].replace('.', '_')
        path = f'/org/freedesktop/portal/desktop/request/{sender}/{token}'
        sub = None

        def response(_conn, _sender, _path, _iface, _signal, params):
            self._bus.signal_unsubscribe(sub)
            code, results = params.unpack()
            if code != 0:                       # 1 = you cancelled, 2 = it failed
                self._end('you cancelled' if code == 1 else 'the portal said no')
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
                self._end(f'the screen-sharing portal failed: {e.message}')
        self._bus.call(PORTAL, PORTAL_PATH, SCREENCAST, method, params, None,
                       Gio.DBusCallFlags.NONE, -1, None, done)

    def _open_stream(self, node):
        Gst = _gst()
        result, fds = self._bus.call_with_unix_fd_list_sync(
            PORTAL, PORTAL_PATH, SCREENCAST, 'OpenPipeWireRemote',
            GLib.Variant('(oa{sv})', (self._session, {})), GLib.VariantType('(h)'),
            Gio.DBusCallFlags.NONE, -1, None, None)
        self._fd = fds.get(result.unpack()[0])
        self._pipeline = Gst.parse_launch(
            f'pipewiresrc fd={self._fd} path={node} always-copy=true keepalive-time=1000 '
            '! videoconvert ! video/x-raw,format=BGRx '
            '! appsink name=sink max-buffers=1 drop=true sync=false enable-last-sample=true')
        self._sink = self._pipeline.get_by_name('sink')
        bus = self._pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect('message::error', lambda _b, m: self._end(
            f'the stream stopped ({m.parse_error()[0].message})'))
        bus.connect('message::eos', lambda *_: self._end('the stream ended'))
        self._pipeline.set_state(Gst.State.PLAYING)

    def _end(self, reason):
        """Tear everything down (idempotent). Tells Robo once."""
        if self._indicator is not None:
            self._indicator.hide()
            self._indicator = None
        if self._pipeline is not None:
            self._pipeline.set_state(_gst().State.NULL)
            self._pipeline.get_bus().remove_signal_watch()
            self._pipeline = self._sink = None
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None
        if self._bus is not None:
            for sub in self._subs:
                self._bus.signal_unsubscribe(sub)
            self._subs = []
            if self._session:
                self._bus.call(PORTAL, self._session, 'org.freedesktop.portal.Session', 'Close',
                               None, None, Gio.DBusCallFlags.NONE, -1, None, None)
        self._session = None
        self.info = None
        on_ended, self._on_ended = self._on_ended, None
        if on_ended is not None:                       # once per share
            log.info('screen sharing ended: %s', reason)
            on_ended(reason)


# ---------------------------------------------------------------- the indicator
class ShareIndicator:
    """A pulsing red border around what you shared, and a banner with Stop.

    The border windows let every click through; only the banner takes clicks."""

    def __init__(self, info, on_stop):
        self.info = info
        self.on_stop = on_stop
        self.frames = []
        self.banner = None
        self.visible = False
        self._timer = None
        self._t = 0.0

    def _areas(self):
        if self.info.rect is not None:
            return [self.info.rect]
        display = Gdk.Display.get_default()        # one window: we can't tell where it is
        out = []
        for i in range(display.get_n_monitors()):
            g = display.get_monitor(i).get_geometry()
            out.append(Rect(g.x, g.y, g.width, g.height))
        return out

    def show(self):
        areas = self._areas()
        for r in areas:
            self.frames.append(self._frame(r))
        top = areas[0]
        self.banner = self._banner(top)
        self.visible = True
        self._timer = GLib.timeout_add(40, self._pulse)

    def hide(self):
        self.visible = False
        if self._timer is not None:
            GLib.source_remove(self._timer)
            self._timer = None
        for w in self.frames + ([self.banner] if self.banner else []):
            w.destroy()
        self.frames, self.banner = [], None

    def _popup(self, r):
        w = Gtk.Window(type=Gtk.WindowType.POPUP)
        w.set_title('Robo can see this')
        screen = w.get_screen()
        visual = screen.get_rgba_visual()
        if visual is not None:
            w.set_visual(visual)
        w.set_app_paintable(True)
        w.move(int(r.x), int(r.y))
        w.set_size_request(int(r.w), int(r.h))
        w.resize(int(r.w), int(r.h))
        return w

    def _frame(self, r):
        w = self._popup(r)
        w.connect('draw', self._draw_frame)
        w.connect('realize', lambda win: win.input_shape_combine_region(cairo.Region()))
        w.show_all()
        return w

    def _draw_frame(self, widget, cr):
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        w, h = widget.get_allocated_width(), widget.get_allocated_height()
        pulse = 0.5 + 0.5 * math.sin(self._t * 3.2)
        for i, alpha in ((0, 0.95), (1, 0.35 + 0.35 * pulse), (2, 0.15 + 0.25 * pulse)):
            lw = BORDER if i == 0 else BORDER + 6 * i * (0.6 + 0.4 * pulse)
            cr.set_source_rgba(*RED, alpha)
            cr.set_line_width(lw)
            cr.rectangle(lw / 2, lw / 2, w - lw, h - lw)
            cr.stroke()
        return False

    def _banner(self, area):
        text = ('Robo can see this screen' if self.info.kind == 'monitor'
                else 'Robo can see the window you picked')
        bw, bh = 380, 44
        r = Rect(area.x + (area.w - bw) // 2, area.y + 14, bw, bh)
        w = self._popup(r)
        box = Gtk.Box(spacing=10)
        box.set_margin_start(16)
        box.set_margin_end(8)
        dot = Gtk.DrawingArea()
        dot.set_size_request(14, 14)
        dot.set_valign(Gtk.Align.CENTER)
        dot.connect('draw', self._draw_dot)
        box.pack_start(dot, False, False, 0)
        label = Gtk.Label()
        label.set_markup(f'<b><span foreground="white">{text}</span></b>')
        box.pack_start(label, True, True, 0)
        stop = Gtk.Button(label='Stop')
        stop.set_valign(Gtk.Align.CENTER)
        stop.connect('clicked', lambda *_: self.on_stop())
        box.pack_end(stop, False, False, 0)
        w.add(box)
        w.connect('draw', self._draw_banner)
        provider = Gtk.CssProvider()
        provider.load_from_data(b'button { background-image: none; background-color: white;'
                                b' color: #C0202E; font-weight: 800; border-radius: 14px;'
                                b' border: none; padding: 3px 14px; box-shadow: none; }'
                                b' button:hover { background-color: #FFE3E5; }')
        stop.get_style_context().add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        w.show_all()
        return w

    def _draw_banner(self, widget, cr):
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
        cr.set_source_rgba(*RED, 0.96)
        cr.fill()
        return False

    def _draw_dot(self, widget, cr):
        pulse = 0.5 + 0.5 * math.sin(self._t * 3.2)
        cr.arc(7, 7, 4 + 2.5 * pulse, 0, 2 * math.pi)
        cr.set_source_rgba(1, 1, 1, 0.55 + 0.45 * pulse)
        cr.fill()
        return False

    def _pulse(self):
        self._t += 0.04
        self._ticks = getattr(self, '_ticks', 0) + 1
        for w in self.frames + ([self.banner] if self.banner else []):
            w.queue_draw()
            if self._ticks % 25 == 0 and w.get_window() is not None:
                w.get_window().raise_()                # stay above other windows
        return True
