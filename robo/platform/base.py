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
from robo.sandbox import Approver, DenyAll, SandboxBackend


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
    icon: Optional[str] = None               # a picture to show before the label ('settings')

    @classmethod
    def separator(cls):
        return cls(None)


@dataclass(frozen=True)
class ShareInfo:
    """What you chose to show him."""
    kind: str = 'monitor'                    # 'monitor' (a whole screen) or 'window'
    rect: Optional[Rect] = None              # where it is on the desktop, if known


class InputControl:
    """Robo (a plugin, really) using your keyboard and mouse. start() must ask
    you first, in a way Robo can't click through (Linux: GNOME's RemoteDesktop
    portal), and the desktop should show while it's on. Everything is on the
    main thread."""
    active = False

    def problem(self) -> Optional[str]:
        """Why it can't work here (None = it can)."""
        return 'not available on this computer'

    def start(self, on_started: Callable[[], None], on_ended: Callable[[str], None]) -> None:
        """Ask you. on_started() once allowed; on_ended(reason) when it's over
        (you said no, stopped it from the desktop, or stop() was called)."""
        on_ended(self.problem() or 'not available')

    def key(self, name: str, down: bool) -> bool:
        """Press / release a key by name ('w', 'space', 'ctrl', 'Return', 'F5').
        False if there's no such key."""
        return False

    def button(self, name: str, down: bool) -> bool:
        """'left', 'right' or 'middle'."""
        return False

    def move(self, dx: float, dy: float) -> None:
        """Move the pointer relative to where it is (games: look around)."""

    def scroll(self, steps: int) -> None:
        """Mouse wheel: positive scrolls down."""

    def stop(self) -> None:
        """Give the keyboard and mouse back (calls on_ended)."""


class Camera:
    """Taking a picture with your camera (the platform shows when it does)."""

    def problem(self) -> Optional[str]:
        return 'no camera'

    def snapshot(self, on_done: Callable[[Optional[bytes], Optional[str]], None]) -> None:
        """on_done(png, None) or on_done(None, why), later, on the main thread."""
        on_done(None, self.problem())


class ScreenShare:
    """You show Robo your screen, on purpose, and you can see that you are.

    The rules every platform must keep:
      * Only start() begins a share, and start() must let YOU pick what to show
        (the system's own picker). Robo can't pick, and nothing starts by itself.
      * While a share is on, an unmistakable indicator is on screen (a pulsing red
        border around what's shared, and a way to stop). No indicator, no frames:
        grab() returns None unless the indicator is showing.
      * stop() ends it everywhere, at once. So does the system's own stop button.
    """
    def problem(self) -> Optional[str]:
        """Why sharing isn't possible here, or None."""
        return 'not supported here'

    def start(self, on_started: Callable[[ShareInfo], None],
              on_ended: Callable[[str], None]) -> None:
        """Ask you what to share. on_ended(reason) also fires if you cancel the picker."""
        on_ended('not supported here')

    @property
    def active(self) -> bool:
        return False

    def grab(self) -> Optional[bytes]:
        """The latest picture of what you're sharing (PNG), or None."""
        return None

    def stop(self) -> None:
        pass


class WindowListener(Protocol):
    """Implemented by robo.core.companion.Companion."""
    def draw(self, cr) -> None: ...          # cr: a cairo.Context sized to the window
    def pointer_press(self, ev: PointerEvent) -> None: ...
    def pointer_motion(self, ev: PointerEvent) -> None: ...
    def pointer_release(self, ev: PointerEvent) -> None: ...
    def pointer_leave(self) -> None: ...     # the mouse left the window


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

    def pointer_position(self) -> Optional[tuple]:
        """Where the mouse pointer is on the screen (x, y), or None if unknown.
        Optional: Robo's eyes follow it."""
        return None

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


# ---------------------------------------------------------------- voice
@dataclass
class Utterance:
    """Something the robot is saying. `envelope` is the loudness (0..1) of
    the audio for every `frame_seconds`, used to move his mouth."""
    text: str
    envelope: List[float]
    frame_seconds: float
    duration: float
    started_at: float = 0.0       # set by the core when playback starts


