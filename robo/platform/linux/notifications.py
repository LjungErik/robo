"""Desktop notifications, read by eavesdropping on the D-Bus session bus.

We call BecomeMonitor (like `dbus-monitor` does) so the bus copies us every
notification any app sends, via either:
  * org.freedesktop.Notifications.Notify       (classic, most apps)
  * org.gtk.Notifications.AddNotification      (GNOME apps, Flatpak portals)
"""
import logging
import time

from gi.repository import Gio, GLib

from robo.events import Event, classify
from robo.platform.base import EventSource

log = logging.getLogger(__name__)

MATCH_RULES = [
    "type='method_call',interface='org.freedesktop.Notifications',member='Notify'",
    "type='method_call',interface='org.gtk.Notifications',member='AddNotification'",
]
DUPLICATE_WINDOW = 3     # seconds; portals + shell can deliver the same notification twice


def _str(v):
    return v if isinstance(v, str) else ''


class NotificationWatcher(EventSource):
    name = 'notifications'

    def __init__(self):
        self.emit = None
        self.conn = None
        self._recent = {}

    def start(self, emit):
        self.emit = emit
        self._connect()

    # ------------------------------------------------------------ connection
    def _connect(self):
        try:
            addr = Gio.dbus_address_get_for_bus_sync(Gio.BusType.SESSION, None)
            conn = Gio.DBusConnection.new_for_address_sync(
                addr,
                Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT
                | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,
                None, None)
            conn.add_filter(self._filter)
            conn.call_sync(
                'org.freedesktop.DBus', '/org/freedesktop/DBus',
                'org.freedesktop.DBus.Monitoring', 'BecomeMonitor',
                GLib.Variant('(asu)', (MATCH_RULES, 0)),
                None, Gio.DBusCallFlags.NONE, -1, None)
            conn.connect('closed', self._on_closed)
            self.conn = conn
            log.info('notification monitor: listening')
        except GLib.Error as e:
            log.warning('notification monitor failed: %s; retrying in 15s', e.message)
            GLib.timeout_add_seconds(15, self._retry)

    def _retry(self):
        self._connect()
        return False

    def _on_closed(self, *_):
        log.info('notification monitor: bus connection closed; reconnecting')
        self.conn = None
        GLib.timeout_add_seconds(5, self._retry)

    # ------------------------------------------------------------ messages
    def _filter(self, conn, msg, incoming):
        # Runs on GDBus' worker thread.
        if not incoming or msg.get_message_type() != Gio.DBusMessageType.METHOD_CALL:
            return msg
        try:
            body = msg.get_body()
            if body is not None:
                iface, member = msg.get_interface(), msg.get_member()
                if iface == 'org.freedesktop.Notifications' and member == 'Notify':
                    self._handle_freedesktop(body)
                elif iface == 'org.gtk.Notifications' and member == 'AddNotification':
                    self._handle_gtk(body)
        except Exception as e:  # never let a weird message kill the monitor
            log.warning('notification parse error: %s', e)
        # A monitor must never answer method calls (the bus would disconnect
        # us), so swallow every incoming call.
        return None

    def _handle_freedesktop(self, body):
        # Notify(app_name, replaces_id, icon, summary, body, actions, hints, timeout)
        app = _str(body.get_child_value(0).unpack())
        summary = _str(body.get_child_value(3).unpack())
        text = _str(body.get_child_value(4).unpack())
        hints = body.get_child_value(6)
        category = hints.lookup_value('category', None)
        urgency = hints.lookup_value('urgency', None)
        try:
            urgent = urgency is not None and int(urgency.unpack()) == 2
        except (TypeError, ValueError):
            urgent = False
        self._dispatch(app, summary, text, _str(category.unpack() if category else ''), urgent)

    def _handle_gtk(self, body):
        # AddNotification(app_id, notification_id, {title, body, priority, ...})
        app = _str(body.get_child_value(0).unpack())
        notif = body.get_child_value(2)

        def get(key):
            v = notif.lookup_value(key, None)
            return _str(v.unpack()) if v is not None else ''
        self._dispatch(app, get('title'), get('body'), get('category'),
                       get('priority') == 'urgent')

    def _dispatch(self, app, summary, body, category, urgent):
        key = (summary, body)
        now = time.monotonic()
        if now - self._recent.get(key, -1e9) < DUPLICATE_WINDOW:
            return
        self._recent[key] = now
        if len(self._recent) > 64:
            self._recent = {k: v for k, v in self._recent.items() if now - v < 10}
        event = Event(classify(app, summary, body, category, urgent), 'notification',
                      f'{app}: {summary} — {body}'.strip())
        GLib.idle_add(self.emit, event)     # hand over to the main thread
