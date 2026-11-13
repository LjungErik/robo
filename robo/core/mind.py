"""Mind: how Robo feels, and what he needs, changing through the day.

    energy     1 = wide awake .. 0 = can't keep his eyes open. Follows the time
               of day (low at night, high in the day), drains while he's busy,
               comes back with naps.
    happiness  1 = over the moon .. 0 = sad. Pats, chats, compliments and
               finished tasks lift it; being ignored, insulted or yanked around
               lowers it. It drifts back to his normal self (higher the closer
               you two are).
    boredom    0 = entertained .. 1 = bored stiff. Grows while you're at the
               computer but don't pay him any attention; anything you do with
               him, a task, or one of his hobbies brings it down.

Long-term affection lives in Memory (it lasts across days). Mind only decides
how he feels; what he does about it is in personality.py / initiative.py.
"""
import math
from datetime import datetime

ENERGY_FOLLOW = 1 / 3600      # per second: energy drifts toward the time-of-day level
HAPPY_RELAX = 1 / 1800        # per second: happiness drifts back to normal
BORED_RISE = 1 / 2400         # per second while you're here but ignoring him (~40 min)
BORED_FALL = 1 / 300          # per second while something is going on
AWAY_SECONDS = 60             # no keyboard / mouse for this long = you're away


def daylight_energy(hour):
    """How awake he is at this hour (0..1): up at 7, best mid-morning, sleepy after 22."""
    if 7 <= hour < 21:
        return 0.8 + 0.2 * math.sin((hour - 7) / 14 * math.pi)
    if 21 <= hour < 24:
        return 0.8 - (hour - 21) / 3 * 0.55        # 0.8 at 21:00 .. 0.25 at midnight
    if hour < 5:
        return 0.15
    return 0.15 + (hour - 5) / 2 * 0.65            # waking up 5..7


class Mind:
    def __init__(self, memory=None, hour=None, rng=None):
        self.memory = memory
        self._hour = hour or (lambda: _local_hour())
        self.rng = rng
        self.energy = daylight_energy(self._hour())
        self.happiness = self.normal_happiness
        self.boredom = 0.1
        self.user_here = True
        self.grabs = []               # recent times he was picked up

    # ------------------------------------------------------------ what's normal
    @property
    def affection(self):
        return self.memory.affection if self.memory is not None else 0.3

    @property
    def normal_happiness(self):
        return 0.55 + 0.25 * self.affection

    # ------------------------------------------------------------ feelings
    @property
    def tired(self):
        return self.energy < 0.4

    @property
    def sleepy(self):
        return self.energy < 0.25

    @property
    def bored(self):
        return self.boredom > 0.7

    @property
    def cheerful(self):
        return self.happiness > 0.78

    @property
    def down(self):
        return self.happiness < 0.35

    def eyelids(self):
        """How far his eyes open when nothing else is going on (tired = droopy)."""
        return 1.0 if self.energy > 0.5 else 0.55 + 0.9 * self.energy

    def walk_factor(self):
        return (0.65 + 0.5 * self.energy) * (1.1 if self.cheerful else 0.9 if self.down else 1)

    def feeling(self):
        """A few words for the AI brain."""
        words = []
        if self.sleepy:
            words.append('very sleepy')
        elif self.tired:
            words.append('a bit tired')
        elif self.energy > 0.85:
            words.append('full of energy')
        if self.cheerful:
            words.append('really happy')
        elif self.down:
            words.append('a little sad')
        if self.bored:
            words.append('bored and wanting some attention')
        return ', '.join(words) or 'fine'

    def grab_reaction(self, now):
        """Picked up: 'giggle' (fun!), 'grumpy' (put me down) or 'surprised'."""
        recent = [g for g in self.grabs if now - g < 120]
        if self.tired or len(recent) > 3 or self.down:
            return 'grumpy'
        if self.cheerful or self.affection > 0.6:
            return 'giggle'
        return 'surprised'

    # ------------------------------------------------------------ things that happen
    def nudge(self, happiness=0.0, boredom=0.0, energy=0.0, affection=0.0):
        self.happiness = _clamp(self.happiness + happiness)
        self.boredom = _clamp(self.boredom + boredom)
        self.energy = _clamp(self.energy + energy)
        if affection and self.memory is not None:
            self.memory.warm(affection)

    def patted(self):
        self.nudge(happiness=0.08, boredom=-0.3, affection=0.004)

    def chatted(self):
        self.nudge(happiness=0.05, boredom=-0.5, affection=0.006)

    def complimented(self):
        self.nudge(happiness=0.15, affection=0.01)

    def insulted(self):
        self.nudge(happiness=-0.25, affection=-0.01)

    def task_done(self):
        self.nudge(happiness=0.1, boredom=-0.4, energy=-0.05, affection=0.01)

    def grabbed(self, now):
        self.grabs = [g for g in self.grabs if now - g < 120] + [now]
        mood = self.grab_reaction(now)
        self.nudge(happiness={'grumpy': -0.07, 'giggle': 0.03}.get(mood, 0.0), boredom=-0.2)
        return mood

    def napped(self, seconds):
        self.nudge(energy=min(0.4, seconds / 150))

    # ------------------------------------------------------------ time passing
    def update(self, dt, busy=False, entertained=False, idle_seconds=None):
        """busy: working / talking. entertained: something nice is going on (a hobby)."""
        if idle_seconds is not None:
            self.user_here = idle_seconds < AWAY_SECONDS
        target = daylight_energy(self._hour())
        self.energy += (target - self.energy) * min(1.0, dt * ENERGY_FOLLOW)
        if busy:
            self.energy -= dt / 36000            # a long task makes him a bit tired
        self.energy = _clamp(self.energy)
        self.happiness += (self.normal_happiness - self.happiness) * min(1.0, dt * HAPPY_RELAX)
        if busy or entertained:
            self.boredom -= dt * BORED_FALL
        elif self.user_here:
            self.boredom += dt * BORED_RISE
        else:
            self.boredom -= dt * BORED_RISE      # nobody here: nothing to want
        self.boredom = _clamp(self.boredom)
        if self.bored and self.user_here:
            self.happiness = _clamp(self.happiness - dt / 7200)   # being ignored stings


def _clamp(x):
    return min(1.0, max(0.0, x))


def _local_hour():
    now = datetime.now()
    return now.hour + now.minute / 60
