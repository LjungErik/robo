"""User settings, and a description of each one for the settings window.

Settings come from (lowest to highest priority): the defaults below, the
settings file (robo/settings_store.py), then any command-line flags.
FIELDS describes every user-editable setting, so a settings window on any
platform can be generated from it.
"""
from dataclasses import asdict, dataclass, field, fields as dc_fields, replace
from typing import Callable, Optional, Tuple

from robo.agents import BACKENDS, OFF
from robo.core import characters

# Characters that existed before settings files recorded "known_characters".
# Anything not known when a file was saved is new, and starts switched on.
LEGACY_KNOWN_CHARACTERS = ('pharaoh', 'cowboy', 'viking', 'accountant', 'mechanic', 'roman')
ALL = ('*',)                          # "every character there is", including ones added later


def all_characters():
    """Every dress-up character (from the character files)."""
    return characters.costume_ids()


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
    characters: Tuple[str, ...] = ALL   # who he may dress up as
    look: str = 'robo'                  # what he looks like normally (a base design or character)
    design_outfits: bool = False        # designs new outfits for himself now and then (AI brain)
    design_every: float = 3 * 86400     # ...about this often
    voice: bool = True                  # speak answers out loud
    voice_pitch: float = 75.0           # 0..99, higher = squeakier
    voice_speed: float = 1.0            # speaking speed multiplier
    voice_volume: float = 0.8           # 0..1
    robot_effect: bool = False          # use the beepy robot voice even when nice
    wake_word: bool = False             # keep listening for "Hey Robo"
    chattiness: str = 'sometimes'       # how often he speaks up on his own: off/rarely/sometimes/often
    break_reminders: bool = True        # suggest a break after a long stretch of work
    break_after: float = 90 * 60        # ...this long without a break
    quiet_hours: str = 'off'            # no chatter in these hours, e.g. '22-8'
    remember_me: bool = True            # keep a memory of you (name, things you told him)
    agent: str = OFF                    # AI brain: 'off', 'claude', 'codex' or 'gemini'
    agent_model: str = ''               # model for chatting ('' = the agent CLI's own default)
    task_model: str = ''                # model for tasks and outfit designs ('' = its default)
    daily_budget: str = 'off'           # tokens a day for things he does on his own
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
            elif f.kind in ('bool', 'memory', 'designs'):
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
        known = all_characters()
        if tuple(chars) == ALL:
            put('characters', known)
        else:
            wanted = set(chars)
            put('characters', tuple(c for c in known if c in wanted))
        put('agent', self.agent if self.agent in BACKENDS else OFF)
        for f in FIELDS:
            if f.kind == 'choice' and f.key != 'agent' and \
                    getattr(self, f.key) not in [v for v, _l in f.choices]:
                put(f.key, getattr(Settings, f.key))
        put('agent_model', str(self.agent_model or '').strip())
        put('task_model', str(self.task_model or '').strip())
        look = str(self.look or characters.DEFAULT_LOOK)
        put('look', look if look in characters.look_ids() else characters.DEFAULT_LOOK)

    # ------------------------------------------------------------ helpers
    @property
    def effective_evil_after(self):
        """Seconds before turning evil, 0 when evil mode is off."""
        return self.evil_after if self.evil_mode else 0.0

    @property
    def budget_tokens(self):
        """Tokens a day for his own ideas, or None for no limit."""
        return None if self.daily_budget == 'off' else int(self.daily_budget)

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
        d['known_characters'] = list(all_characters())
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
                    seen = data.get('known_characters', LEGACY_KNOWN_CHARACTERS)
                    new = [c for c in all_characters() if c not in set(seen)]
                    changes[key] = tuple(chosen) + tuple(new)
            elif key in ('look', 'agent', 'agent_model', 'task_model', 'chattiness',
                         'quiet_hours', 'daily_budget'):
                changes[key] = str(value)
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
    kind: str                         # 'float', 'seconds' (pick from options), 'bool',
                                      # 'characters' (pick several), 'look' (pick one),
                                      # 'choice' (one of `choices`), 'model' (one of the
                                      # AI brain's MODELS), 'designs' (bool + his
                                      # own outfits), 'memory' (bool + the
                                      # list of what he remembers)
    help: str = ''
    min: float = 0.0
    max: float = 1.0
    step: float = 0.1
    options: Tuple[float, ...] = ()
    depends: Optional[str] = None     # only editable while this bool setting is on
    choices: Tuple[Tuple[str, str], ...] = ()   # 'choice': (value, label) pairs
    fmt: Callable[[float], str] = field(default=lambda v: f'{v:g}', compare=False)


SECTIONS = (
    # id, title, emoji
    ('robo', 'Robo', '🤖'),
    ('look', 'Everyday look', '👀'),
    ('bubbles', 'Speech bubbles', '💬'),
    ('evil', 'Evil mode', '😈'),
    ('dress', 'Dressing up', '🎭'),
    ('designs', 'His own designs', '✏️'),
    ('voice', 'Voice & talking', '🗣️'),
    ('personality', 'Personality', '💛'),
    ('brain', 'AI brain', '🧠'),
    ('advanced', 'Advanced', '🔧'),
)

