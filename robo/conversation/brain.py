"""The Brain interface: everything a conversation engine has to provide."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional, Tuple

# Things a Reply can ask the robot to do (see robo.core.personality.on_reply).
ACTIONS = ('dance', 'dress_up', 'undress', 'nap', 'wave', 'cheer', 'hearts', 'laugh',
           'start_task',   # action_arg: task kind (robo.tasks.TASK_KINDS), None = default
           'abort_task')   # action_arg: 'all' to abandon every task, else just the current one


@dataclass(frozen=True)
class Reply:
    text: str                        # what he says out loud
    mood: str = 'happy'              # face while talking: happy, normal, surprised, sad,
                                     #   sing, focus, cat, roar, laugh
    icon: Optional[str] = None       # bubble icon shown while he talks (e.g. 'heart')
    action: Optional[str] = None     # one of ACTIONS
    action_arg: Optional[str] = None  # e.g. the character for 'dress_up'
    end: bool = False                # end the conversation after saying this


@dataclass(frozen=True)
class Context:
    """What the brain may know about the world when answering."""
    now: datetime = field(default_factory=datetime.now)
    battery: Optional[Tuple[int, bool]] = None    # (percent, charging)
    costume: Optional[str] = None                 # current character id
    evil: bool = False
    characters: Tuple[str, ...] = ()              # characters he may become
    turn: int = 0                                 # how many things the user said so far
    task: Optional[str] = None                    # title of the task he's working on
    task_progress: Optional[float] = None         # 0..1 if known
    tasks_waiting: int = 0                        # tasks queued up after the current one
    tasks_unavailable: Optional[str] = None       # why he can't do tasks safely here


class Brain(ABC):
    @abstractmethod
    def greeting(self, ctx: Context) -> Reply:
        """First thing he says when a conversation starts."""

    @abstractmethod
    def respond(self, heard: str, ctx: Context) -> Reply:
        """Answer to what the user said."""

    @abstractmethod
    def farewell(self, ctx: Context) -> Reply:
        """What he says when the user stopped talking to him (should end=True)."""

    def ask(self, heard: str, ctx: Context, on_reply: Callable[[Reply], None]) -> None:
        """Asynchronous entry point used by the conversation.

        The default answers immediately. A slow brain (an LLM) should
        override this, work in the background and call on_reply(reply) on
        the main thread when done; Robo shows a "thinking" bubble meanwhile.
        """
        on_reply(self.respond(heard, ctx))
