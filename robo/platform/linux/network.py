"""Online / offline changes from NetworkManager (system D-Bus)."""
import logging

from gi.repository import Gio, GLib

from robo.events import Event
from robo.platform.base import EventSource

log = logging.getLogger(__name__)

NM = 'org.freedesktop.NetworkManager'
NM_PATH = '/org/freedesktop/NetworkManager'
CONNECTED_GLOBAL = 70     # NMState: full internet access
SETTLE_SECONDS = 4        # NetworkManager passes through several states; wait until it settles


class NetworkWatcher(EventSource):
    name = 'network'

    def __init__(self):
        self.emit = None
        self.online = None
        self._pending = None

    def start(self, emit):
        self.emit = emit
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
            res = bus.call_sync(NM, NM_PATH, 'org.freedesktop.DBus.Properties', 'Get',
                                GLib.Variant('(ss)', (NM, 'State')),
                                None, Gio.DBusCallFlags.NONE, 3000, None)
            self.online = res.unpack()[0] >= CONNECTED_GLOBAL
            bus.signal_subscribe(NM, NM, 'StateChanged', NM_PATH, None,
                                 Gio.DBusSignalFlags.NONE, self._on_state)
            self.bus = bus
            log.info('network watcher: online=%s', self.online)
        except GLib.Error as e:
            log.info('network watcher unavailable: %s', e.message)

    def _on_state(self, conn, sender, path, iface, signal, params):
        if self._pending:
            GLib.source_remove(self._pending)
        online = params.unpack()[0] >= CONNECTED_GLOBAL
        self._pending = GLib.timeout_add_seconds(SETTLE_SECONDS, self._settle, online)

    def _settle(self, online):
        self._pending = None
        if online != self.online:
            self.online = online
            self.emit(Event('wifi' if online else 'wifi_off', 'system',
                            'back online' if online else 'went offline'))
        return False
