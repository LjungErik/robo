"""What Robo says. A Brain turns what he heard into a Reply.

    brain.py   the Brain interface, Reply and Context
    rules.py   RuleBrain: a simple keyword "switch statement"
    agent.py   AgentBrain: RuleBrain for commands + an AI agent (robo.agents) for the rest

Another brain: subclass Brain, override ask() to answer asynchronously,
and pass it to Companion.conversation.attach().
"""
from .brain import Brain, Context, Reply  # noqa: F401
from .rules import RuleBrain  # noqa: F401
from .agent import AgentBrain  # noqa: F401
