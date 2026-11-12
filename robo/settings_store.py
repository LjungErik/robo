"""Saving and loading settings as a small JSON file.

The file can also be edited by hand; RoboApp checks it every couple of
seconds and applies changes on the fly.
"""
import json
import logging
import os

from robo.config import Settings

log = logging.getLogger(__name__)

FILE_NAME = 'settings.json'


class SettingsStore:
    def __init__(self, directory):
        self.path = os.path.join(directory, FILE_NAME)
        self._seen_mtime = self._mtime()

    def _mtime(self):
        try:
            return os.stat(self.path).st_mtime_ns
        except OSError:
            return None

    def load(self, base=None):
        """Settings from the file on top of `base` (defaults if no file)."""
        self._seen_mtime = self._mtime()
        try:
            with open(self.path, encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            return base or Settings()
        except (OSError, ValueError) as e:
            log.warning('could not read %s (%s); using defaults', self.path, e)
            return base or Settings()
        if not isinstance(data, dict):
            return base or Settings()
        return Settings.from_dict(data, base)

    def save(self, settings):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(settings.to_dict(), f, indent=2)
            f.write('\n')
        os.replace(tmp, self.path)          # atomic: never a half-written file
        self._seen_mtime = self._mtime()

    def changed_on_disk(self):
        """True once after someone else changed the file."""
        mtime = self._mtime()
        if mtime is not None and mtime != self._seen_mtime:
            self._seen_mtime = mtime
            return True
        return False
