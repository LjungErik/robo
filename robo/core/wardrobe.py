"""Wardrobe: when Robo dresses up, who as, and his signature moves.

Every `every_seconds` (randomised) he vanishes in a puff of smoke and
comes back as a character he picked himself (robo.core.outfits decides who;
without a choice it's a random one). He stays dressed up until he is clicked.
Clothes are swapped halfway through the poof so the change is hidden.
"""
from . import characters

POOF_SECONDS = 0.7
RANDOM_SPREAD = (0.6, 1.4)       # actual wait = every_seconds * uniform(spread)


class Wardrobe:
    def __init__(self, every_seconds, now, rng, allowed=None):
        self.every = every_seconds
        self.rng = rng
        self.allowed = tuple(allowed) if allowed is not None else characters.costume_ids()
        self.current = None          # Character or None
        self.last_id = None
        self.poof_start = -10.0
        self._swap_to = None         # Character, or False for "back to normal"
        self._swap_at = None
        self.move_start = -10.0
        self.move_until = 0.0
        self.choice = None           # outfits.Choice if he picked it himself
        self.dressed_at = 0.0
        self.next_change = now + self._wait()

    def _wait(self):
        return self.every * self.rng.uniform(*RANDOM_SPREAD)

    # ------------------------------------------------------------ queries
    @property
    def enabled(self):
        return self.every > 0 and bool(self.allowed)

    def changing(self, now):
        return self._swap_at is not None or now - self.poof_start < POOF_SECONDS

    def due(self, now):
        """Time to dress up on his own?"""
        return (self.enabled and self.current is None and not self.changing(now)
                and now >= self.next_change)

    def poof(self, now):
        """Progress of the smoke puff (0..1), or None."""
        k = (now - self.poof_start) / POOF_SECONDS
        return k if 0 <= k < 1 else None

    def doing_move(self, now):
        return self.current is not None and now < self.move_until

    # ------------------------------------------------------------ actions
    def configure(self, every_seconds, allowed, now):
        """Change settings live (restarts the countdown if the interval changed)."""
        if every_seconds != self.every:
            self.every = every_seconds
            self.next_change = now + self._wait()
        self.allowed = tuple(allowed)

    def dress_up(self, now, character_id=None, exclude=(), choice=None):
        """Poof into a character (random one from `allowed` if none given).
        Returns False if there is no such character."""
        known = characters.costume_ids()
        if character_id is None:
            pool = [c for c in self.allowed if c in known] or list(known)  # menu works even if none ticked
            pool = [c for c in pool if c not in exclude] or pool
            if not pool:
                return False
            choices = [c for c in pool if c != self.last_id] or pool
            character_id = self.rng.choice(choices)
        character = characters.get(character_id)
        if character is None or character.role != 'costume':
            return False
        self.choice = choice
        self._begin_poof(now, character)
        return True

    def undress(self, now):
        if self.current is not None:
            self._begin_poof(now, False)

    def clear(self, now):
        """Take the costume off instantly, no poof (another outfit covers the change)."""
        self.current = None
        self._swap_to = self._swap_at = None
        self.stop_move()
        self.next_change = now + self._wait()

    def _begin_poof(self, now, target):
        self.poof_start = now
        self._swap_to = target
        self._swap_at = now + POOF_SECONDS / 2
        self.stop_move()

    def start_move(self, now):
        if self.current is not None:
            self.move_start = now
            self.move_until = now + self.move_seconds

    @property
    def move_seconds(self):
        move = self.current.move if self.current else None
        return move.seconds if move else 0.0

    def refresh(self):
        """The character files were reloaded: pick up the new version of his costume."""
        if self.current is not None:
            self.current = characters.get(self.current.id) or self.current

    def stop_move(self):
        self.move_until = 0.0

    def update(self, now):
        """Returns 'dressed' or 'undressed' at the moment the clothes swap."""
        if self._swap_at is None or now < self._swap_at:
            return None
        target, self._swap_to, self._swap_at = self._swap_to, None, None
        if target:
            self.current = target
            self.last_id = target.id
            self.dressed_at = now
            return 'dressed'
        self.current = None
        self.choice = None
        self.next_change = now + self._wait()
        return 'undressed'
