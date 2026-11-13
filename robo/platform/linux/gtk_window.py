"""GTK 3 implementation of WindowHost.

A POPUP (override-redirect) window: the window manager leaves it alone,
so it has no decorations, no taskbar entry, never takes focus, and can be
moved anywhere. It is transparent (RGBA visual) and uses an input shape so
clicks outside the robot fall through to the desktop.
"""
import logging

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_foreign('cairo')
from gi.repository import Gdk, Gtk  # noqa: E402
import cairo  # noqa: E402

from robo.core.geometry import Rect  # noqa: E402
from robo.platform.base import PointerEvent, WindowHost  # noqa: E402

log = logging.getLogger(__name__)


class GtkWindowHost(WindowHost):
    def __init__(self, width, height, listener):
        self.listener = listener
        self.menu = None
        self._last_button_event = None
        w = self.window = Gtk.Window(type=Gtk.WindowType.POPUP)
        w.set_title('Robot Companion')
        w.set_size_request(width, height)
        w.resize(width, height)
        screen = w.get_screen()
        visual = screen.get_rgba_visual()
        if visual is None or not screen.is_composited():
            log.warning('no compositing — the robot will have a black box around him')
        if visual is not None:
            w.set_visual(visual)
        w.set_app_paintable(True)
        w.add_events(Gdk.EventMask.BUTTON_PRESS_MASK
                     | Gdk.EventMask.BUTTON_RELEASE_MASK
                     | Gdk.EventMask.POINTER_MOTION_MASK)
        w.connect('draw', self._on_draw)
        w.connect('button-press-event', self._on_press)
        w.connect('button-release-event', self._on_release)
        w.connect('motion-notify-event', self._on_motion)
        self._regions = None
        w.connect('realize', lambda *_: self._apply_regions())

    # ------------------------------------------------------------ WindowHost
    def show(self):
        self.window.show_all()

    def move(self, x, y):
        self.window.move(x, y)

    def position(self):
        return self.window.get_position()

    def resize(self, width, height):
        self.window.set_size_request(width, height)
        self.window.resize(width, height)

    def workarea(self):
        display = Gdk.Display.get_default()
        mon = display.get_primary_monitor() or display.get_monitor(0)
        wa = mon.get_workarea()
        return Rect(wa.x, wa.y, wa.width, wa.height)

    def set_click_regions(self, regions):
        self._regions = regions
        self._apply_regions()

    def _apply_regions(self):
        if self._regions is None or self.window.get_window() is None:
            return
        rects = [cairo.RectangleInt(int(r.x), int(r.y), int(r.w), int(r.h)) for r in self._regions]
        self.window.input_shape_combine_region(cairo.Region(rects))

    def redraw(self):
        self.window.queue_draw()

    def pointer_position(self):
        # Under XWayland this only updates while the pointer is over an X11 window.
        try:
            seat = Gdk.Display.get_default().get_default_seat()
            _screen, x, y = seat.get_pointer().get_position()
            return x, y
        except Exception:
            return None

    def keep_on_top(self):
        gdkwin = self.window.get_window()
        if gdkwin is not None and self.menu is None:
            gdkwin.raise_()

    def show_menu(self, items):
        menu = Gtk.Menu()
        for item in items:
            if item.label is None:
                menu.append(Gtk.SeparatorMenuItem())
                continue
            mi = Gtk.MenuItem(label=item.label)
            mi.connect('activate', lambda _mi, fn=item.action: fn())
            menu.append(mi)
        menu.connect('deactivate', lambda *_: setattr(self, 'menu', None))
        menu.show_all()
        self.menu = menu
        if self._last_button_event is not None:
            menu.popup_at_pointer(self._last_button_event)
        else:
            menu.popup_at_pointer(None)

    # ------------------------------------------------------------ GTK signals
    @staticmethod
    def _pointer(ev, button=0):
        return PointerEvent(button, ev.x, ev.y, ev.x_root, ev.y_root)

    def _on_draw(self, _w, cr):
        self.listener.draw(cr)
        return False

    def _on_press(self, _w, ev):
        if ev.type == Gdk.EventType.BUTTON_PRESS:      # ignore double-click events
            self._last_button_event = ev      # lets show_menu() open at this click
            try:
                self.listener.pointer_press(self._pointer(ev, ev.button))
            finally:
                self._last_button_event = None
        return True

    def _on_motion(self, _w, ev):
        self.listener.pointer_motion(self._pointer(ev))
        return True

    def _on_release(self, _w, ev):
        self.listener.pointer_release(self._pointer(ev, ev.button))
        return True
