"""Hacker mode: how Robo looks while he has a task.

He puts on his 80s hacker outfit (poof) as soon as he has work, sits down
at his laptop and types while a task runs, stands up (laptop under his
arm) while he is interrupted, and changes back once every task is done.
This is not a dress-up character: it never comes up at random and its
outfit lives in robo/characters/hacker.yaml (role: work).
"""
from .wardrobe import POOF_SECONDS

OUTFIT = 'hacker'
SIT_SECONDS = 0.35        # sitting down / standing up


class HackerMode:
    def __init__(self):
        self.dressed = False
        self.sit = 0.0               # 0 standing .. 1 sitting at the laptop
        self.poof_start = -10.0
        self._swap_to = None         # True / False while a poof is playing
        self._swap_at = None

    # ------------------------------------------------------------ queries
    @property
    def active(self):
        """In (or changing into) the hacker outfit."""
        return self.dressed if self._swap_at is None else bool(self._swap_to)

    @property
    def typing(self):
        return self.dressed and self.sit >= 0.99

    def changing(self, now):
        return self._swap_at is not None or now - self.poof_start < POOF_SECONDS

    def poof(self, now):
        k = (now - self.poof_start) / POOF_SECONDS
        return k if 0 <= k < 1 else None

    # ------------------------------------------------------------ per frame
    def update(self, now, dt, has_work, can_sit):
        """has_work: wear the outfit. can_sit: a task is running and he's on the
        ground, so sit and type. Returns 'dressed' / 'undressed' at the swap."""
        change = None
        if has_work != self.active:
            self.poof_start = now
            self._swap_to, self._swap_at = has_work, now + POOF_SECONDS / 2
        if self._swap_at is not None and now >= self._swap_at:
            self.dressed, self._swap_to, self._swap_at = self._swap_to, None, None
            change = 'dressed' if self.dressed else 'undressed'
        target = 1.0 if self.dressed and can_sit and not self.changing(now) else 0.0
        step = dt / SIT_SECONDS
        self.sit = min(target, self.sit + step) if target > self.sit else max(target, self.sit - step)
        return change
