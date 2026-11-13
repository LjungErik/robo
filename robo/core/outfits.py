"""Outfits: Robo decides what he wants to wear, and learns what he likes.

When it's time to dress up he doesn't pick at random any more. Every outfit
he's allowed to wear gets a score, and he picks one by weighted chance (so
he can still surprise you):

    situation   what's going on right now: the time of day, the season or a
                holiday, how he feels, and what you're doing (music playing,
                a meeting coming up...). A character file lists the situations
                it suits with `wear: [night, music]` (see SITUATIONS below and
                robo/characters/README.md).
    taste       his own taste. Every outfit starts with a small built-in
                liking (the same on every computer, so he has favourites from
                day one) and it changes with how things go while he wears it:
                chats and compliments make him like it more, being clicked out
                of it after a few seconds makes him like it less.

The taste is kept in a small JSON file (~/.local/share/robo/outfits.json on
Linux). It's about him, not you, so it's kept even with "Remember things
about me" switched off.
"""
import json
import logging
import math
import os
import zlib

log = logging.getLogger(__name__)

# situation -> how he'd say it ("I'm the astronaut because <it's the middle of the night>")
SITUATIONS = {
    # the time of day / week
    'morning': "it's a fresh new morning",
    'lunch': "it's lunchtime",
    'afternoon': "it's the afternoon",
    'evening': "it's evening",
    'night': "it's the middle of the night",
    'monday': "it's Monday",
    'friday': "it's Friday",
    'weekend': "it's the weekend",
    # seasons and holidays
    'spring': "it's spring",
    'summer': "it's summer",
    'autumn': "it's autumn",
    'winter': "it's winter",
    'halloween': "Halloween is coming",
    'christmas': "it's nearly Christmas",
    'new_year': "it's New Year",
    'valentine': "it's Valentine's Day",
    # how he feels
    'happy': "I'm in a great mood",
    'sad': 'I need cheering up',
    'bored': "I'm bored",
    'tired': "I'm a bit sleepy",
    # what you're doing
    'music': "there's music on",
    'mail': "you've got mail",
    'chat': "people are messaging you",
    'meeting': 'you have something on your calendar',
    'fixing': 'the computer needs updating',
    'working': "you've been working hard",
    'back': "you're back",
    'video': "we're watching something",
}

# what just happened (event kinds, robo.events) -> a situation, for RECENT_SECONDS
EVENT_SITUATIONS = {'music': 'music', 'mail': 'mail', 'chat': 'chat', 'calendar': 'meeting',
                    'alarm': 'meeting', 'update': 'fixing', 'reboot': 'fixing'}
RECENT_SECONDS = 15 * 60
WORKING_MINUTES = 60          # at the computer this long without a break = working hard

SITUATION_WEIGHT = 1.2        # per matching situation (up to MAX_MATCHES)
MAX_MATCHES = 2
TASTE_WEIGHT = 1.6            # taste goes from -1 to 1
INNATE = 0.35                 # how far the built-in liking goes (either way)

# how his taste changes while he wears something
CHATTED = 0.08
PRAISED = 0.25
PROUD = 0.5                   # he just designed it himself
HURT = -0.2
ASKED_FOR = 0.1               # you asked for it: if you like it, he likes it a bit too
WORN_LONG = 0.05              # kept it on for a while
WORN_LONG_SECONDS = 180
CLICKED_OFF = -0.25           # you clicked him out of it right away
CLICKED_OFF_SECONDS = 20
FAVOURITE = 0.35              # taste above this: one of his favourites


def innate_taste(cid):
    """A stable small liking for each outfit, from its id (-INNATE..INNATE)."""
    return (zlib.crc32(cid.encode('utf-8')) % 1000 / 999 * 2 - 1) * INNATE


