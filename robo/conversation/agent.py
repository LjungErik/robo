"""AgentBrain: Robo's brain with an AI agent (Claude, ChatGPT or Gemini) behind it.

Clear commands are still handled by RuleBrain, instantly and offline: dress
up, tasks, fly, nap, dance, the time, the battery, goodbye. Everything else
(questions, chit-chat, "explain black holes") goes to the agent. The agent
can also ask Robo to do things (wave, dance, dress up...) by answering with
a small JSON object; see SYSTEM_PROMPT.

The agent is a slow, blocking CLI, so it runs on a worker thread. Answers
are handed back on the main thread from update(), which the conversation
calls every frame. Hushing him (stop) cancels the request.
"""
import json
import logging
import queue
import re
import threading

from robo.agents import OFF, AgentCancelled, AgentError, make_backend
from robo.core import characters

from .brain import ACTIONS, Brain, Reply

log = logging.getLogger(__name__)

# RuleBrain topics answered locally even with an agent (fast, offline, reliable):
# always for tasks and goodbye, and for the rest when it's just the short command
# ("dress up as a pirate"), not a longer request ("...and tell me a pirate fact").
ALWAYS_LOCAL = frozenset({'abort_task', 'task_status', 'do_task', 'goodbye'})
SHORT_LOCAL = frozenset({'undress', 'dress_up', 'travel', 'dance', 'sleep', 'time', 'date',
                         'battery'})
SHORT_WORDS = 6
MOODS = ('happy', 'normal', 'surprised', 'sad', 'sing', 'focus', 'cat', 'roar', 'laugh')
AGENT_ACTIONS = ('wave', 'cheer', 'hearts', 'laugh', 'dance', 'dress_up', 'undress', 'nap',
                 'travel')
MAX_SPOKEN = 600                  # characters; he answers out loud, so keep it short
FORGET_AFTER = 30 * 60            # seconds between conversations before he starts fresh

SYSTEM_PROMPT = """\
You are Robo, a small, cute, cheerful robot who lives at the bottom of the \
user's computer screen. You are talking with the user OUT LOUD: they speak, \
speech recognition writes down what they said (it can mishear words), and \
your answer is read aloud by a text-to-speech voice.

How to answer:
- Be warm, playful and helpful. An occasional "beep" or "boop" is welcome.
- Keep it short: one to three spoken sentences, unless they ask for more.
- Plain speech only: no markdown, lists, emoji, code blocks or URLs.
- You can't see the screen, open files, browse or run anything yet. If asked \
to, say so kindly and help with what you know.

Answer with ONE JSON object and nothing else:
{"say": "what you say out loud", "mood": "<mood>", "action": "<action or null>", \
"arg": "<argument or null>"}
mood is one of: happy, normal, surprised, sad, sing, focus, cat, laugh.
action (optional) makes your body do something while you speak:
  wave, cheer, hearts, laugh, dance, nap (after the chat), undress (back to plain Robo),
  dress_up (arg = one of the characters listed in your status),
  travel (fly / hang / teleport around the screen, only if your status says you can).
Only dress_up, undress, travel or nap when the user asks you to; the others you may use whenever they fit (wave hello, laugh at a joke, hearts for a compliment)."""


def _status_line(ctx):
    bits = [ctx.now.strftime('%A %d %B %Y, %H:%M')]
    if ctx.battery:
        pct, charging = ctx.battery
        bits.append(f'battery {pct}%{" and charging" if charging else ""}')
    look = characters.title(ctx.look) if ctx.look else 'Robo'
    bits.append(f'your everyday look: {look}')
    if ctx.costume:
        bits.append(f'dressed up as: {characters.title(ctx.costume)}')
    if ctx.evil:
        bits.append('you are in your playful evil mode (mwahaha)')
    if ctx.task:
        bits.append(f'busy with a task: {ctx.task}')
    if ctx.travel:
        bits.append(f'you can travel by: {", ".join(ctx.travel)}')
    if ctx.characters:
        bits.append('characters you can dress up as: ' + ', '.join(ctx.characters))
    return '[Robo status: ' + '; '.join(bits) + ']'


_FENCE = re.compile(r'^```(?:json)?\s*|\s*```$', re.S)
_EMOJI = re.compile('[\U0001F000-\U0001FAFF☀-➿️‍]')
_MARKUP = re.compile(r'[*_#`>|]+')


def spoken(text):
    """Make agent text sound right when read aloud."""
    text = _EMOJI.sub('', text)
    text = re.sub(r'https?://\S+', 'a link', text)
    text = _MARKUP.sub('', text)
    text = re.sub(r'^\s*[-•]\s+', '', text, flags=re.M)
    text = ' '.join(text.split())
    if len(text) > MAX_SPOKEN:
        cut = text[:MAX_SPOKEN]
        end = max(cut.rfind('. '), cut.rfind('! '), cut.rfind('? '))
        text = cut[:end + 1] if end > 100 else cut.rstrip() + '...'
    return text


