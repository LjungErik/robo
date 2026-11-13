"""Usage: how many tokens Robo's AI brain has used, kept day by day.

Every answer Claude Code gives (a chat line, a line he says on his own, a
task, an outfit design) ends with a result that says exactly how many tokens
it took and what that would cost on the API. Robo adds those up here, per
day and per kind of use, in a small JSON file (~/.local/share/robo/usage.json
on Linux). Nothing is sent anywhere.

What is *left* of your plan isn't something Claude Code tells him, so he
can't say that. He does remember the last time he ran into the limit, and
what Claude said about it ("resets 6pm").

    LEDGER.record(kind, usage)   kind: 'chat', 'speak_up', 'task', 'design'
    LEDGER.day() / .week()       totals
    LEDGER.spoken()              "Today I used about 12 thousand tokens..."
"""
import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

log = logging.getLogger(__name__)

KEEP_DAYS = 60
KINDS = ('chat', 'speak_up', 'task', 'design')
KIND_WORDS = {'chat': ('chat', 'chats'), 'speak_up': ('thing I said on my own',
                                                      'things I said on my own'),
              'task': ('task', 'tasks'), 'design': ('outfit design', 'outfit designs')}


@dataclass(frozen=True)
class Usage:
    """One answer's worth. `input` counts every token he sent, cached or not."""
    input: int = 0
    output: int = 0
    cache_read: int = 0              # part of `input` that was read from Claude's cache
    cost: float = 0.0                # what it would cost on the API, in US dollars
    model: str = ''

    @property
    def total(self):
        return self.input + self.output


def from_claude(data) -> Optional[Usage]:
    """The `result` object Claude Code prints (json / stream-json) -> Usage."""
    if not isinstance(data, dict):
        return None
    u = data.get('usage')
    if not isinstance(u, dict):
        return None
    try:
        fresh = int(u.get('input_tokens') or 0)
        written = int(u.get('cache_creation_input_tokens') or 0)
        read = int(u.get('cache_read_input_tokens') or 0)
        out = int(u.get('output_tokens') or 0)
        cost = float(data.get('total_cost_usd') or 0.0)
    except (TypeError, ValueError):
        return None
    models = data.get('modelUsage')
    model = max(models, key=lambda m: (models[m] or {}).get('costUSD') or 0) \
        if isinstance(models, dict) and models else ''
    return Usage(fresh + written + read, out, read, cost, str(model))


def _empty():
    return {'calls': 0, 'input': 0, 'output': 0, 'cost': 0.0}


