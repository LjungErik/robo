"""TaskManager: which tasks run now, which wait in line, and interruptions.

    submit() ──► queue ──(free slot)──► running ──► done / aborted
                                          │
                       pause reasons ─────┘  (e.g. 'conversation', 'held')

* `max_parallel` tasks run at the same time (1 for now); the rest wait in
  the queue, first come first served.
* Anything may interrupt the work by adding a pause reason; work resumes
  once every reason is gone. Time spent paused doesn't count.
* Everything that happens is recorded as an event (`'started'`, `'paused'`,
  `'resumed'`, `'finished'`, `'aborted'`) and handed out by update(), so the
  robot can react to it in one place.
"""
from .base import PAUSED, RUNNING

STARTED, PAUSED_EV, RESUMED, FINISHED, ABORTED_EV = (
    'started', 'paused', 'resumed', 'finished', 'aborted')


class TaskManager:
    def __init__(self, max_parallel=1):
        self.max_parallel = max_parallel
        self.running = []           # Tasks that started (RUNNING or PAUSED)
        self.queued = []            # Tasks waiting for a free slot
        self._pause_reasons = set()
        self._events = []

    # ------------------------------------------------------------ queries
    @property
    def busy(self):
        """Has anything to do (running, paused or waiting)."""
        return bool(self.running or self.queued)

    @property
    def working(self):
        """Is actually working right now (not interrupted)."""
        return any(t.state == RUNNING for t in self.running)

    @property
    def paused(self):
        return bool(self._pause_reasons)

    @property
    def current(self):
        """The task he'd tell you about first, or None."""
        return self.running[0] if self.running else None

    def all_tasks(self):
        return self.running + self.queued

    # ------------------------------------------------------------ control
    def submit(self, task, now):
        """Add a task. Returns 'started' or 'queued'."""
        self.queued.append(task)
        self._fill_slots(now)
        return STARTED if task in self.running else 'queued'

    def abort(self, now, task_id=None):
        """Abandon one task (default: the current one). Returns what was aborted."""
        if task_id is None:
            targets = self.running[:1] or self.queued[:1]
        else:
            targets = [t for t in self.all_tasks() if t.id == task_id]
        for t in targets:
            self._abort(t, now)
        self._fill_slots(now)
        return targets

    def abort_all(self, now):
        targets = self.all_tasks()
        for t in targets:
            self._abort(t, now)
        return targets

    def set_paused(self, reason, paused, now):
        """Interrupt (or stop interrupting) the work for `reason`."""
        was = self.paused
        if paused:
            self._pause_reasons.add(reason)
        else:
            self._pause_reasons.discard(reason)
        if self.paused == was:
            return
        for t in self.running:
            if self.paused:
                t.pause(now)
                self._events.append((PAUSED_EV, t))
            else:
                t.resume(now)
                self._events.append((RESUMED, t))

    # ------------------------------------------------------------ per frame
    def update(self, now):
        """Poll the running tasks. Returns the events since the last call."""
        for t in list(self.running):
            if t.poll(now):
                self.running.remove(t)
                self._events.append((FINISHED, t))
        self._fill_slots(now)
        events, self._events = self._events, []
        return events

    # ------------------------------------------------------------ internals
    def _abort(self, task, now):
        task.abort(now)
        if task in self.running:
            self.running.remove(task)
        if task in self.queued:
            self.queued.remove(task)
        self._events.append((ABORTED_EV, task))

    def _fill_slots(self, now):
        while self.queued and len(self.running) < self.max_parallel:
            t = self.queued.pop(0)
            t.start(now)
            if self.paused:
                t.pause(now)
            self.running.append(t)
            self._events.append((STARTED, t))
