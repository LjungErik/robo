"""User settings, and a description of each one for the settings window.

Settings come from (lowest to highest priority): the defaults below, the
settings file (robo/settings_store.py), then any command-line flags.
FIELDS describes every user-editable setting, so a settings window on any
platform can be generated from it.
"""
from dataclasses import asdict, dataclass, field, fields as dc_fields, replace
from typing import Callable, Optional, Tuple

from robo.core.characters import CHARACTERS

ALL_CHARACTERS = tuple(CHARACTERS)
# Characters that existed before settings files recorded "known_characters".
# Anything not known when a file was saved is new, and starts switched on.
LEGACY_KNOWN_CHARACTERS = ('pharaoh', 'cowboy', 'viking', 'accountant', 'mechanic', 'roman')


@dataclass(frozen=True)
class Settings:
    scale: float = 1.0                  # size multiplier
    walk_speed: float = 1.0             # walking speed multiplier
    bubble_seconds: float = 6.0         # how long a notification bubble stays up
    check_updates: bool = True          # look for software updates every couple of hours
    naps: bool = True                   # allowed to take naps
    evil_mode: bool = True
    evil_after: float = 60.0            # seconds without input before turning evil
    dress_up: bool = True
    dress_up_every: float = 45.0        # about how often he dresses up as a character
    characters: Tuple[str, ...] = ALL_CHARACTERS   # who he may dress up as
    voice: bool = True                  # speak answers out loud
    voice_pitch: float = 75.0           # 0..99, higher = squeakier
    voice_speed: float = 1.0            # speaking speed multiplier
    voice_volume: float = 0.8           # 0..1
    robot_effect: bool = False          # use the beepy robot voice even when nice
    wake_word: bool = False             # keep listening for "Hey Robo"
    verbose: bool = False               # log events
    demo: bool = False                  # show every icon once at start-up (not saved)

    def __post_init__(self):
        def put(name, value):
            object.__setattr__(self, name, value)
        for f in FIELDS:
            value = getattr(self, f.key)
            if f.kind == 'float':
                put(f.key, min(max(float(value), f.min), f.max))
            elif f.kind == 'seconds':
                put(f.key, float(value))
            elif f.kind == 'bool':
                put(f.key, bool(value))
        # "--evil-after 0" / "--dress-up-every 0" mean "off"
        if self.evil_after <= 0:
            put('evil_mode', False)
            put('evil_after', Settings.evil_after)
        if self.dress_up_every <= 0:
            put('dress_up', False)
            put('dress_up_every', Settings.dress_up_every)
        put('evil_after', min(max(self.evil_after, 5.0), 3 * 3600.0))
        put('dress_up_every', min(max(self.dress_up_every, 10.0), 6 * 3600.0))
        chars = self.characters
        if isinstance(chars, str):
            chars = [c.strip() for c in chars.split(',')]
        wanted = set(chars)
        put('characters', tuple(c for c in ALL_CHARACTERS if c in wanted))

    # ------------------------------------------------------------ helpers
    @property
    def effective_evil_after(self):
        """Seconds before turning evil, 0 when evil mode is off."""
        return self.evil_after if self.evil_mode else 0.0

    @property
    def effective_dress_up_every(self):
        """Dress-up interval, 0 when dressing up is off."""
        return self.dress_up_every if self.dress_up else 0.0

    def with_changes(self, **changes):
        return replace(self, **changes)

    def to_dict(self):
        """Only the values worth saving."""
        d = asdict(self)
        d.pop('demo', None)
        d['characters'] = list(self.characters)
        d['known_characters'] = list(ALL_CHARACTERS)
        return d

    @classmethod
    def from_dict(cls, data, base=None):
        """Build Settings from a (possibly partial or messy) dict."""
        base = base or cls()
        known = {f.name for f in dc_fields(cls)} - {'demo'}
        changes = {}
        for key, value in (data or {}).items():
            if key not in known:
                continue
            if key == 'characters':
                if isinstance(value, (list, tuple, str)):
                    chosen = value.split(',') if isinstance(value, str) else list(value)
                    known = data.get('known_characters', LEGACY_KNOWN_CHARACTERS)
                    new = [c for c in ALL_CHARACTERS if c not in set(known)]
                    changes[key] = tuple(chosen) + tuple(new)
            elif isinstance(getattr(base, key), bool):
                changes[key] = bool(value)
            else:
                try:
                    changes[key] = float(value)
                except (TypeError, ValueError):
                    continue
        return replace(base, **changes)


