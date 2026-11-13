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


class DenyAll(Approver):
    def ask_permissions(self, title, lines, on_answer):
        on_answer(False)

    def review_changes(self, title, lines, on_answer):
        on_answer(False)
