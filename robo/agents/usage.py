"""Usage: how many tokens Robo's AI brain has used, kept day by day.

Every answer Claude Code gives (a chat line, a line he says on his own, a
task, an outfit design) ends with a result that says exactly how many tokens
it took and what that would cost on the API. Robo adds those up here, per
day and per kind of use, in a small JSON file (~/.local/share/robo/usage.json
on Linux). Nothing is sent anywhere.

How much of your *plan* is used comes separately: with stream-json output
Claude Code also prints a rate_limit_event, with how full each of your
plan's windows is (the 5-hour session, the week, and sometimes the week for
one model). Robo keeps the latest one (record_limits) and shows it as
progress bars. He also remembers the last time he ran into the limit, and
what Claude said about it ("resets 6pm").

    LEDGER.record(kind, usage)   kind: 'chat', 'speak_up', 'task', 'design'
    LEDGER.record_limits(info)   Claude Code's rate_limit_info
    LEDGER.plan_windows()        [PlanWindow('Session (5 hours)', 0.12, resets_at), ...]
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


@dataclass(frozen=True)
class PlanWindow:
    """One of your plan's usage windows, as Claude Code last reported it."""
    key: str                         # 'five_hour', 'seven_day', 'seven_day_opus', ...
    label: str                       # 'Session (5 hours)'
    used: float                      # 0..1
    resets_at: Optional[float] = None    # epoch seconds
    status: str = ''                 # 'allowed', 'allowed_warning', 'rejected'


# the windows worth showing, in order; per-model weeks are added when Claude reports them
WINDOW_LABELS = {'five_hour': 'Session (5 hours)', 'seven_day': 'This week (all models)'}
MODEL_FAMILIES = ('opus', 'sonnet', 'haiku', 'fable')


def window_label(key):
    if key in WINDOW_LABELS:
        return WINDOW_LABELS[key]
    family = key[len('seven_day_'):] if key.startswith('seven_day_') else ''
    return f'This week ({family.capitalize()})' if family in MODEL_FAMILIES else None


def pretty_model(model):
    """'claude-haiku-5-5' -> 'Haiku 5.5', 'claude-sonnet-4-5-20250929' -> 'Sonnet 4.5'."""
    model = str(model or '').strip()
    if not model or model == '?':
        return ''
    parts = [p for p in model.replace('_', '-').split('-') if p]
    if parts and parts[0].lower() == 'claude':
        parts = parts[1:]
    parts = [p for p in parts if not (p.isdigit() and len(p) >= 6)]      # date stamps
    names = [p for p in parts if not p.isdigit()]
    version = '.'.join(p for p in parts if p.isdigit())
    if not names:
        return model
    return ' '.join(n.capitalize() for n in names) + (f' {version}' if version else '')


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
        self.plan = None              # {'when': epoch, 'windows': {key: {...}}}: rate_limit_info
        self.last_model = ''          # the model that answered last
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
            plan = data.get('plan')
            self.plan = plan if isinstance(plan, dict) and isinstance(
                plan.get('windows'), dict) else None
            self.last_model = str(data.get('last_model') or '')

    def _save(self):
        if not self.path:
            return
        data = {'days': self.days, 'models': self.models, 'limit': self.limit,
                'plan': self.plan, 'last_model': self.last_model}
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
            if usage.model:
                self.last_model = usage.model
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

    def record_limits(self, info):
        """Claude Code's rate_limit_info: how full your plan's windows are."""
        if not isinstance(info, dict):
            return
        windows = {}
        for key, w in (info.get('unifiedWindows') or {}).items():
            used = _fraction(w.get('utilization')) if isinstance(w, dict) else None
            if used is not None:
                windows[str(key)] = {'used': used, 'resets_at': _number(w.get('resetsAt')),
                                     'status': str(w.get('status') or '')}
        top = info.get('rateLimitType')               # older shape: only the one window
        used = _fraction(info.get('utilization'))
        if top and used is not None and top not in windows:
            windows[str(top)] = {'used': used, 'resets_at': _number(info.get('resetsAt')),
                                 'status': str(info.get('status') or '')}
        if not windows:
            return
        with self._lock:
            self.plan = {'when': self.clock(), 'windows': windows}
            self._save()

    def plan_windows(self):
        """[PlanWindow] for the bars, session first. A window whose reset time has
        passed shows as empty again. [] until Claude has reported something."""
        with self._lock:
            plan = self.plan
        if not plan:
            return []
        now = self.clock()
        out = []
        for key, w in plan['windows'].items():
            label = window_label(key)
            if label is None:
                continue
            resets = w.get('resets_at')
            used = 0.0 if resets and resets <= now else float(w.get('used') or 0.0)
            out.append(PlanWindow(key, label, max(0.0, min(1.0, used)),
                                  resets if resets and resets > now else None,
                                  str(w.get('status') or '')))
        order = list(WINDOW_LABELS)
        out.sort(key=lambda w: (order.index(w.key) if w.key in order else len(order), w.key))
        return out

    def window_for_model(self, model):
        """The week window just for `model` ('opus', 'claude-opus-5-5'...), if Claude
        reports one; else None."""
        low = str(model or '').lower()
        for w in self.plan_windows():
            family = w.key[len('seven_day_'):] if w.key.startswith('seven_day_') else ''
            if family and family in low:
                return w
        return None

    def plan_checked_at(self):
        with self._lock:
            return self.plan['when'] if self.plan else None

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
        windows = {w.key: w for w in self.plan_windows()}
        if limit:
            when = time.strftime('%H:%M', time.localtime(limit['when']))
            bits.append(f'I ran into the plan limit at {when}. Claude said: {limit["message"]}')
        elif windows:
            said = [f'{round(w.used * 100)} percent of {name}' for key, name in
                    (('five_hour', 'this session'), ('seven_day', 'this week'))
                    if (w := windows.get(key)) is not None]
            if said:
                bits.append(f"Of your Claude plan I've used {_join(said)}.")
        else:
            bits.append("I don't know how much of your plan is left yet, but I'll "
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


def _fraction(v):
    """utilization: 0..1 (Claude Code's own), or a percentage just in case."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    if v != v or v < 0:                               # NaN / nonsense
        return None
    return v / 100 if v > 1.5 else min(v, 1.0)


def _number(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def resets_in_words(resets_at, now=None):
    """'resets in 2 h 10 min' / 'resets Mon 14:00' (None -> '')."""
    if not resets_at:
        return ''
    now = time.time() if now is None else now
    left = resets_at - now
    if left <= 0:
        return ''
    if left < 3600:
        return f'resets in {max(1, round(left / 60))} min'
    if left < 24 * 3600:
        h, m = int(left // 3600), int(left % 3600 // 60)
        return f'resets in {h} h {m} min' if m else f'resets in {h} h'
    return 'resets ' + time.strftime('%a %H:%M', time.localtime(resets_at))


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
