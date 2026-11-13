"""A fake platform with no real window: renders off-screen, time is manual.

Used by the tests and for rendering previews; it is also the smallest
complete example of a back end, handy as a template for a new port.

    p = HeadlessPlatform()
    robot = build_companion(Settings(), p)    # see robo.app
    p.scheduler.advance(5)                    # simulate 5 seconds
    p.window.save_png('frame.png')
"""
import os

import cairo

from robo.core.geometry import Rect
from robo.platform.base import (IdleMonitor, Platform, Scheduler, SpeechInput, SpeechOutput,
                                Utterance, WindowHost)
from robo.sandbox import Approver, SandboxBackend, SandboxProcess


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

    pointer = None                 # tests set (x, y) to move the "mouse"

    def pointer_position(self):
        return self.pointer

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


class FakeSandbox(SandboxBackend):
    """Pretends to run jobs, on the manual clock. Runs no code at all, so it's
    safe; the real sandboxes are tested in tests/test_sandbox.py."""
    name = 'fake'

    def __init__(self, clock):
        self.clock = clock
        self.problem = None
        self.launched = []

    def check(self):
        return self.problem

    def launch(self, spec):
        proc = FakeSandboxProcess(self.clock)
        self.launched.append((spec, proc))
        return proc

    def stdio_command(self, spec):
        """Tests only: Robo's MCP tool server WITHOUT any isolation, in the work folder."""
        import sys
        from robo.sandbox.backend import WORKER_DIR
        self.launched.append((spec, None))
        return [sys.executable, '-I', os.path.join(WORKER_DIR, spec.entry),
                '--root', spec.work_dir], {}


class FakeSandboxProcess(SandboxProcess):
    """Understands the 'placeholder' job: works for args['seconds']."""

    def __init__(self, clock):
        self.clock = clock
        self.seconds = None
        self.worked = 0.0
        self.paused = False
        self.killed = False
        self._last = clock()
        self._outbox = []
        self._done = False

    def send(self, message):
        if message.get('type') == 'start':
            if message.get('job') == 'placeholder':
                self.seconds = float(message['args'].get('seconds', 1))
            else:
                self._outbox.append({'type': 'error', 'message': 'unknown job'})

    def receive(self):
        now = self.clock()
        if not (self.paused or self.killed or self._done) and self.seconds:
            self.worked += now - self._last
            if self.worked >= self.seconds:
                self._done = True
                self._outbox.append({'type': 'done', 'result': 'pretend result'})
            else:
                self._outbox.append({'type': 'progress', 'value': self.worked / self.seconds})
        self._last = now
        out, self._outbox = self._outbox, []
        return out

    def pause(self):
        self.receive()
        self.paused = True

    def resume(self):
        self._last = self.clock()
        self.paused = False

    def kill(self):
        self.killed = True

    def exit_code(self):
        return -9 if self.killed else (0 if self._done else None)


class FakeApprover(Approver):
    """Answers `answer` (default yes) and records what it was asked."""

    def __init__(self):
        self.answer = True
        self.asked = []

    def ask_permissions(self, title, lines, on_answer):
        self.asked.append(('permissions', title, lines))
        on_answer(self.answer)

    def review_changes(self, title, lines, on_answer):
        self.asked.append(('changes', title, lines))
        on_answer(self.answer)


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
        self.fake_sandbox = FakeSandbox(self.clock)
        self.fake_approver = FakeApprover()
        self.tmp_task_dir = None

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

    def sandbox(self):
        return self.fake_sandbox

    def approver(self):
        return self.fake_approver

    def agent_dir(self):
        return os.path.join(self.task_dir(), 'agent')

    def task_dir(self):
        if self.tmp_task_dir is None:
            import atexit
            import shutil
            import tempfile
            self.tmp_task_dir = tempfile.mkdtemp(prefix='robo-tasks-')
            atexit.register(shutil.rmtree, self.tmp_task_dir, True)
        return self.tmp_task_dir

    @property
    def has_settings_window(self):
        return True

    def open_settings(self, settings, on_apply, memory=None):
        self.settings_opened.append((settings, on_apply))

    def data_dir(self):
        return os.path.join(self.task_dir(), 'data')
