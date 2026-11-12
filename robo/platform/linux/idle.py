"""User idle time from the desktop (sees input in every app, Wayland too).

Tries GNOME's org.gnome.Mutter.IdleMonitor first, then the
org.freedesktop.ScreenSaver interface offered by KDE and others.
"""
import logging
import time

from gi.repository import Gio, GLib

from robo.platform.base import IdleMonitor

log = logging.getLogger(__name__)

POLL_MS = 500
INHIBIT_CACHE_SECONDS = 10
INHIBIT_IDLE = 8          # GNOME SessionManager inhibit flag: "idle"

# (bus name, object path, interface, method, multiplier to seconds)
BACKENDS = [
    ('org.gnome.Mutter.IdleMonitor', '/org/gnome/Mutter/IdleMonitor/Core',
     'org.gnome.Mutter.IdleMonitor', 'GetIdletime', 0.001),
    ('org.freedesktop.ScreenSaver', '/org/freedesktop/ScreenSaver',
     'org.freedesktop.ScreenSaver', 'GetSessionIdleTime', 1.0),
]


class MutterIdleMonitor(IdleMonitor):
    @classmethod
    def create(cls):
        """Return a monitor, or None if this desktop offers no idle time."""
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except GLib.Error as e:
            log.info('idle monitor unavailable: %s', e.message)
            return None
        for backend in BACKENDS:
            try:
                bus.call_sync(*backend[:4], None, None, Gio.DBusCallFlags.NONE, 1500, None)
                log.info('idle monitor: using %s', backend[0])
                return cls(bus, backend)
            except GLib.Error:
                continue
        log.info('idle monitor: none found, evil mode disabled')
        return None

    def __init__(self, bus, backend):
        self.bus = bus
        self.backend = backend
        self.on_idle = None
        self._busy = False
        self._inhibit_checked = -1e9
        self._inhibited = False

    def start(self, on_idle):
        self.on_idle = on_idle
        GLib.timeout_add(POLL_MS, self._poll)

    def _poll(self):
        if not self._busy:          # asynchronous: a slow reply never blocks the animation
            self._busy = True
            self.bus.call(*self.backend[:4], None, None, Gio.DBusCallFlags.NONE, 1000,
                          None, self._done)
        return True

    def _done(self, bus, res):
        self._busy = False
        try:
            value = bus.call_finish(res).unpack()[0]
        except GLib.Error:
            return
        self.on_idle(value * self.backend[4])

    def is_inhibited(self):
        now = time.monotonic()
        if now - self._inhibit_checked < INHIBIT_CACHE_SECONDS:
            return self._inhibited
        self._inhibit_checked = now
        try:
            res = self.bus.call_sync(
                'org.gnome.SessionManager', '/org/gnome/SessionManager',
                'org.gnome.SessionManager', 'IsInhibited',
                GLib.Variant('(u)', (INHIBIT_IDLE,)), None, Gio.DBusCallFlags.NONE, 500, None)
            self._inhibited = bool(res.unpack()[0])
        except GLib.Error:
            self._inhibited = False
        return self._inhibited
