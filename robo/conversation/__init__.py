"""What Robo says. A Brain turns what he heard into a Reply.

    brain.py   the Brain interface, Reply and Context
    rules.py   RuleBrain: a simple keyword "switch statement"

To plug in an LLM later: subclass Brain, override ask() to answer
asynchronously, and pass it to Companion.conversation.attach().
"""
from .brain import Brain, Context, Reply  # noqa: F401
from .rules import RuleBrain  # noqa: F401