class Taste:
    def __init__(self, path=None):
        self.path = path
        self.scores = {}              # outfit id -> -1..1 (missing: innate_taste)
        self.worn = {}                # outfit id -> times worn
        self.last_design = 0.0        # wall-clock time he last started designing an outfit
        self.load()

    def load(self):
        if not self.path:
            return
        try:
            with open(self.path, encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            return
        except (OSError, ValueError) as e:
            log.warning('could not read %s (%s): starting with fresh taste', self.path, e)
            return
        if not isinstance(data, dict):
            return
        try:
            self.last_design = float(data.get('last_design') or 0.0)
        except (TypeError, ValueError):
            pass
        for key, target in (('scores', self.scores), ('worn', self.worn)):
            for cid, v in (data.get(key) or {}).items():
                try:
                    target[str(cid)] = float(v) if key == 'scores' else int(v)
                except (TypeError, ValueError):
                    continue

    def use_file(self, path):
        self.path = path
        self.load()

    def save(self):
        if not self.path:
            return
        data = {'scores': {k: round(v, 3) for k, v in sorted(self.scores.items())},
                'worn': dict(sorted(self.worn.items())), 'last_design': self.last_design}
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
                f.write('\n')
            os.replace(tmp, self.path)
        except OSError as e:
            log.warning('could not save outfit taste: %s', e)

    # ------------------------------------------------------------ taste
    def of(self, cid):
        return self.scores.get(cid, innate_taste(cid))

    def nudge(self, cid, amount):
        if not cid:
            return
        self.scores[cid] = min(1.0, max(-1.0, self.of(cid) + amount))
        self.save()

    def wore(self, cid):
        self.worn[cid] = self.worn.get(cid, 0) + 1
        self.save()

    def took_off(self, cid, seconds, clicked):
        """He stopped wearing it after `seconds` (`clicked`: you clicked him out of it)."""
        if clicked and seconds < CLICKED_OFF_SECONDS:
            self.nudge(cid, CLICKED_OFF)
        elif seconds >= WORN_LONG_SECONDS:
            self.nudge(cid, WORN_LONG)

    def favourites(self, ids, n=3):
        liked = sorted((c for c in ids if self.of(c) > FAVOURITE), key=self.of, reverse=True)
        return liked[:n]


# ---------------------------------------------------------------- what's going on
def calendar_situations(dt):
    tags = set()
    h = dt.hour
    tags.add('morning' if 5 <= h < 11 else 'lunch' if h < 14 else 'afternoon' if h < 18
             else 'evening' if h < 22 else 'night')
    if h < 5:
        tags.discard('morning')
        tags.add('night')
    wd = dt.weekday()
    if wd == 0:
        tags.add('monday')
    elif wd == 4:
        tags.add('friday')
    elif wd >= 5:
        tags.add('weekend')
    m, d = dt.month, dt.day
    tags.add('winter' if m in (12, 1, 2) else 'spring' if m in (3, 4, 5)
             else 'summer' if m in (6, 7, 8) else 'autumn')
    if m == 10 and d >= 20 or m == 11 and d == 1:
        tags.add('halloween')
    if m == 12 and d <= 26:
        tags.add('christmas')
    if m == 12 and d == 31 or m == 1 and d == 1:
        tags.add('new_year')
    if m == 2 and d == 14:
        tags.add('valentine')
    return tags


def situations(robot, now):
    """Everything that's true right now, as SITUATIONS keys."""
    tags = calendar_situations(robot.initiative.now_dt())
    mind = robot.mind
    if mind.down:
        tags.add('sad')
    elif mind.cheerful:
        tags.add('happy')
    if mind.bored:
        tags.add('bored')
    if mind.tired:
        tags.add('tired')
    for kind, when in robot.recent_events.items():
        tag = EVENT_SITUATIONS.get(kind)
        if tag and now - when < RECENT_SECONDS:
            tags.add(tag)
    if robot.initiative.working_minutes(now) >= WORKING_MINUTES:
        tags.add('working')
    back = robot.initiative.came_back_at
    if back is not None and now - back < RECENT_SECONDS:
        tags.add('back')
    if robot.evil.is_inhibited():
        tags.add('video')
    return tags


# ---------------------------------------------------------------- choosing
class Choice:
    def __init__(self, cid, reason='', why='whim', announce=''):
        self.id = cid
        self.reason = reason          # a SITUATIONS key ('' = none)
        self.why = why                # 'situation', 'favourite', 'new' (he just made it) or 'whim'
        self.announce = announce      # what to say when he's in it ('' = the usual)

    @property
    def because(self):
        """Why, in words ('' if it was just a whim)."""
        if self.why == 'situation':
            return SITUATIONS.get(self.reason, '')
        if self.why == 'favourite':
            return "it's one of my favourites"
        if self.why == 'new':
            return 'I designed it myself'
        return ''

    def __repr__(self):
        return f'Choice({self.id!r}, {self.reason!r}, {self.why!r})'


def score(character, tags, taste):
    """(score, the situations it matched)"""
    matched = [t for t in character.wear if t in tags]
    s = SITUATION_WEIGHT * min(len(matched), MAX_MATCHES) + TASTE_WEIGHT * taste.of(character.id)
    return s, matched


def choose(candidates, tags, taste, rng, exclude=(), avoid=()):
    """Pick an outfit from `candidates` (Characters), never one in `exclude`, and
    one in `avoid` (what he just wore) only if there's nothing else. A Choice or None."""
    pool = [c for c in candidates if c.id not in exclude]
    pool = [c for c in pool if c.id not in avoid] or pool
    if not pool:
        return None
    scored = [(c, *score(c, tags, taste)) for c in pool]
    best = max(s for _c, s, _m in scored)
    weights = [math.exp(s - best) for _c, s, _m in scored]
    pick = rng.uniform(0, sum(weights))
    for (c, _s, matched), w in zip(scored, weights):
        pick -= w
        if pick <= 0:
            break
    if matched:
        return Choice(c.id, rng.choice(sorted(matched)), 'situation')
    if taste.of(c.id) > FAVOURITE:
        return Choice(c.id, '', 'favourite')
    return Choice(c.id)
