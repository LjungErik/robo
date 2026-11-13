"""Tasks: work you ask Robo to do. Pure logic, no robot or OS code.

    base.py      Task and its lifecycle (start / pause / resume / abort / done)
    manager.py   TaskManager: running tasks, the queue, interruptions
    sandboxed.py SandboxedTask: the work runs in a sandboxed worker (robo.sandbox)
    catalog.py   the kinds of task he knows (only a placeholder for now)

The Companion owns a TaskManager, pauses it while you talk to him or hold
him, and dresses him as a hacker (robo.core.hacker) while it is busy.
"""
from .base import Task  # noqa: F401
from .catalog import TASK_KINDS, TimerTask, make_task  # noqa: F401
from .sandboxed import SandboxedTask, TaskEnvironment  # noqa: F401
from .manager import TaskManager  # noqa: F401
