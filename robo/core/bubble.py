"""The speech bubble queue: one icon at a time, duplicates merged."""
from dataclasses import dataclass
from typing import Optional

from robo.events import FALLBACK_KIND, KINDS, SYSTEM_KINDS

from .characters import DEMAND_ICONS

DEFAULT_SECONDS = 6.0
POP_IN, POP_OUT = 0.35, 0.22     # animation times
GAP = 0.35                       # pause between two bubbles
DEDUP_SECONDS = 60
MAX_QUEUE = 10
BUBBLE_KINDS = frozenset(KINDS) | DEMAND_ICONS   # every icon a bubble can show


def ease_out_back(x):
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


@dataclass
class Bubble:
    kind: str
    count: int = 1
    duration: float = DEFAULT_SECONDS
    start: float = 0.0
    until: float = 0.0
    hide: Optional[float] = None     # time it started closing

    @property
    def closing(self):
        return self.hide is not None

    def age(self, now):
        return now - self.start

    def scale(self, now):
        """Pop-in / pop-out animation size, 0..~1.1."""
        if self.closing:
            s = max(0.0, 1 - (now - self.hide) / POP_OUT)
            return s * s
        return ease_out_back(min(1.0, (now - self.start) / POP_IN))


class BubbleQueue:
    def __init__(self):
        self.current: Optional[Bubble] = None
        self.pending = []
        self.next_show_at = 0.0
        self._last_seen = {}

    @property
    def visible(self):
        return self.current is not None

    @property
    def open(self):
        """Visible and not closing."""
        return self.current is not None and not self.current.closing

    @property
    def busy(self):
        return self.current is not None or bool(self.pending)

    def push(self, kind, now, duration=DEFAULT_SECONDS, dedup=True, limit=MAX_QUEUE):
        """Queue an icon. Returns 'queued', 'bumped' (count +1 on the open
        bubble), 'merged' (count +1 on a waiting one) or 'ignored'."""
        if kind not in BUBBLE_KINDS:
            kind = FALLBACK_KIND
        if dedup and kind in SYSTEM_KINDS:
            if now - self._last_seen.get(kind, -1e9) < DEDUP_SECONDS:
                return 'ignored'
        self._last_seen[kind] = now
        cur = self.current
        if cur and cur.kind == kind and not cur.closing:
            cur.count += 1
            cur.until = now + cur.duration
            return 'bumped'
        for b in self.pending:
            if b.kind == kind:
                b.count += 1
                return 'merged'
        if len(self.pending) >= limit:
            return 'ignored'
        self.pending.append(Bubble(kind, duration=duration))
        return 'queued'

    def dismiss(self, now):
        if self.open:
            self.current.hide = now

    def discard(self, kinds, now):
        """Drop any queued or open bubble showing one of `kinds`."""
        self.pending = [b for b in self.pending if b.kind not in kinds]
        if self.current and self.current.kind in kinds:
            self.dismiss(now)

    def update(self, now):
        """Advance timers. Returns the Bubble that just appeared, if any."""
        cur = self.current
        if cur:
            if not cur.closing and now > cur.until:
                cur.hide = now
            if cur.closing and now - cur.hide > POP_OUT:
                self.current = None
                self.next_show_at = now + GAP
            return None
        if self.pending and now >= self.next_show_at:
            b = self.pending.pop(0)
            b.start, b.until = now, now + b.duration
            self.current = b
            return b
        return None
