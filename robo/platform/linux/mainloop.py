"""GLib/GTK main loop as a Scheduler."""
import signal

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gtk  # noqa: E402

from robo.platform.base import Scheduler  # noqa: E402


def _add_signal_handler(sig, fn):
    try:
        gi.require_version('GLibUnix', '2.0')
        from gi.repository import GLibUnix
        GLibUnix.signal_add(GLib.PRIORITY_DEFAULT, sig, fn)
    except (ValueError, ImportError):
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, sig, fn)


class GLibScheduler(Scheduler):
    def every(self, seconds, fn):
        def wrapper():
            fn()
            return True
        GLib.timeout_add(max(1, int(seconds * 1000)), wrapper)

    def after(self, seconds, fn):
        def wrapper():
            fn()
            return False
        GLib.timeout_add(max(1, int(seconds * 1000)), wrapper)

    def run(self):
        for sig in (signal.SIGINT, signal.SIGTERM):
            _add_signal_handler(sig, self._on_signal)
        Gtk.main()

    def _on_signal(self):
        self.quit()
        return False

    def quit(self):
        Gtk.main_quit()
