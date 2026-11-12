"""The contract between the robot and the operating system.

To port Robo to another OS, implement these classes (see robo/platform/linux
for a complete example and robo/platform/headless.py for a minimal one) and
register the new Platform in robo/platform/__init__.py.

Rules every implementation must follow:
  * All callbacks into the robot (listener methods, `emit`, idle callbacks,
    scheduled functions) must run on the main thread.
  * Coordinates are physical screen pixels; (0, 0) is the top-left of the
    virtual screen.
"""
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, List, Optional, Protocol

from robo.config import Settings
from robo.core.geometry import Rect
from robo.events import EventSink


# ---------------------------------------------------------------- window
@dataclass(frozen=True)
class PointerEvent:
    button: int        # 1 = left, 2 = middle, 3 = right (0 for plain motion)
    x: float           # position inside the window
    y: float
    root_x: float      # position on the screen
    root_y: float


@dataclass(frozen=True)
class MenuItem:
    label: Optional[str]                     # None = separator
    action: Optional[Callable[[], None]] = None

    @classmethod
    def separator(cls):
        return cls(None)


class WindowListener(Protocol):
    """Implemented by robo.core.companion.Companion."""
    def draw(self, cr) -> None: ...          # cr: a cairo.Context sized to the window
    def pointer_press(self, ev: PointerEvent) -> None: ...
    def pointer_motion(self, ev: PointerEvent) -> None: ...
    def pointer_release(self, ev: PointerEvent) -> None: ...


class WindowHost(ABC):
    """A borderless, transparent, always-on-top window the robot lives in.

    It must not appear in the taskbar or take keyboard focus, and must let
    clicks outside `set_click_regions` fall through to whatever is below.
    """

    @abstractmethod
    def show(self) -> None: ...

    @abstractmethod
    def move(self, x: int, y: int) -> None:
        """Place the window's top-left corner at screen position (x, y)."""

    @abstractmethod
    def position(self) -> tuple: ...

    @abstractmethod
    def resize(self, width: int, height: int) -> None:
        """Change the window size (the robot's size setting changed)."""

    @abstractmethod
    def workarea(self) -> Rect:
        """Usable area of the screen the robot walks on (minus docks/panels)."""

    @abstractmethod
    def set_click_regions(self, regions: List[Rect]) -> None:
        """Only these window-local rectangles receive mouse input."""

    @abstractmethod
    def redraw(self) -> None:
        """Ask for listener.draw() to be called soon."""

    @abstractmethod
    def show_menu(self, items: List[MenuItem]) -> None:
        """Pop up a context menu at the mouse pointer."""

    def keep_on_top(self) -> None:
        """Called every few seconds; re-raise the window if the OS needs it."""


# ---------------------------------------------------------------- main loop
class Scheduler(ABC):
    @abstractmethod
    def every(self, seconds: float, fn: Callable[[], None]) -> None:
        """Call fn repeatedly, about every `seconds`."""

    @abstractmethod
    def after(self, seconds: float, fn: Callable[[], None]) -> None:
        """Call fn once, after `seconds`."""

    @abstractmethod
    def run(self) -> None:
        """Run the main loop until quit() is called."""

    @abstractmethod
    def quit(self) -> None: ...


# ---------------------------------------------------------------- inputs
class EventSource(ABC):
    """Something the robot keeps an eye on (battery, notifications, ...)."""
    name = 'source'

    @abstractmethod
    def start(self, emit: EventSink) -> None:
        """Begin watching; call emit(Event(...)) on the main thread."""

    def apply_settings(self, settings: Settings) -> None:
        """Settings changed while running (e.g. update checks switched off)."""


class IdleMonitor(ABC):
    """Tells how long the user has not touched keyboard or mouse."""

    @abstractmethod
    def start(self, on_idle: Callable[[float], None]) -> None:
        """Call on_idle(seconds_idle) about twice a second."""

    def is_inhibited(self) -> bool:
        """True while something (a video player...) keeps the screen awake."""
        return False


# ---------------------------------------------------------------- platform
class Platform(ABC):
    """Bundles everything OS specific. One instance per run."""
    name = 'unknown'

    def __init__(self):
        self.scheduler: Scheduler = self.create_scheduler()

    def clock(self) -> float:
        """Monotonic time in seconds used for all animation."""
        return time.monotonic()

    @abstractmethod
    def create_scheduler(self) -> Scheduler: ...

    @abstractmethod
    def create_window(self, width: int, height: int, listener: WindowListener) -> WindowHost: ...

    def event_sources(self, settings: Settings) -> List[EventSource]:
        return []

    def idle_monitor(self) -> Optional[IdleMonitor]:
        return None

    def acquire_single_instance(self) -> bool:
        """Return False if another robot is already running."""
        return True

    def config_dir(self) -> str:
        """Folder for settings.json."""
        return os.path.join(os.path.expanduser('~'), '.robo')

    # ------------------------------------------------------------ settings window
    # A platform with a settings window returns True and implements
    # open_settings(). The window should be generated from robo.config.FIELDS
    # and call on_apply(new_settings) when the user presses Apply.
    @property
    def has_settings_window(self) -> bool:
        return False

    def open_settings(self, settings: Settings,
                      on_apply: Callable[[Settings], None]) -> None:
        raise NotImplementedError