class SpeechOutput(ABC):
    """Text to speech in Robo's voice."""
    available = True

    def configure(self, settings: Settings) -> None:
        """Pitch, speed, volume and effect settings changed."""

    @abstractmethod
    def say(self, text: str, on_started: Callable[[Utterance], None],
            on_done: Callable[[], None], style: str = 'normal') -> None:
        """Speak `text` without blocking. Call on_started(utterance) when the
        audio starts and on_done() when it has finished (or was stopped),
        both on the main thread. `style` is 'normal' (soft, friendly voice)
        or 'evil' (robotic and menacing)."""

    @abstractmethod
    def stop(self) -> None:
        """Stop talking right now (on_done is still called)."""

    def shutdown(self) -> None:
        """The app is closing."""
        self.stop()

    def update(self, now: float) -> None:
        """Called every frame; for implementations without real audio."""


class SpeechInput(ABC):
    """Speech recognition. All callbacks must run on the main thread."""
    available = True
    unavailable_reason = ''

    @abstractmethod
    def listen(self, timeout: float, on_heard: Callable[[str], None],
               on_silence: Callable[[], None],
               on_partial: Optional[Callable[[str], None]] = None) -> None:
        """Listen for one sentence. on_heard(text) when the user finished
        speaking; on_silence() if nothing was said within `timeout` seconds."""

    @abstractmethod
    def pause(self) -> None:
        """Stop listening (e.g. while Robo talks, so he doesn't hear himself)."""

    def overhear(self, phrases, on_text: Callable[[str], None]) -> None:
        """While Robo talks: listen for `phrases` ("stop talking", "mute") and call
        on_text(text) with what was heard (Robo decides; his own voice may come
        through the speakers). pause(), listen() or set_wake_word() ends it.
        Ears that can't (the default) don't."""

    def prepare(self) -> None:
        """A conversation is starting: get ready to listen (e.g. load the
        speech model) without opening the microphone yet."""

    def set_wake_word(self, enabled: bool, on_wake: Callable[[], None]) -> None:
        """Keep listening for "Hey Robo" between conversations."""

    def shutdown(self) -> None:
        """The app is closing."""


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

    def speech_output(self) -> Optional[SpeechOutput]:
        return None

    def screen_share(self) -> Optional['ScreenShare']:
        """Letting you show Robo your screen (None if this platform can't)."""
        return None

    def input_control(self) -> Optional[InputControl]:
        """Letting a plugin use your keyboard and mouse (None if this platform can't)."""
        return None

    def camera(self) -> Optional[Camera]:
        """Letting a plugin take pictures with your camera (None if it can't)."""
        return None

    def plugin_dir(self) -> str:
        """Where your own plugins live (~/.config/robo/plugins on Linux)."""
        return os.path.join(self.config_dir(), 'plugins')

    def speech_input(self) -> Optional[SpeechInput]:
        return None

    def battery_percent(self) -> Optional[tuple]:
        """(percent, charging) or None, for answering "how's my battery?"."""
        return None

    def config_dir(self) -> str:
        """Folder for settings.json."""
        return os.path.join(os.path.expanduser('~'), '.robo')

    # ------------------------------------------------------------ tasks
    # Tasks only run when the platform provides a sandbox (see
    # robo/sandbox/backend.py for the rules it must follow).
    def sandbox(self) -> Optional[SandboxBackend]:
        """The sandbox tasks run in, or None (then Robo refuses tasks)."""
        return None

    def approver(self) -> Approver:
        """Asks you before a task gets permissions or changes your files."""
        return DenyAll()

    def task_dir(self) -> str:
        """Folder for task workspaces."""
        return os.path.join(os.path.expanduser('~'), '.robo', 'tasks')

    def agent_dir(self) -> str:
        """Empty folder of Robo's own that the AI agent CLI runs in."""
        return os.path.join(os.path.expanduser('~'), '.robo', 'agent')

    # ------------------------------------------------------------ settings window
    # A platform with a settings window returns True and implements
    # open_settings(). The window should be generated from robo.config.FIELDS
    # and call on_apply(new_settings) when the user presses Apply.
    @property
    def has_settings_window(self) -> bool:
        return False

    def open_settings(self, settings: Settings, on_apply: Callable[[Settings], None],
                      memory=None, designs=None, plugins=None) -> None:
        """`memory` (robo.core.memory.Memory) lets the window show and erase it;
        `plugins` (robo.plugins.PluginManager) lists plugins to switch on and off;
        `designs` is the folder of outfits he designed himself; the window can list,
        remove, export and import outfits (robo.design.sharing) next to it."""
        raise NotImplementedError

    def data_dir(self) -> str:
        """Folder for Robo's own data (his memory of you)."""
        return os.path.join(os.path.expanduser('~'), '.robo')