class Ledger:
    def __init__(self, path=None, today=date.today, clock=time.time):
        self.path = path
        self.today = today
        self.clock = clock
        self.days = {}                # 'YYYY-MM-DD' -> kind -> totals
        self.models = {}              # model -> totals (all time)
        self.limit = None             # {'when': epoch, 'message': ...}: the last time he hit it
        self._lock = threading.Lock()
        self.load()

    # ------------------------------------------------------------ file
    def use_file(self, path):
        self.path = path
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
            log.warning('could not read %s (%s): starting a fresh usage log', self.path, e)
            return
        if not isinstance(data, dict):
            return
        with self._lock:
            self.days = {d: {k: {**_empty(), **v} for k, v in kinds.items() if isinstance(v, dict)}
                         for d, kinds in (data.get('days') or {}).items()
                         if isinstance(kinds, dict)}
            self.models = {m: {**_empty(), **v} for m, v in (data.get('models') or {}).items()
                           if isinstance(v, dict)}
            limit = data.get('limit')
            self.limit = limit if isinstance(limit, dict) and 'when' in limit else None

    def _save(self):
        if not self.path:
            return
        data = {'days': self.days, 'models': self.models, 'limit': self.limit}
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=1, sort_keys=True)
                f.write('\n')
            os.replace(tmp, self.path)
        except OSError as e:
            log.warning('could not save the usage log: %s', e)

    # ------------------------------------------------------------ recording (any thread)
    def record(self, kind, usage):
        if usage is None:
            return
        kind = kind if kind in KINDS else 'chat'
        with self._lock:
            day = self.today().isoformat()
            for bucket in (self.days.setdefault(day, {}).setdefault(kind, _empty()),
                           self.models.setdefault(usage.model or '?', _empty())):
                bucket['calls'] += 1
                bucket['input'] += usage.input
                bucket['output'] += usage.output
                bucket['cost'] = round(bucket['cost'] + usage.cost, 6)
            cutoff = (self.today() - timedelta(days=KEEP_DAYS)).isoformat()
            for d in [d for d in self.days if d < cutoff]:
                del self.days[d]
            self._save()
        log.info('usage: %s %d in / %d out tokens ($%.4f API value)', kind, usage.input,
                 usage.output, usage.cost)

    def hit_limit(self, message):
        """Claude said he's used up the plan's limit for now."""
        with self._lock:
            self.limit = {'when': self.clock(), 'message': ' '.join(str(message).split())[:200]}
            self._save()

    # ------------------------------------------------------------ totals
    def totals(self, days=1):
        """kind -> totals over the last `days` days (1 = today), plus 'all'."""
        first = (self.today() - timedelta(days=days - 1)).isoformat()
        out = {k: _empty() for k in KINDS + ('all',)}
        with self._lock:
            for d, kinds in self.days.items():
                if d < first:
                    continue
                for k, t in kinds.items():
                    for bucket in (out.setdefault(k, _empty()), out['all']):
                        for field in ('calls', 'input', 'output'):
                            bucket[field] += t[field]
                        bucket['cost'] += t['cost']
        return out

    def day(self):
        return self.totals(1)

    def week(self):
        return self.totals(7)

    def tokens_today(self):
        t = self.day()['all']
        return t['input'] + t['output']

    def recent_limit(self, within=12 * 3600):
        if self.limit and self.clock() - self.limit['when'] < within:
            return self.limit
        return None

    # ------------------------------------------------------------ in words
    def spoken(self):
        """What he says when you ask how many tokens he used."""
        today, week = self.day(), self.week()
        if not week['all']['calls']:
            return "I haven't used any of my AI brain's tokens yet. All my answers so far " \
                   'came from my own little rule book!'
        bits = []
        if today['all']['calls']:
            what = [_count(today[k]['calls'], *KIND_WORDS[k]) for k in KINDS if today[k]['calls']]
            bits.append(f"Today I've used about {_tokens(_sum(today['all']))} tokens, "
                        f'for {_join(what)}. That would be about '
                        f"{_money(today['all']['cost'])} on the API.")
        else:
            bits.append("I haven't used any tokens today.")
        if week['all']['calls'] > today['all']['calls']:
            bits.append(f"This week it's about {_tokens(_sum(week['all']))} tokens.")
        limit = self.recent_limit()
        if limit:
            when = time.strftime('%H:%M', time.localtime(limit['when']))
            bits.append(f'I ran into the plan limit at {when}. Claude said: {limit["message"]}')
        else:
            bits.append("Claude doesn't tell me how much of your plan is left, but I'll "
                        'tell you if I run out.')
        return ' '.join(bits)

    def lines(self):
        """For the settings window: a few short lines."""
        out = []
        for title, t in (('Today', self.day()), ('Last 7 days', self.week())):
            a = t['all']
            if not a['calls']:
                out.append(f'{title}: nothing yet')
                continue
            parts = [f'{t[k]["calls"]} {KIND_WORDS[k][0 if t[k]["calls"] == 1 else 1]}'
                     for k in KINDS if t[k]['calls']]
            out.append(f'{title}: {_short(a["input"])} in, {_short(a["output"])} out '
                       f'(≈ ${a["cost"]:.2f} API value) · {", ".join(parts)}')
        limit = self.recent_limit(7 * 86400)
        if limit:
            when = time.strftime('%a %H:%M', time.localtime(limit['when']))
            out.append(f'Last hit the plan limit {when}: {limit["message"]}')
        return out


def _sum(t):
    return t['input'] + t['output']


def _tokens(n):
    if n < 1000:
        return str(n)
    if n < 1_000_000:
        return f'{round(n / 1000)} thousand'
    return f'{n / 1_000_000:.1f} million'


def _short(n):
    return f'{n / 1_000_000:.1f}M' if n >= 1_000_000 else f'{n / 1000:.1f}k' if n >= 1000 \
        else str(n)


def _money(usd):
    if usd < 0.01:
        return 'less than a cent'
    if usd < 1:
        return f'{round(usd * 100)} cents'
    return f'{usd:.2f} dollars'


def _count(n, one, many):
    return f'{n} {one if n == 1 else many}'


def _join(items):
    return items[0] if len(items) == 1 else ', '.join(items[:-1]) + ' and ' + items[-1]


LEDGER = Ledger()                    # the app gives it a file
