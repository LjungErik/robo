"""Start-up and settings: pick the platform, wire everything up, hot reload.

Settings priority: defaults < settings file < command-line flags.
Changes from the settings window (Apply) or from editing the file are
applied to the running robot immediately.
"""
import argparse
import logging
import os
import sys

from robo.config import Settings
from robo.conversation import AgentBrain, RuleBrain
from robo.core.companion import Companion
from robo.design import REGISTRY
from robo.platform import load_platform
from robo.sandbox import Workspace
from robo.settings_store import SettingsStore
from robo.tasks import TaskEnvironment

TICKS_PER_SECOND = 30
DEMO_DELAY = 1.2
FILE_CHECK_SECONDS = 2

log = logging.getLogger(__name__)


def parse_args(argv=None):
    """Returns (overrides, platform name). Only flags actually given override."""
    ap = argparse.ArgumentParser(prog='robot_companion',
                                 description='A cute desktop robot companion. '
                                             'Most settings are easier to change from his '
                                             'right-click menu → Settings.')
    ap.add_argument('--scale', type=float, help='size multiplier (e.g. 1.5)')
    ap.add_argument('--demo', action='store_true', help='show every icon once at start-up')
    ap.add_argument('--verbose', '-v', action='store_true', default=None,
                    help='log events to stdout')
    ap.add_argument('--no-updates', action='store_true', help='do not check for software updates')
    ap.add_argument('--evil-after', type=float, metavar='SECONDS',
                    help='turn evil after this long without keyboard/mouse input (0 = never)')
    ap.add_argument('--dress-up-every', type=float, metavar='SECONDS',
                    help='about how often he dresses up as a character (0 = never)')
    ap.add_argument('--look', metavar='ID',
                    help='what he looks like (robo, ironman, spiderman, thanos, ...)')
    ap.add_argument('--agent', choices=('off', 'claude', 'codex', 'gemini'),
                    help='AI brain to talk through (uses that CLI\'s own login, no API key)')
    ap.add_argument('--check', nargs='*', metavar='FILE',
                    help='check character files (all of them if none given) and exit')
    ap.add_argument('--platform', default=None, help=argparse.SUPPRESS)   # e.g. 'headless'
    a = ap.parse_args(argv)
    overrides = {}
    if a.check is not None:
        overrides['check'] = a.check
    if a.look:
        overrides['look'] = a.look
    if a.agent:
        overrides['agent'] = a.agent
    if a.scale is not None:
        overrides['scale'] = a.scale
    if a.verbose:
        overrides['verbose'] = True
    if a.no_updates:
        overrides['check_updates'] = False
    if a.evil_after is not None:
        overrides.update(evil_after=a.evil_after, evil_mode=a.evil_after > 0)
    if a.dress_up_every is not None:
        overrides.update(dress_up_every=a.dress_up_every, dress_up=a.dress_up_every > 0)
    if a.demo:
        overrides['demo'] = True
    return overrides, a.platform


def _set_log_level(settings):
    logging.getLogger().setLevel(logging.INFO if settings.verbose else logging.WARNING)


class RoboApp:
    """Owns the settings and connects robot, platform and settings file."""

    def __init__(self, settings, platform, store=None):
        self.settings = settings
        self.platform = platform
        self.store = store
        self.robot = Companion(settings, clock=platform.clock)
        host = platform.create_window(self.robot.width, self.robot.height, listener=self.robot)
        self.robot.attach(host)
        self.robot.on_quit = platform.scheduler.quit
        if platform.has_settings_window:
            self.robot.on_open_settings = self.open_settings

        self.sources = platform.event_sources(settings)
        for source in self.sources:
            source.start(self.robot.handle_event)

        # Tasks run in the platform's sandbox, and ask you via its approver.
        self.robot.task_env = TaskEnvironment(sandbox=platform.sandbox(),
                                              approver=platform.approver(),
                                              workspace_root=platform.task_dir(),
                                              agent_factory=self._task_agent)
        Workspace.prune(platform.task_dir())

        # Conversation: RuleBrain for commands, plus an AI agent if one is chosen
        # in settings (Claude / ChatGPT / Gemini through their own logged-in CLI).
        self.brain = AgentBrain(RuleBrain(), workdir=platform.agent_dir())
        self.brain.configure(settings)
        self.robot.conversation.battery = platform.battery_percent
        self.robot.conversation.attach(self.brain, voice=platform.speech_output(),
                                       ears=platform.speech_input())

        idle = platform.idle_monitor()     # always on, so evil mode can be switched on live
        if idle is not None:
            self.robot.evil.is_inhibited = idle.is_inhibited
            idle.start(self.robot.on_idle)

        sched = platform.scheduler
        sched.every(1 / TICKS_PER_SECOND, self.robot.tick)
        if store is not None:
            sched.every(FILE_CHECK_SECONDS, self._check_settings_file)
            sched.every(FILE_CHECK_SECONDS, self._check_character_files)
        if settings.demo:
            sched.after(DEMO_DELAY, self.robot.demo)
        host.show()

    def _task_agent(self):
        """A fresh agent backend for a task (separate from the one he chats with)."""
        from robo.agents import make_backend
        s = self.settings
        return make_backend(s.agent, self.platform.agent_dir(), s.agent_model)

    # ------------------------------------------------------------ settings
    def open_settings(self):
        self.platform.open_settings(self.settings, self.apply)

    def apply(self, settings, save=True):
        """Use new settings right away (and remember them)."""
        settings = settings.with_changes(demo=False)
        if save and self.store is not None:
            try:
                self.store.save(settings)
            except OSError as e:
                log.warning('could not save settings: %s', e)
        self.settings = settings
        _set_log_level(settings)
        self.robot.apply_settings(settings)
        self.brain.configure(settings)
        for source in self.sources:
            source.apply_settings(settings)
        log.info('settings applied: %s', settings.to_dict())

    def _check_character_files(self):
        """Edited a character file? He changes right away (handy while designing one)."""
        if REGISTRY.reload_if_changed():
            log.info('character files changed, reloaded')
            self.settings = self.settings.with_changes()       # re-check look / characters
            self.robot.characters_reloaded()
            self.robot.apply_settings(self.settings)

    def _check_settings_file(self):
        if self.store.changed_on_disk():
            log.info('settings file changed, reloading')
            self.apply(self.store.load(), save=False)


def characters_dir(platform):
    """Where your own character files go (~/.config/robo/characters on Linux)."""
    return os.path.join(platform.config_dir(), 'characters')


def build_companion(settings, platform):
    """Robot + platform without a settings file (used by tests and previews)."""
    return RoboApp(settings, platform).robot


def main(argv=None):
    overrides, platform_name = parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format='%(asctime)s %(message)s',
                        datefmt='%H:%M:%S')
    if 'check' in overrides:
        from robo.design.check import check
        files = overrides.pop('check')
        if not files:                          # everything, including your own folder
            REGISTRY.add_directory(characters_dir(load_platform('headless')))
        return 1 if check(files) else 0
    platform = load_platform(platform_name)
    if not platform.acquire_single_instance():
        print('Robot companion is already running.')
        return 0
    REGISTRY.add_directory(characters_dir(platform))       # your own characters
    store = SettingsStore(platform.config_dir())
    settings = store.load().with_changes(**overrides)
    _set_log_level(settings)
    app = RoboApp(settings, platform, store)
    try:
        platform.scheduler.run()
    finally:
        app.robot.conversation.shutdown()   # close the microphone helper
        app.robot.shutdown()                # stop every task sandbox
    return 0


if __name__ == '__main__':
    sys.exit(main())
