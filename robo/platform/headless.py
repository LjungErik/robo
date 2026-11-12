"""A fake platform with no real window: renders off-screen, time is manual.

Used by the tests and for rendering previews; it is also the smallest
complete example of a back end, handy as a template for a new port.

    p = HeadlessPlatform()
    robot = build_companion(Settings(), p)    # see robo.app
    p.scheduler.advance(5)                    # simulate 5 seconds
    p.window.save_png('frame.png')
"""
import cairo

from robo.core.geometry import Rect
from robo.platform.base import (IdleMonitor, Platform, Scheduler, SpeechInput, SpeechOutput,
                                Utterance, WindowHost)


class ManualScheduler(Scheduler):
    """Time only moves when advance() is called."""

    def __init__(self, start=1000.0):
        self.now = start
        self._jobs = []           # [next_time, interval or None, fn]
        self.running = False

    def every(self, seconds, fn):
        self._jobs.append([self.now + seconds, seconds, fn])

    def after(self, seconds, fn):
        self._jobs.append([self.now + seconds, None, fn])

    def advance(self, seconds, step=1 / 30):
        end = self.now + seconds
        while self.now < end:
            self.now = min(end, self.now + step)
            for job in list(self._jobs):
                if job[0] <= self.now:
                    job[2]()
                    if job[1] is None:
                        self._jobs.remove(job)
                    else:
                        job[0] += job[1]

    def run(self):
        self.running = True

    def quit(self):
        self.running = False


class OffscreenWindow(WindowHost):
    def __init__(self, width, height, listener, workarea=Rect(0, 0, 1920, 1080)):
        self.listener = listener
        self.width, self.height = width, height
        self.pos = (0, 0)
        self.regions = []
        self.menus = []           # every menu that was "shown"
        self._workarea = workarea
        self.surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)

    def show(self):
        self.redraw()

    def move(self, x, y):
        self.pos = (x, y)

    def position(self):
        return self.pos

    def resize(self, width, height):
        self.width, self.height = width, height
        self.surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)

    def workarea(self):
        return self._workarea

    def set_click_regions(self, regions):
        self.regions = list(regions)

    def redraw(self):
        self.listener.draw(cairo.Context(self.surface))

    def show_menu(self, items):
        self.menus.append(items)

    def save_png(self, path):
        self.surface.write_to_png(path)


class FakeIdleMonitor(IdleMonitor):
    def __init__(self):
        self.on_idle = None
        self.inhibited = False

    def start(self, on_idle):
        self.on_idle = on_idle

    def feed(self, seconds):
        self.on_idle(seconds)

    def is_inhibited(self):
        return self.inhibited


class FakeVoice(SpeechOutput):
    """Records what was said; each sentence 'plays' for a while on the manual clock."""
    SECONDS_PER_WORD = 0.3

    def __init__(self, scheduler):
        self.scheduler = scheduler
        self.said = []
        self.styles = []
        self.settings = None
        self._job = 0

    def configure(self, settings):
        self.settings = settings

    def say(self, text, on_started, on_done, style='normal'):
        self.said.append(text)
        self.styles.append(style)
        self._job += 1
        job = self._job
        duration = max(0.5, len(text.split()) * self.SECONDS_PER_WORD)
        frames = int(duration * 30)
        on_started(Utterance(text, [0.8 if i % 4 < 2 else 0.2 for i in range(frames)],
                             1 / 30, duration))
        self._on_done = on_done
        self.scheduler.after(duration, lambda: self._done(job))

    def _done(self, job):
        if job == self._job and self._on_done:
            cb, self._on_done = self._on_done, None
            cb()

    def stop(self):
        self._job += 1
        cb, self._on_done = getattr(self, '_on_done', None), None
        if cb:
            cb()


class FakeEars(SpeechInput):
    """Tests decide what the user "says" with hear() / stay_silent()."""

    def __init__(self):
        self.listening = None
        self.wake_word = False
        self.on_wake = None

    def listen(self, timeout, on_heard, on_silence, on_partial=None):
        self.listening = (on_heard, on_silence)

    def pause(self):
        self.listening = None

    def set_wake_word(self, enabled, on_wake):
        self.wake_word, self.on_wake = enabled, on_wake

    def hear(self, text):
        on_heard, _ = self.listening
        self.listening = None
        on_heard(text)

    def stay_silent(self):
        _, on_silence = self.listening
        self.listening = None
        on_silence()

    def say_wake_word(self):
        if self.wake_word and self.on_wake:
            self.on_wake()


class HeadlessPlatform(Platform):
    name = 'headless'

    def __init__(self, config_dir=None):
        super().__init__()
        self.window = None
        self.idle = FakeIdleMonitor()
        self._config_dir = config_dir
        self.settings_opened = []      # (settings, on_apply) for every open_settings() call
        self.voice = FakeVoice(self.scheduler)
        self.ears = FakeEars()
        self.battery = (76, False)

    def clock(self):
        return self.scheduler.now

    def create_scheduler(self):
        return ManualScheduler()

    def create_window(self, width, height, listener):
        self.window = OffscreenWindow(width, height, listener)
        return self.window

    def idle_monitor(self):
        return self.idle

    def config_dir(self):
        return self._config_dir or super().config_dir()

    def speech_output(self):
        return self.voice

    def speech_input(self):
        return self.ears

    def battery_percent(self):
        return self.battery

    @property
    def has_settings_window(self):
        return True

    def open_settings(self, settings, on_apply):
        self.settings_opened.append((settings, on_apply))
