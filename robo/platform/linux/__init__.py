"""Linux back end: GTK 3 window (via XWayland), D-Bus, sysfs.

Pieces, each replaceable on its own:
    mainloop.py       GLib main loop                       -> Scheduler
    gtk_window.py     transparent click-through window     -> WindowHost
    notifications.py  desktop notifications (D-Bus)        -> EventSource
    battery.py        /sys/class/power_supply              -> EventSource
    network.py        NetworkManager (D-Bus)               -> EventSource
    updates.py        apt / snap / flatpak                 -> EventSource
    idle.py           GNOME Mutter idle monitor (D-Bus)    -> IdleMonitor
    instance.py       lock file                            -> single instance
    settings_window.py the themed settings window          -> open_settings()
    voice.py          espeak-ng + robot filter + pw-play     -> SpeechOutput
    listen.py         Vosk helper process (stt_worker.py)    -> SpeechInput
    sandbox.py        bubblewrap + systemd-run limits        -> SandboxBackend
    approval.py       "may this task...?" dialogs            -> Approver
"""
import os

# Wayland does not let apps position their own windows; XWayland does.
# Must be set before GTK is imported.
os.environ['GDK_BACKEND'] = 'x11'

from robo.platform.base import Platform  # noqa: E402


class LinuxPlatform(Platform):
    name = 'linux'

    def create_scheduler(self):
        from .mainloop import GLibScheduler
        return GLibScheduler()

    def create_window(self, width, height, listener):
        from .gtk_window import GtkWindowHost
        return GtkWindowHost(width, height, listener)

    def event_sources(self, settings):
        from .battery import BatteryWatcher
        from .network import NetworkWatcher
        from .notifications import NotificationWatcher
        from .updates import UpdateWatcher
        # The update watcher always exists so it can be switched on/off live.
        return [NotificationWatcher(), BatteryWatcher(), NetworkWatcher(),
                UpdateWatcher(enabled=settings.check_updates)]

    def idle_monitor(self):
        from .idle import MutterIdleMonitor
        return MutterIdleMonitor.create()

    def acquire_single_instance(self):
        from .instance import acquire_lock
        return acquire_lock()

    def speech_output(self):
        from .voice import create_voice
        return create_voice()

    def speech_input(self):
        from .listen import VoskEars
        return VoskEars()

    def screen_share(self):
        from .screencast import PortalScreenShare
        return PortalScreenShare()

    def input_control(self):
        from .remote_input import PortalInput
        return PortalInput()

    def camera(self):
        from .camera import GstCamera
        return GstCamera()

    def battery_percent(self):
        import glob
        for bat in sorted(glob.glob('/sys/class/power_supply/BAT*')):
            try:
                with open(os.path.join(bat, 'capacity')) as f:
                    pct = int(f.read().strip())
                with open(os.path.join(bat, 'status')) as f:
                    status = f.read().strip()
            except (OSError, ValueError):
                continue
            return pct, status in ('Charging', 'Full', 'Not charging')
        return None

    def sandbox(self):
        if getattr(self, '_sandbox', None) is None:
            from .sandbox import BubblewrapBackend
            self._sandbox = BubblewrapBackend()
        return self._sandbox

    def approver(self):
        from .approval import GtkApprover
        return GtkApprover()

    def task_dir(self):
        from .paths import data_dir
        return os.path.join(data_dir(), 'tasks')

    def agent_dir(self):
        from .paths import data_dir
        return os.path.join(data_dir(), 'agent')

    def config_dir(self):
        base = os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser('~/.config')
        return os.path.join(base, 'robo')

    @property
    def has_settings_window(self):
        return True

    def open_settings(self, settings, on_apply, memory=None, designs=None, plugins=None):
        if getattr(self, '_settings_window', None) is None:
            from .settings_window import SettingsWindow
            self._settings_window = SettingsWindow()
        self._settings_window.open(settings, on_apply, memory, designs, plugins)

    def data_dir(self):
        from .paths import data_dir
        return data_dir()
