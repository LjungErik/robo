"""Battery level and charger state from /sys/class/power_supply."""
import glob
import logging
import os

from gi.repository import GLib

from robo.events import Event
from robo.platform.base import EventSource

log = logging.getLogger(__name__)

POLL_SECONDS = 20
LOW_LEVELS = (20, 10, 5)          # warn once at each of these percentages


class BatteryWatcher(EventSource):
    name = 'battery'

    def __init__(self):
        self.emit = None
        self.bat = next(iter(sorted(glob.glob('/sys/class/power_supply/BAT*'))), None)
        self.last_status = None
        self.warned = set()
        self.full_announced = False

    def start(self, emit):
        self.emit = emit
        if not self.bat:
            log.info('battery watcher: no battery found')
            return
        log.info('battery watcher: %s', self.bat)
        self._poll()
        GLib.timeout_add_seconds(POLL_SECONDS, self._poll)

    def _read(self, name):
        try:
            with open(os.path.join(self.bat, name)) as f:
                return f.read().strip()
        except OSError:
            return None

    def _poll(self):
        try:
            cap = int(self._read('capacity') or -1)
        except ValueError:
            cap = -1
        status = self._read('status') or 'Unknown'
        first = self.last_status is None
        full = status == 'Full' or cap >= 100

        if status == 'Discharging':
            self.full_announced = False
            for lvl in LOW_LEVELS:
                if 0 <= cap <= lvl and lvl not in self.warned:
                    self.warned.update(l for l in LOW_LEVELS if l >= lvl)
                    self.emit(Event('battery_low', 'system', f'{cap}% left'))
                    break
        else:
            self.warned.clear()
            if self.last_status == 'Discharging':
                self.emit(Event('battery_charging', 'system', f'plugged in ({cap}%)'))
            if full and not self.full_announced:
                self.full_announced = True
                if not first:                   # don't announce "full" at start-up
                    self.emit(Event('battery_full', 'system', f'{cap}%'))
        self.last_status = status
        return True
