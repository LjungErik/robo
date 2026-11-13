"""AI agents Robo can talk through, each via the provider's own logged-in CLI
(so no API keys: a Claude Pro subscription works through Claude Code).

To add a provider: subclass AgentBackend (base.py) and add it to BACKENDS.
"""
from .base import AgentAnswer, AgentBackend, AgentCancelled, AgentError, AgentStatus  # noqa: F401
from .claude import ClaudeCode
from .codex import Codex
from .gemini import GeminiCli

BACKENDS = {b.id: b for b in (ClaudeCode, Codex, GeminiCli)}
OFF = 'off'


def make_backend(agent_id, workdir, model=''):
    cls = BACKENDS.get(agent_id)
    return cls(workdir, model=model) if cls else None