TABS = (
    # id, title, emoji, the SECTIONS shown on that tab (as cards, in this order)
    ('general', 'General', '🤖', ('robo', 'bubbles', 'advanced')),
    ('characters', 'Characters', '🎭', ('look', 'dress', 'designs')),
    ('voice', 'Voice', '🗣️', ('voice',)),
    ('personality', 'Personality', '💛', ('personality', 'evil')),
    ('brain', 'AI brain', '🧠', ('brain',)),
)

FIELDS = (
    Field('scale', 'Size', 'robo', 'float', 'How big Robo is on your screen.',
          min=0.5, max=4.0, step=0.1, fmt=fmt_times),
    Field('walk_speed', 'Walking speed', 'robo', 'float', 'From leisurely stroll to zoomies.',
          min=0.3, max=3.0, step=0.1, fmt=fmt_times),
    Field('naps', 'Naps', 'robo', 'bool', 'Let him doze off now and then (zzz).'),
    Field('look', 'Look', 'look', 'look',
          'Who he is the rest of the time. Some can fly around the screen! '
          'Add your own in ~/.config/robo/characters.'),
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
    Field('design_outfits', 'Design new outfits on his own', 'designs', 'designs',
          'Now and then, when he has nothing to do, he sits down at his laptop and designs '
          'himself a brand-new outfit with the Claude AI brain (it uses your Claude account). '
          'You can always ask him: "design yourself a disco outfit". Everything he made is '
          'listed below.'),
    Field('design_every', 'At most', 'designs', 'seconds', '',
          options=(86400, 2 * 86400, 3 * 86400, 7 * 86400, 14 * 86400),
          depends='design_outfits', fmt=lambda v: 'once a day' if v <= 86400 else
          f'every {v / 86400:.0f} days'),
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
    Field('chattiness', 'Speaks up on his own', 'personality', 'choice',
          'Now and then he says hi when you come back, asks how you are, or shares a '
          'thought. Never during videos, chats or quiet hours.',
          choices=(('off', 'Never'), ('rarely', 'Rarely'), ('sometimes', 'Sometimes'),
                   ('often', 'Often'))),
    Field('break_reminders', 'Remind me to take breaks', 'personality', 'bool',
          'After a long stretch at the computer he suggests a stretch.'),
    Field('break_after', 'Break after', 'personality', 'seconds', '',
          options=(30 * 60, 45 * 60, 60 * 60, 90 * 60, 120 * 60, 180 * 60),
          depends='break_reminders', fmt=fmt_seconds),
    Field('quiet_hours', 'Quiet hours', 'personality', 'choice',
          'No chatter at all during these hours.',
          choices=(('off', 'None'), ('22-8', '22:00 to 8:00'), ('23-7', '23:00 to 7:00'),
                   ('21-9', '21:00 to 9:00'), ('18-9', '18:00 to 9:00'))),
    Field('remember_me', 'Remember things about me', 'personality', 'memory',
          'Your name and things you tell him, kept on this computer (and told to the AI '
          'brain while you chat). See and erase it below.'),
    Field('agent', 'Talk through', 'brain', 'choice',
          'Answers your questions with an AI agent, using the login of its own app '
          '(Claude Code, Codex or Gemini CLI): no API key needed, a Claude Pro account '
          'works. What you say to him is sent to that service. With Claude he can also '
          'do real tasks (right-click → Give me a task), safely sandboxed.',
          choices=(('off', 'Off (just Robo)'), ('claude', 'Claude (Claude Code)'),
                   ('codex', 'ChatGPT (Codex CLI)'), ('gemini', 'Gemini (Gemini CLI)'))),
    Field('agent_model', 'Model for chatting', 'brain', 'model',
          'Short chats don\'t need the biggest model: a lighter one answers faster and '
          'makes your plan last much longer.'),
    Field('task_model', 'Model for tasks and designs', 'brain', 'model',
          'Real tasks and outfit designs are harder: a smarter model does them better.'),
    Field('daily_budget', 'Daily budget for his own ideas', 'brain', 'choice',
          'Things he does on his own (chatting up, designing outfits) use the AI brain only '
          'until he has used this many tokens today; after that he uses his own rule book. '
          'Anything you ask him always works. The usage below counts everything.',
          choices=(('off', 'No limit'), ('25000', '25 thousand'), ('100000', '100 thousand'),
                   ('250000', '250 thousand'), ('1000000', '1 million'))),
    Field('verbose', 'Log what he sees', 'advanced', 'bool',
          'Prints notifications and decisions to the terminal.'),
)

FIELDS_BY_KEY = {f.key: f for f in FIELDS}
