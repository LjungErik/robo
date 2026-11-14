"""Approver: asking you before a task gets anything, and showing what it made.

A platform shows these questions however suits it (Linux: GTK dialogs in
robo/platform/linux/approval.py). on_answer(True / False) must be called
on the main thread. Without a way to ask, the answer is always no.

The questions come as plain lines like "Read: /home/you/notes.txt" (easy to
log and test). group_lines() turns them into titled sections for a nicer
dialog: lines with the same "Label:" end up together under one heading.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, List, Tuple


@dataclass
class Section:
    heading: str
    emoji: str = ''
    items: List[str] = field(default_factory=list)
    paths: bool = False              # the items are file / folder paths


# "Label:" at the start of a line -> (heading, emoji, items are paths)
LABELS = {          # Robo speaks for himself in his popups
    'summary': ('What I did', '💬', False),
    'do': ('What I\'ll do', '📝', False),
    'design': ('My idea', '🎨', False),
    'with': ('Who does the thinking', '🧠', False),
    'read': ('I\'d like to look at', '👀', True),
    'change (you review first)': ('I\'d like to change (you check every change first)', '✏️',
                                  True),
    'download from': ('I\'d like to download from', '🌐', False),
    'new files go to (you review first)': ('New files will be saved in', '📁', True),
    'the new outfit goes to': ('The new outfit will be saved in', '📁', True),
    'note': ('Good to know', '💡', False),
    'added': ('New files', '✨', True),
    'modified': ('Changed files', '✏️', True),
    'deleted': ('Deleted files', '🗑️', True),
}


def group_lines(lines) -> Tuple[List[Section], List[str]]:
    """['Read: a', 'Read: b', 'just a note'] -> ([Section("I'd like to look at", [a, b])],
    ['just a note']). Section order follows the first line of each label."""
    sections, notes, by_label = [], [], {}
    last = None
    for line in lines:
        line = str(line)
        if not line.strip():
            continue
        label, sep, rest = line.partition(': ')
        key = label.strip().lower()
        if sep and key in LABELS or (sep and len(label) <= 40 and '/' not in label
                                     and not label.startswith('.')):
            heading, emoji, paths = LABELS.get(key, (label.strip(), '', False))
            sec = by_label.get(key)
            if sec is None:
                sec = by_label[key] = Section(heading, emoji, [], paths)
                sections.append(sec)
            sec.items.append(rest.strip())
            last = sec
        elif line.startswith('... and ') and last is not None:
            last.items.append(line)          # "... and 12 more" belongs to the list above
        else:
            notes.append(line)
    return sections, notes


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

    def show_results(self, title: str, summary: str, files: List[str], folder: str) -> None:
        """Optional: the task is done and its files are saved. Show them, with a
        quick way to open each one and the folder they're in."""

    def open_path(self, path: str) -> bool:
        """Optional: open a file or folder in your usual app. False if it can't."""
        return False


class DenyAll(Approver):
    def ask_permissions(self, title, lines, on_answer):
        on_answer(False)

    def review_changes(self, title, lines, on_answer):
        on_answer(False)
