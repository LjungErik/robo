"""Initiative: when Robo speaks up on his own, and about what.

He notices you (through the idle monitor: when you're at the keyboard / mouse)
and now and then says something without being asked:

    first_meeting  the very first time ever: says hi and asks your name
    morning        your first time at the computer today (before noon)
    welcome_back   you were away for a while and came back
    break          you've been at it for a long time without a break
    late           it's late at night and you're still up
    bored          he's bored: nobody paid him any attention for a long time
    remark/question  a small thought, a fun fact, or a question to get to know you

Politeness rules: nothing at all when chattiness is off, never during quiet
hours, never while a video / presentation keeps the screen awake, never while
you're talking to him, while a bubble is up, while he's evil, working on a task
or asleep, and never two things close together (the gap depends on chattiness).
What he says comes from the AI brain if there is one, otherwise from the
`personality.lines` of the character he is (see robo/characters/README.md).
"""
import time
from datetime import datetime

AWAY_SECONDS = 5 * 60          # no input this long = you stepped away
WELCOME_AFTER = 10 * 60        # say welcome back after a break at least this long
NEW_DAY_AFTER = 4 * 3600       # a gap this long counts as the start of a new day
LATE_HOUR = 23
CHATTY_GAP = {'off': None, 'rarely': 60 * 60, 'sometimes': 25 * 60, 'often': 10 * 60}
GREETING_GAP = 5 * 60          # greetings may come sooner than chatter
CHANCE_PER_MINUTE = {'rarely': 0.05, 'sometimes': 0.12, 'often': 0.25}


def in_quiet_hours(spec, hour):
    """spec 'off' or 'HH-HH' (e.g. '22-8', wrapping past midnight)."""
    if not spec or spec == 'off':
        return False
    try:
        start, end = (int(x) for x in spec.split('-'))
    except ValueError:
        return False
    return start <= hour < end if start < end else (hour >= start or hour < end)


class Initiative:
    def __init__(self, rng, now_dt=datetime.now):
        self.rng = rng
        self.now_dt = now_dt              # wall clock (for the time of day)
        self.last_spoke = -1e9
        self.pending = []                 # (kind, info) things that just happened
        self._away = False
        self._active_since = None         # when you sat down this time
        self._last_input = None           # wall time of your last input
        self._break_said = False
        self._late_said_on = None
        self._next_roll = 0.0

    # ------------------------------------------------------------ you
    def on_idle(self, idle_seconds, now, memory=None):
        """Fed by the idle monitor (seconds since your last keyboard / mouse input)."""
        wall = time.time()
        if idle_seconds >= AWAY_SECONDS:
            if not self._away:
                self._away = True
            self._active_since = None
            return
        if self._last_input is not None and self._away:
            gap = wall - idle_seconds - self._last_input
        else:
            gap = 0.0
        if self._away or self._active_since is None:
            self._away = False
            self._active_since = now - idle_seconds
            self._break_said = False
            seen = memory.saw_you() if memory is not None else None
            hour = self.now_dt().hour
            if seen == 'first':
                self.pending.append(('first_meeting', {}))
            elif (seen == 'new_day' or gap >= NEW_DAY_AFTER) and 5 <= hour < 12:
                self.pending.append(('morning', {}))
            elif gap >= WELCOME_AFTER:
                self.pending.append(('welcome_back', {'minutes': int(gap // 60)}))
        self._last_input = wall - idle_seconds

    def working_minutes(self, now):
        return 0 if self._active_since is None else int((now - self._active_since) // 60)

    # ------------------------------------------------------------ deciding
    def choose(self, robot, now):
        """What to say now, as (kind, info), or None. Called every second or so."""
        s = robot.settings
        gap = CHATTY_GAP.get(s.chattiness)
        if gap is None:
            self.pending.clear()
            return None
        hour = self.now_dt().hour
        if not self._may_speak(robot, now, hour):
            return None
        mind = robot.mind
        # things that just happened come first
        while self.pending:
            kind, info = self.pending.pop(0)
            if now - self.last_spoke >= GREETING_GAP or kind == 'first_meeting':
                return self._said(kind, info, now)
        if now - self.last_spoke < gap:
            return None
        if s.break_reminders and not self._break_said and \
                self.working_minutes(now) >= s.break_after / 60:
            self._break_said = True
            return self._said('break', {'minutes': self.working_minutes(now)}, now)
        today = self.now_dt().date()
        if hour >= LATE_HOUR and self._late_said_on != today and mind.user_here:
            self._late_said_on = today
            return self._said('late', {'time': self.now_dt().strftime('%H:%M')}, now)
        if now < self._next_roll:
            return None
        self._next_roll = now + 60                       # roll the dice once a minute
        if not mind.user_here:
            return None
        if mind.bored and self.rng.random() < 0.5:
            return self._said('bored', {}, now)
        if self.rng.random() < CHANCE_PER_MINUTE.get(s.chattiness, 0):
            kind = 'question' if self.rng.random() < 0.4 else 'remark'
            return self._said(kind, {}, now)
        return None

    def _may_speak(self, robot, now, hour):
        if in_quiet_hours(robot.settings.quiet_hours, hour):
            return False
        if robot.evil.is_inhibited():                    # a video / presentation is on
            return False
        return not (robot.conversation.active or robot.bubbles.busy or robot.evil.active
                    or robot.busy_working or robot.body.state == 'sleep' or robot.body.held
                    or robot.wardrobe.changing(now))

    def _said(self, kind, info, now):
        self.last_spoke = now
        return kind, info


# ---------------------------------------------------------------- what to say
SITUATIONS = {
    'first_meeting': 'This is the very first time you meet the user. Say hi, introduce '
                     'yourself in one sentence and ask their name.',
    'morning': 'The user just sat down at the computer for the first time today. Greet them '
               'for the morning.',
    'welcome_back': 'The user just came back after about {minutes} minutes away. Welcome '
                    'them back.',
    'break': 'The user has been working for {minutes} minutes without a break. Gently '
             'suggest a short break (stretch, water, look out of the window).',
    'late': "It's {time} and the user is still at the computer. Say something caring about "
            "how late it is.",
    'bored': "You're bored: nobody has paid attention to you for a long time. Playfully ask "
             'for a little attention.',
    'remark': 'Make a small spontaneous remark: a thought, a fun fact, or something about '
              'your day. Keep it light.',
    'question': 'Ask the user one friendly question to get to know them better (about '
                "something you don't know yet).",
}
LISTENS_AFTER = frozenset({'first_meeting', 'question', 'bored', 'welcome_back', 'morning'})


def fill(line, name):
    """'Good morning{, name}!' -> 'Good morning, Erik!' (or 'Good morning!')."""
    import re

    def sub(m):
        return f'{m.group(1)}{name}' if name else ''
    line = re.sub(r'\{([^{}]*)name\}', sub, line)
    return ' '.join(line.split())


def line_for(kind, personality, name, rng, info=None):
    lines = (personality.get('lines') or {}).get(kind)
    if not lines:
        return None
    text = fill(rng.choice(lines), name)
    for k, v in (info or {}).items():
        text = text.replace('{' + k + '}', str(v))
    return text
