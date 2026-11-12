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
from robo.platform.base import IdleMonitor, Platform, Scheduler, WindowHost


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


class HeadlessPlatform(Platform):
    name = 'headless'

    def __init__(self, config_dir=None):
        super().__init__()
        self.window = None
        self.idle = FakeIdleMonitor()
        self._config_dir = config_dir
        self.settings_opened = []      # (settings, on_apply) for every open_settings() call

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

    @property
    def has_settings_window(self):
        return True

    def open_settings(self, settings, on_apply):
        self.settings_opened.append((settings, on_apply))