# ---------------------------------------------------------------- schema
def fmt_times(v):
    return f'{v:.1f}×'


def fmt_seconds(v):
    v = int(round(v))
    if v < 60:
        return f'{v} s'
    if v < 3600:
        m, s = divmod(v, 60)
        return f'{m} min' if not s else f'{m} min {s} s'
    h, rest = divmod(v, 3600)
    return f'{h} h' if not rest else f'{h} h {rest // 60} min'


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    section: str
    kind: str                         # 'float', 'seconds' (pick from options), 'bool', 'characters'
    help: str = ''
    min: float = 0.0
    max: float = 1.0
    step: float = 0.1
    options: Tuple[float, ...] = ()
    depends: Optional[str] = None     # only editable while this bool setting is on
    fmt: Callable[[float], str] = field(default=lambda v: f'{v:g}', compare=False)


SECTIONS = (
    # id, title, emoji
    ('robo', 'Robo', '🤖'),
    ('bubbles', 'Speech bubbles', '💬'),
    ('evil', 'Evil mode', '😈'),
    ('dress', 'Dressing up', '🎭'),
    ('voice', 'Voice & talking', '🗣️'),
    ('advanced', 'Advanced', '🔧'),
)

FIELDS = (
    Field('scale', 'Size', 'robo', 'float', 'How big Robo is on your screen.',
          min=0.5, max=4.0, step=0.1, fmt=fmt_times),
    Field('walk_speed', 'Walking speed', 'robo', 'float', 'From leisurely stroll to zoomies.',
          min=0.3, max=3.0, step=0.1, fmt=fmt_times),
    Field('naps', 'Naps', 'robo', 'bool', 'Let him doze off now and then (zzz).'),
    Field('bubble_seconds', 'Bubble time', 'bubbles', 'float',
          'How long a notification bubble stays up.', min=2, max=20, step=1, fmt=fmt_seconds),
    Field('check_updates', 'Check for software updates', 'bubbles', 'bool',
          'Every couple of hours: apt, snap and flatpak.'),
    Field('evil_mode', 'Turn evil when I leave', 'evil', 'bool',
          'Mwahaha. He turns back as soon as you touch anything.'),
    Field('evil_after', 'Turn evil after', 'evil', 'seconds', 'Time without keyboard or mouse.',
          options=(10, 15, 20, 30, 45, 60, 90, 120, 180, 300, 600, 900, 1800, 3600),
          depends='evil_mode', fmt=fmt_seconds),
    Field('dress_up', 'Dress up as characters', 'dress', 'bool',
          'Every so often he becomes someone else. Click him to end it.'),
    Field('dress_up_every', 'Roughly every', 'dress', 'seconds',
          'The exact time is a surprise.',
          options=(15, 30, 45, 60, 120, 180, 300, 600, 900, 1800, 3600, 7200),
          depends='dress_up', fmt=fmt_seconds),
    Field('characters', 'Characters', 'dress', 'characters', 'Who he is allowed to become.',
          depends='dress_up'),
    Field('voice', 'Talk out loud', 'voice', 'bool',
          'Double-click Robo (or right-click → Talk to me) to chat.'),
    Field('voice_pitch', 'Voice pitch', 'voice', 'float', 'From deep bot to squeaky bot.',
          min=0, max=99, step=1, depends='voice', fmt=lambda v: f'{v:.0f}'),
    Field('voice_speed', 'Talking speed', 'voice', 'float', '',
          min=0.5, max=2.0, step=0.1, depends='voice', fmt=fmt_times),
    Field('voice_volume', 'Volume', 'voice', 'float', '',
          min=0.0, max=1.0, step=0.1, depends='voice', fmt=lambda v: f'{v * 100:.0f}%'),
    Field('robot_effect', 'Robotic voice', 'voice', 'bool',
          'Use the beepy robot voice all the time. Evil Robo always sounds like this.',
          depends='voice'),
    Field('wake_word', 'Listen for "Hey Robo"', 'voice', 'bool',
          'Keeps the microphone open so you can just say "Hey Robo". '
          'Everything is understood offline, on this computer.'),
    Field('verbose', 'Log what he sees', 'advanced', 'bool',
          'Prints notifications and decisions to the terminal.'),
)

FIELDS_BY_KEY = {f.key: f for f in FIELDS}
