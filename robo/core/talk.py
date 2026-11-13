"""Conversation: Robo listens, thinks, answers out loud, and listens again.

    IDLE ──start()──► SPEAKING (greeting) ──► LISTENING ──heard──► THINKING
      ▲                    ▲                     │                    │
      └──── end / bye ─────┴──── silence ────────┘          brain.ask()│
                           └──────────────── SPEAKING (reply) ◄────────┘

The microphone is paused while he speaks, so he never answers himself.
Voice and ears are platform objects (robo.platform.base.SpeechOutput /
SpeechInput); the brain is any robo.conversation.Brain.
"""
import logging
from datetime import datetime

from robo.agents.usage import LEDGER
from robo.conversation import Context, Reply
from robo.platform.base import SpeechOutput, Utterance

from . import personality
from .bubble import TALK_ICONS

log = logging.getLogger(__name__)

IDLE, SPEAKING, LISTENING, THINKING = 'idle', 'speaking', 'listening', 'thinking'
LISTEN_SECONDS = 7.0          # how long he waits for you to start talking
THINK_BUBBLE_DELAY = 0.15     # only show "thinking" if the brain takes a moment
MIC, THINKING_ICON = 'mic', 'thinking'      # see bubble.TALK_ICONS
EVIL_MOODS = ('laugh', 'evil')   # these lines are said in the evil voice ("mwahaha")

CANT_HEAR = Reply("I'd love to chat, but I can't hear you yet. "
                  'Run the install script to give me ears!', 'sad', end=True)


def _describe(p):
    """A character's personality as one line for the AI brain."""
    bits = []
    for key, label in (('traits', 'traits'), ('likes', 'likes'), ('dislikes', 'dislikes'),
                       ('quirks', 'quirks')):
        if p.get(key):
            bits.append(f'{label}: ' + ', '.join(p[key]))
    if p.get('speech'):
        bits.append(f"how you talk: {p['speech']}")
    return '; '.join(bits)