def parse_reply(raw, ctx):
    """The agent's answer (JSON, ideally) -> Reply. Never fails."""
    text = _FENCE.sub('', raw.strip())
    data = None
    start, end = text.find('{'), text.rfind('}')
    if start != -1 and end > start:
        try:
            data = json.loads(text[start:end + 1])
        except ValueError:
            data = None
    if not isinstance(data, dict) or not isinstance(data.get('say'), str):
        return Reply(spoken(text) or 'Beep?', 'happy')
    mood = data.get('mood') if data.get('mood') in MOODS else 'happy'
    action, arg = data.get('action'), data.get('arg')
    if action not in AGENT_ACTIONS or action not in ACTIONS:
        action, arg = None, None
    if action == 'dress_up' and (arg not in characters.costume_ids() or ctx.task):
        action, arg = None, None
    if action == 'travel' and not ctx.travel:
        action, arg = None, None
    if action == 'nap':
        return Reply(spoken(data['say']) or 'Yawn.', mood, action='nap', end=True)
    return Reply(spoken(data['say']) or 'Beep!', mood, action=action,
                 action_arg=str(arg) if arg else None)


class AgentBrain(Brain):
    """RuleBrain for commands, an AI agent for everything else (when one is set up)."""

    def __init__(self, rules, workdir):
        self.rules = rules
        self.workdir = workdir
        self.backend = None
        self.agent_id = OFF
        self._results = queue.Queue()
        self._job = 0                     # increases with every request; stale answers are dropped
        self._waiting = None              # (job, on_reply, ctx)
        self._last_talk = None

    # ------------------------------------------------------------ setup
    def configure(self, settings):
        agent, model = settings.agent, settings.agent_model
        if agent == self.agent_id and (self.backend is None or self.backend.model == model):
            return
        self.cancel()
        self.agent_id = agent
        self.backend = make_backend(agent, self.workdir, model) if agent != OFF else None
        log.info('brain: %s', self.backend.name if self.backend else 'rules only')

    @property
    def thinking(self):
        return self._waiting is not None

    # ------------------------------------------------------------ Brain
    def greeting(self, ctx):
        return self.rules.greeting(ctx)

    def farewell(self, ctx):
        return self.rules.farewell(ctx)

    def respond(self, heard, ctx):
        return self.rules.respond(heard, ctx)

    def conversation_started(self, now):
        if self.backend and self._last_talk is not None and now - self._last_talk > FORGET_AFTER:
            self.backend.forget()             # it's been a while: a fresh conversation

    def conversation_ended(self, now):
        self._last_talk = now

    def ask(self, heard, ctx, on_reply):
        if self.backend is None or self._local(heard):
            on_reply(self.rules.respond(heard, ctx))
            return
        self._job += 1
        job, backend = self._job, self.backend
        self._waiting = (job, on_reply, ctx)
        prompt = f'{_status_line(ctx)}\n{heard}'
        threading.Thread(target=self._work, args=(job, backend, prompt), daemon=True,
                         name='robo-agent').start()

    def _local(self, heard):
        topic = self.rules.topic(heard)
        if topic in ALWAYS_LOCAL:
            return True
        return topic in SHORT_LOCAL and len(heard.split()) <= SHORT_WORDS

    def _work(self, job, backend, prompt):
        try:
            answer = backend.ask(prompt, SYSTEM_PROMPT)
            self._results.put((job, answer.text, None))
        except AgentCancelled:
            self._results.put((job, None, None))
        except AgentError as e:
            log.warning('%s: %s', backend.name, e)
            self._results.put((job, None, e.spoken))
        except Exception as e:            # noqa: BLE001  (never take the robot down)
            log.exception('%s failed', backend.name)
            self._results.put((job, None, "Oops, my AI brain hiccuped. Let's try again!"))

    def update(self, now):
        """Main thread: deliver a finished answer."""
        while True:
            try:
                job, text, problem = self._results.get_nowait()
            except queue.Empty:
                return
            if self._waiting is None or job != self._waiting[0]:
                continue                      # cancelled or replaced
            _job, on_reply, ctx = self._waiting
            self._waiting = None
            if text is not None:
                on_reply(parse_reply(text, ctx))
            elif problem:
                on_reply(Reply(problem, 'sad'))

    def cancel(self):
        """Stop waiting (he was hushed, or the brain changed)."""
        self._waiting = None
        if self.backend is not None:
            threading.Thread(target=self.backend.cancel, daemon=True).start()

    def status(self):
        return self.backend.status() if self.backend else None
