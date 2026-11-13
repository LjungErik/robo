"""Task: one job Robo does for you, and its lifecycle.

    PENDING ──start()──► RUNNING ──pause()──► PAUSED
                           │  ▲                 │
                           │  └────resume()─────┘
                           ├──► DONE       (is_done() said so)
                           └──► ABORTED    (abort(), from any unfinished state)

A Task never touches the robot. The TaskManager drives it and the
Companion reacts to what happened. To make a real task, subclass Task and
implement is_done(); override the on_* hooks to start, pause, resume or
cancel the real work. Work done in a background thread must only change
what is_done() / progress() report; the manager polls them on the main
thread every frame.
"""
import itertools
from abc import ABC, abstractmethod
from typing import Optional

PENDING, RUNNING, PAUSED, DONE, ABORTED = 'pending', 'running', 'paused', 'done', 'aborted'
FINISHED_STATES = (DONE, ABORTED)

_ids = itertools.count(1)


class Task(ABC):
    kind = 'task'                    # registry name (see robo.tasks.catalog)

    def __init__(self, title):
        self.id = next(_ids)
        self.title = title
        self.state = PENDING
        self.result: Optional[str] = None   # short summary for Robo to tell you when done
        self._worked = 0.0          # seconds spent RUNNING before the current stretch
        self._since = None          # when the current RUNNING stretch began

    # ------------------------------------------------------------ queries
    @property
    def finished(self):
        return self.state in FINISHED_STATES

    def worked_seconds(self, now):
        """Time spent actually working (pauses don't count)."""
        extra = now - self._since if self.state == RUNNING and self._since is not None else 0.0
        return self._worked + extra

    def progress(self, now) -> Optional[float]:
        """0..1, or None if this task can't tell."""
        return None

    # ------------------------------------------------------------ lifecycle (called by the manager)
    def start(self, now):
        if self.state == PENDING:
            self.state, self._since = RUNNING, now
            self.on_start(now)

    def pause(self, now):
        if self.state == RUNNING:
            self._worked += now - self._since
            self.state, self._since = PAUSED, None
            self.on_pause(now)

    def resume(self, now):
        if self.state == PAUSED:
            self.state, self._since = RUNNING, now
            self.on_resume(now)

    def abort(self, now):
        if not self.finished:
            if self.state == RUNNING:
                self._worked += now - self._since
            self.state, self._since = ABORTED, None
            self.on_abort(now)

    def poll(self, now):
        """Returns True the moment the task completes."""
        if self.state == RUNNING and self.is_done(now):
            self._worked += now - self._since
            self.state, self._since = DONE, None
            self.on_done(now)
            return True
        return False

    # ------------------------------------------------------------ for subclasses
    @abstractmethod
    def is_done(self, now) -> bool:
        """Has the work finished? Only asked while RUNNING."""

    def on_start(self, now): pass
    def on_pause(self, now): pass
    def on_resume(self, now): pass
    def on_abort(self, now): pass
    def on_done(self, now): pass

    def __repr__(self):
        return f'<{type(self).__name__} #{self.id} {self.title!r} {self.state}>'
