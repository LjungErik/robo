"""The usage card: hover over Robo for a moment and he shows which AI model he's
using and how much of your plan is used, as little progress bars.

    HoverWatch   tracks the mouse over him (pointer_motion / pointer_leave) and
                 says when the card should pop up (after HOVER_SECONDS) and go
    build_card   Settings + the usage ledger -> UsageCard (what to draw)

Pure Python; robo/render/usage_card.py draws it.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from robo.agents.usage import pretty_model, resets_in_words

HOVER_SECONDS = 2.0              # keep the mouse on him this long
POP_IN, POP_OUT = 0.3, 0.2

AGENT_NAMES = {'claude': 'Claude', 'codex': 'ChatGPT', 'gemini': 'Gemini'}


@dataclass
class UsageCard:
    title: str                                        # 'Claude · Haiku 5.5'
    bars: List[Tuple[str, float, str]] = field(default_factory=list)  # (label, 0..1, detail)
    note: str = ''                                    # shown when there are no bars


def model_name(settings, ledger):
    """The model he chats with: what you picked in Settings, or (default) the one
    Claude last answered with."""
    chosen = (getattr(settings, 'agent_model', '') or '').strip()
    last = ledger.last_model if settings.agent == 'claude' else ''
    if chosen and chosen.lower() not in last.lower():
        return pretty_model(chosen) or chosen
    return pretty_model(last) or ("Claude Code's default" if settings.agent == 'claude'
                                  else 'its default model')


def build_card(settings, ledger, now=None) -> UsageCard:
    agent = getattr(settings, 'agent', 'off')
    if agent == 'off' or agent not in AGENT_NAMES:
        return UsageCard('AI brain: off', note='Just me and my rule book!')
    title = f'{AGENT_NAMES[agent]} · {model_name(settings, ledger)}'
    if agent != 'claude':
        return UsageCard(title, note="It doesn't tell me its usage")
    windows = {w.key: w for w in ledger.plan_windows()}
    bars = []
    session = windows.get('five_hour')
    if session is not None:
        bars.append(('Session', session.used, resets_in_words(session.resets_at, now)))
    week = ledger.window_for_model(model_name(settings, ledger)) or windows.get('seven_day')
    if week is not None:
        label = 'Week' if week.key == 'seven_day' else f'Week ({week.key[10:].capitalize()})'
        bars.append((label, week.used, resets_in_words(week.resets_at, now)))
    if not bars:
        return UsageCard(title, note='Usage: ask me something first!')
    return UsageCard(title, bars)


class HoverWatch:
    """Is the mouse resting on him? `update(now)` -> True while the card shows."""

    def __init__(self):
        self.since: Optional[float] = None    # when the mouse came onto him
        self.shown_at: Optional[float] = None
        self.hide_at: Optional[float] = None  # closing animation started

    def over(self, now):
        if self.since is None:
            self.since = now

    def away(self, now):
        self.since = None
        if self.shown_at is not None and self.hide_at is None:
            self.hide_at = now

    def update(self, now):
        if self.hide_at is not None and now - self.hide_at >= POP_OUT:
            self.shown_at = self.hide_at = None
        if self.since is not None and self.shown_at is None and \
                now - self.since >= HOVER_SECONDS:
            self.shown_at = now
        return self.visible

    @property
    def visible(self):
        return self.shown_at is not None

    def scale(self, now):
        """Pop-in / pop-out size, 0..1."""
        if self.shown_at is None:
            return 0.0
        if self.hide_at is not None:
            k = max(0.0, 1 - (now - self.hide_at) / POP_OUT)
            return k * k
        k = min(1.0, (now - self.shown_at) / POP_IN)
        return 1 - (1 - k) ** 3
