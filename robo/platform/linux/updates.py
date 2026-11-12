"""Software updates (apt, snap, flatpak) and "restart required"."""
import logging
import os
import shutil
import subprocess
import threading
import time

from gi.repository import GLib

from robo.events import Event
from robo.platform.base import EventSource

log = logging.getLogger(__name__)

FIRST_CHECK_SECONDS = 90
CHECK_EVERY_SECONDS = 2 * 3600
REMIND_EVERY_SECONDS = 6 * 3600
REBOOT_FLAGS = ('/run/reboot-required', '/var/run/reboot-required')


def _run(cmd, timeout=180):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                              env={**os.environ, 'LANG': 'C', 'LC_ALL': 'C'})
    except (OSError, subprocess.SubprocessError):
        return None


def count_apt():
    if os.path.exists('/usr/lib/update-notifier/apt-check'):
        r = _run(['/usr/lib/update-notifier/apt-check'])   # prints "updates;security" to stderr
        if r and ';' in r.stderr:
            try:
                return int(r.stderr.strip().split(';')[0])
            except ValueError:
                pass
    if shutil.which('apt'):
        r = _run(['apt', 'list', '--upgradable'])
        if r:
            return sum(1 for l in r.stdout.splitlines() if '/' in l and 'upgradable' in l)
    return 0


def count_snap():
    if not shutil.which('snap'):
        return 0
    r = _run(['snap', 'refresh', '--list'], timeout=90)
    if not r or r.returncode != 0:
        return 0
    lines = [l for l in r.stdout.splitlines() if l.strip()]
    return len(lines) - 1 if lines and lines[0].startswith('Name') else 0


def count_flatpak():
    if not shutil.which('flatpak'):
        return 0
    r = _run(['flatpak', 'remote-ls', '--updates', '--columns=application'], timeout=90)
    if not r or r.returncode != 0:
        return 0
    return sum(1 for l in r.stdout.splitlines() if l.strip())


COUNTERS = (count_apt, count_snap, count_flatpak)


class UpdateWatcher(EventSource):
    name = 'updates'

    def __init__(self, enabled=True):
        self.emit = None
        self.enabled = enabled
        self.last_count = 0
        self.last_update_note = -1e9
        self.last_reboot_note = -1e9

    def start(self, emit):
        self.emit = emit
        GLib.timeout_add_seconds(FIRST_CHECK_SECONDS, self._first_check)

    def _first_check(self):
        self._check_in_background()
        GLib.timeout_add_seconds(CHECK_EVERY_SECONDS, self._check_in_background)
        return False

    def apply_settings(self, settings):
        was, self.enabled = self.enabled, settings.check_updates
        if self.enabled and not was:            # just switched on: check soon
            GLib.timeout_add_seconds(10, lambda: self._check_in_background() and False)

    def _check_in_background(self):
        # The package tools can take a while; keep them off the main thread.
        if self.enabled:
            threading.Thread(target=self._check, daemon=True).start()
        return True

    def _check(self):
        count = sum(counter() for counter in COUNTERS)
        reboot = any(os.path.exists(p) for p in REBOOT_FLAGS)
        GLib.idle_add(self._report, count, reboot)

    def _report(self, count, reboot):
        now = time.monotonic()
        log.info('update check: %d updates, reboot required=%s', count, reboot)
        if count > 0 and (count > self.last_count
                          or now - self.last_update_note > REMIND_EVERY_SECONDS):
            self.last_update_note = now
            self.emit(Event('update', 'system', f'{count} updates available'))
        self.last_count = count
        if reboot and now - self.last_reboot_note > REMIND_EVERY_SECONDS:
            self.last_reboot_note = now
            self.emit(Event('reboot', 'system', 'restart required'))
        return False