class SilentVoice(SpeechOutput):
    """Used when talking out loud is off (or no speech engine exists): his
    mouth still moves and the conversation keeps its rhythm."""
    WORDS_PER_SECOND = 2.6
    FRAME = 1 / 30

    def __init__(self, clock):
        self.clock = clock
        self._done_at = None
        self._on_done = None

    def say(self, text, on_started, on_done, style='normal'):
        duration = max(0.8, len(text.split()) / self.WORDS_PER_SECOND)
        frames = int(duration / self.FRAME)
        envelope = [0.55 + 0.45 * ((i // 4) % 2) if (i // 2) % 5 else 0.1 for i in range(frames)]
        on_started(Utterance(text, envelope, self.FRAME, duration))
        self._done_at, self._on_done = self.clock() + duration, on_done

    def stop(self):
        self._finish()

    def update(self, now):
        if self._done_at is not None and now >= self._done_at:
            self._finish()

    def _finish(self):
        cb, self._on_done, self._done_at = self._on_done, None, None
        if cb:
            cb()


class Conversation:
    def __init__(self, robot):
        self.robot = robot
        self.state = IDLE
        self.brain = None
        self.ears = None              # SpeechInput or None
        self.real_voice = None        # SpeechOutput or None
        self.silent_voice = SilentVoice(robot.clock)
        self.voice = self.silent_voice
        self.battery = lambda: None   # platform hook: () -> (percent, charging) or None
        self.reply = None             # Reply being spoken
        self.utterance = None
        self.turn = 0
        self._wake_word = False
        self._thinking_since = None
        self._announcements = []
        self._quiet = False

    # ------------------------------------------------------------ setup
    def attach(self, brain, voice=None, ears=None):
        self.brain = brain
        self.real_voice = voice if voice is not None and voice.available else None
        self.ears = ears
        self.configure(self.robot.settings)

    def configure(self, settings):
        """Settings changed (voice on/off, pitch, wake word...)."""
        self.voice = (self.real_voice if settings.voice and self.real_voice
                      else self.silent_voice)
        if self.real_voice:
            self.real_voice.configure(settings)
        self._wake_word = settings.wake_word
        if self.ears and self.ears.available and self.state == IDLE:
            self.ears.set_wake_word(settings.wake_word, self.on_wake_word)

    @property
    def active(self):
        return self.state != IDLE

    @property
    def can_hear(self):
        return self.ears is not None and self.ears.available

    def context(self):
        r = self.robot
        task = r.tasks.current
        now = r.clock()
        pick = r.pick_outfit(now)
        return Context(now=datetime.now(), battery=self.battery(),
                       costume=r.wardrobe.current.id if r.wardrobe.current else None,
                       evil=r.evil.active, characters=tuple(r.settings.characters),
                       look=r.look, travel=tuple(a.kind for a in r.travel.abilities(r)),
                       turn=self.turn,
                       task=task.title if task else None,
                       task_progress=task.progress(now) if task else None,
                       tasks_waiting=len(r.tasks.queued),
                       tasks_unavailable=r.task_env.unavailable_reason(),
                       agent_tasks=self._agent_tasks(),
                       task_note=getattr(task, 'note', '') if task else '',
                       user_name=r.memory.name, feeling=r.mind.feeling(),
                       memory_text=r.memory.describe(), memory_summary=r.memory.summary(),
                       remembers=r.memory.enabled, personality=_describe(r.personality()),
                       usage_text=LEDGER.spoken(),
                       outfit_choice=pick.id if pick else None,
                       outfit_because=pick.because if pick else '',
                       favourite_outfits=tuple(r.taste.favourites(
                           c.id for c in r.outfit_candidates())))

    def _agent_tasks(self):
        backend = getattr(self.brain, 'backend', None)
        return bool(backend and backend.supports_tasks
                    and not self.robot.task_env.unavailable_reason())

    # ------------------------------------------------------------ control
    def start(self, opener=None, quiet=False):
        """Start talking. `opener`: a Reply he starts with instead of his usual
        greeting (when he speaks up on his own); `quiet`: if you don't answer, he
        just stops instead of saying goodbye."""
        if self.active or self.brain is None:
            return
        now = self.robot.clock()
        log.info('conversation started')
        self.turn = 0
        self._quiet = quiet
        self.brain.conversation_started(now)
        personality.on_conversation_started(self.robot, now)
        if not self.can_hear:
            if self.ears is not None and self.ears.unavailable_reason:
                log.info('cannot listen: %s', self.ears.unavailable_reason)
            self._say(CANT_HEAR)
            return
        self.ears.prepare()           # warm up recognition while he says hello
        self._say(opener or self.brain.greeting(self.context()))

    def stop(self):
        """Hush now (e.g. he was clicked)."""
        if not self.active:
            return
        log.info('conversation stopped')
        self.reply = Reply('', end=True)
        if self.state == THINKING:
            self.brain.cancel()
        if self.ears:
            self.ears.pause()
        self.voice.stop()             # may already finish via _spoken
        if self.active:
            self._finish()

    def announce(self, text, mood='happy'):
        """Say something on his own (e.g. what a finished task did). Waits for a
        quiet moment if you're in the middle of a chat."""
        if not text:
            return
        if self.active:
            self._announcements.append((text, mood))
            return
        log.info('announcing: %s', text)
        self._say(Reply(text, mood, end=True))

    def on_wake_word(self):
        log.info('heard the wake word')
        self.start()

    # ------------------------------------------------------------ turns
    def _say(self, reply):
        now = self.robot.clock()
        self.state = SPEAKING
        self.reply = reply
        self.robot.bubbles.discard(TALK_ICONS, now)
        if reply.icon:
            self.robot.bubbles.push(reply.icon, now, duration=4.0, dedup=False, front=True)
        personality.on_reply(self.robot, reply, now)
        if self.ears:
            self.ears.pause()
        style = 'evil' if self.robot.evil.active or reply.mood in EVIL_MOODS else 'normal'
        log.info('robo says (%s voice): %s', style, reply.text)
        self.utterance = None
        self.voice.say(reply.text, self._started, self._spoken, style=style)

    def _started(self, utterance):
        utterance.started_at = self.robot.clock()
        self.utterance = utterance

    def _spoken(self):
        if self.state != SPEAKING:
            return
        self.utterance = None
        if self.reply is None or self.reply.end or not self.can_hear:
            self._finish()
        else:
            self._listen()

    def _listen(self):
        now = self.robot.clock()
        self.state = LISTENING
        self.robot.bubbles.discard({THINKING_ICON}, now)
        self.robot.bubbles.push(MIC, now, duration=LISTEN_SECONDS + 30, dedup=False, front=True)
        self.ears.listen(LISTEN_SECONDS, self._heard, self._silence, self._partial)

    def _partial(self, text):
        pass                          # the bubble's waves already show he's listening

    def _heard(self, text):
        if self.state != LISTENING:
            return
        log.info('heard: %s', text)
        self.turn += 1
        self._quiet = False                       # you answered: a real chat now
        self.state = THINKING
        self._thinking_since = self.robot.clock()
        self.robot.bubbles.discard({MIC}, self._thinking_since)
        self.brain.ask(text, self.context(), self._answer)

    def _answer(self, reply):
        if self.state == THINKING:
            self._thinking_since = None
            self._say(reply)

    def _silence(self):
        if self.state == LISTENING:
            if self._quiet:                       # he spoke up, you didn't answer: fine
                self._finish()
            else:
                self._say(self.brain.farewell(self.context()))

    def _finish(self):
        now = self.robot.clock()
        reply, self.reply = self.reply, None
        self.state = IDLE
        self.utterance = None
        self.robot.bubbles.discard(TALK_ICONS, now)
        self.brain.conversation_ended(now)
        personality.on_conversation_ended(self.robot, reply, now)
        if self.ears and self.ears.available:
            self.ears.set_wake_word(self._wake_word, self.on_wake_word)
        if self._announcements:
            text, mood = self._announcements.pop(0)
            self.announce(text, mood)

    # ------------------------------------------------------------ per frame
    def update(self, now):
        self.voice.update(now)
        if self.brain is not None:
            self.brain.update(now)
        if (self.state == THINKING and self._thinking_since is not None
                and now - self._thinking_since > THINK_BUBBLE_DELAY
                and not (self.robot.bubbles.current
                         and self.robot.bubbles.current.kind == THINKING_ICON)):
            self.robot.bubbles.push(THINKING_ICON, now, duration=60, dedup=False, front=True)

    def mouth(self, now):
        """How far his mouth is open right now (0..1)."""
        u = self.utterance
        if u is None or not u.envelope:
            return 0.0
        i = int((now - u.started_at) / u.frame_seconds)
        return u.envelope[i] if 0 <= i < len(u.envelope) else 0.0

    def shutdown(self):
        if self.ears:
            self.ears.shutdown()
        if self.real_voice:
            self.real_voice.shutdown()
