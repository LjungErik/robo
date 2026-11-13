"""Approver: asking you before a task gets anything.

A platform shows these questions however suits it (Linux: GTK dialogs in
robo/platform/linux/approval.py). on_answer(True / False) must be called
on the main thread. Without a way to ask, the answer is always no.
"""
from abc import ABC, abstractmethod
from typing import Callable, List


class Approver(ABC):
    @abstractmethod
    def ask_permissions(self, title: str, lines: List[str],
                        on_answer: Callable[[bool], None]) -> None:
        """May the task `title` have these permissions?"""

    @abstractmethod
    def review_changes(self, title: str, lines: List[str],
                       on_answer: Callable[[bool], None]) -> None:
        """The task changed these files (in its copies). Apply the changes?"""


    def ask_task(self, agent_name: str, on_answer: Callable[[dict], None]) -> bool:
        """Optional: ask you for a task in a form (what to do, which files he may
        read / change). Calls on_answer({'goal', 'read', 'write'}) or never (cancel).
        Returns False if this platform can't show such a form."""
        return False


class DenyAll(Approver):
    def ask_permissions(self, title, lines, on_answer):
        on_answer(False)

    def review_changes(self, title, lines, on_answer):
        on_answer(False)
