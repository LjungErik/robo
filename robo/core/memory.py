"""Memory: what Robo remembers about you, across days.

A small JSON file on your computer (~/.local/share/robo/memory.json on Linux).
Nothing in it leaves your computer, except that when you chat with an AI brain
he tells it what he remembers about you, so it can talk like a friend who knows
you. You can see and erase it in Settings → Personality, ask him "what do you
remember about me?" / "forget everything", or edit the file by hand.

    name            what to call you
    facts           short things you told him ("likes pizza", "has a cat named Mo")
    tasks           the last few tasks he did for you
    first_met / last_seen / days_together / chats    how long you've known each other
    affection       0..1, grows slowly the more you two get along (see mind.py)
"""
import json
import logging
import os
import time
from datetime import date

log = logging.getLogger(__name__)

MAX_FACTS = 40
MAX_FACT_CHARS = 160
MAX_TASKS = 10
SAVE_EVERY = 60.0         # seconds between saves of slowly changing things (affection)


class Memory:
    def __init__(self, path=None, enabled=True, clock=time.time, today=date.today):
        self.path = path
        self.enabled = enabled
        self.clock = clock
        self.today = today
        self.name = ''
        self.facts = []               # [{'text': ..., 'when': 'YYYY-MM-DD'}]
        self.tasks = []               # [{'title': ..., 'result': ..., 'when': ...}]
        self.first_met = ''
        self.last_seen = ''
        self.days_together = 0
        self.chats = 0
        self.affection = 0.3
        self._dirty_since = None
        self.load()

    # ------------------------------------------------------------ file
    def load(self):
        if not self.path:
            return
        try:
            with open(self.path, encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            return
        except (OSError, ValueError) as e:
            log.warning('could not read %s (%s); starting with a blank memory', self.path, e)
            return
        if not isinstance(data, dict):
            return
        self.name = str(data.get('name') or '')[:40]
        self.facts = [f for f in data.get('facts') or () if isinstance(f, dict) and f.get('text')]
        self.facts = self.facts[-MAX_FACTS:]
        self.tasks = [t for t in data.get('tasks') or () if isinstance(t, dict)][-MAX_TASKS:]
        self.first_met = str(data.get('first_met') or '')
        self.last_seen = str(data.get('last_seen') or '')
        self.days_together = int(data.get('days_together') or 0)
        self.chats = int(data.get('chats') or 0)
        try:
            self.affection = min(1.0, max(0.0, float(data.get('affection', self.affection))))
        except (TypeError, ValueError):
            pass

    def save(self):
        self._dirty_since = None
        if not self.path or not self.enabled:
            return
        data = dict(name=self.name, facts=self.facts, tasks=self.tasks, first_met=self.first_met,
                    last_seen=self.last_seen, days_together=self.days_together,
                    chats=self.chats, affection=round(self.affection, 3))
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.write('\n')
            os.replace(tmp, self.path)
        except OSError as e:
            log.warning('could not save memory: %s', e)

    def _changed(self, now_ok=True):
        if now_ok:
            self.save()
        elif self._dirty_since is None:
            self._dirty_since = self.clock()

    def update(self):
        """Save slowly-changing things now and then."""
        if self._dirty_since is not None and self.clock() - self._dirty_since > SAVE_EVERY:
            self.save()

    def use_file(self, path):
        """Keep the memory in this file from now on (what's in it is loaded)."""
        self.path = path
        self.load()

    # ------------------------------------------------------------ remembering
    def set_enabled(self, enabled):
        self.enabled = enabled

    def remember_name(self, name):
        name = ' '.join(str(name).split())[:40].strip(' .,!?')
        if not name or not self.enabled:
            return False
        self.name = name[:1].upper() + name[1:]
        self._changed()
        return True

    def remember(self, fact):
        """Keep a short fact about you. Returns True if it was new."""
        fact = ' '.join(str(fact).split())[:MAX_FACT_CHARS].strip()
        if not fact or not self.enabled:
            return False
        low = fact.lower()
        for f in self.facts:
            if f['text'].lower() == low:
                return False
        self.facts.append({'text': fact, 'when': self.today().isoformat()})
        del self.facts[:-MAX_FACTS]
        self._changed()
        return True

    def remember_task(self, title, result):
        if not self.enabled:
            return
        self.tasks.append({'title': str(title)[:120], 'result': str(result or '')[:200],
                           'when': self.today().isoformat()})
        del self.tasks[:-MAX_TASKS]
        self._changed()

    def forget(self, what='all'):
        """Forget everything, or the facts that mention `what`. Returns how much."""
        if what == 'all':
            n = len(self.facts) + len(self.tasks) + (1 if self.name else 0)
            self.name, self.facts, self.tasks = '', [], []
            self.affection = 0.3
            self.first_met = self.last_seen = ''
            self.days_together = self.chats = 0
        else:
            low = str(what).lower()
            before = len(self.facts)
            self.facts = [f for f in self.facts if low not in f['text'].lower()]
            n = before - len(self.facts)
            if self.name and low in self.name.lower():
                self.name, n = '', n + 1
        self.save()
        return n

    def forget_fact(self, index):
        if 0 <= index < len(self.facts):
            del self.facts[index]
            self.save()

    # ------------------------------------------------------------ the relationship
    def saw_you(self):
        """You're at the computer. Returns 'first' (ever), 'new_day' or None."""
        if not self.enabled:
            return None
        today = self.today().isoformat()
        if self.last_seen == today:
            return None
        first = not self.first_met
        if first:
            self.first_met = today
        self.last_seen = today
        self.days_together += 1
        self._changed()
        return 'first' if first else 'new_day'

    def chatted(self):
        if self.enabled:
            self.chats += 1
            self._changed(now_ok=False)

    def warm(self, amount):
        """Affection changes slowly over many days."""
        if self.enabled:
            self.affection = min(1.0, max(0.0, self.affection + amount))
            self._changed(now_ok=False)

    # ------------------------------------------------------------ telling the AI
    def summary(self, max_facts=25):
        """A few lines for the AI brain: who you are to him."""
        if not self.enabled:
            return ''
        bits = []
        if self.name:
            bits.append(f"the user's name is {self.name}")
        if self.days_together > 1:
            bits.append(f"you've spent {self.days_together} days together")
        if self.facts:
            bits.append('you remember: ' + '; '.join(f['text'] for f in self.facts[-max_facts:]))
        if self.tasks:
            t = self.tasks[-1]
            bits.append(f"the last task you did for them: {t['title']} ({t['when']})")
        bond = ('you are close friends' if self.affection > 0.75 else
                'you are good friends' if self.affection > 0.5 else
                'you are still getting to know each other')
        bits.append(bond)
        return '; '.join(bits)

    def describe(self):
        """For "what do you remember about me?" (spoken)."""
        if not self.enabled:
            return "My memory is switched off, so I don't keep anything about you."
        bits = []
        if self.name:
            bits.append(f'your name is {self.name}')
        bits += [f['text'] for f in self.facts[-6:]]
        if not bits:
            return "I don't remember anything about you yet. Tell me about yourself!"
        more = f' And {len(self.facts) - 6} more things.' if len(self.facts) > 6 else ''
        return 'I remember that ' + ', '.join(bits[:-1]) + \
            (' and ' if len(bits) > 1 else '') + bits[-1] + '.' + more
