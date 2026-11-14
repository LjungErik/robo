"""One running plugin: its sandboxed process, and the messages to and from it.

Robo's side of robo/sandbox/worker/plugin_host.py. Everything here runs on
Robo's main thread (update() is called every frame by the PluginManager).
"""
import logging
import os
import shutil

from robo.sandbox.backend import Limits, LaunchSpec, Mount

log = logging.getLogger(__name__)

LIMITS = Limits(memory_mb=768, max_processes=48, max_file_mb=128)
START_TIMEOUT = 20.0          # seconds to say "ready"
INVOKE_TIMEOUT = 60.0         # a command / tool / menu item must answer by then
STOP_GRACE = 2.5
RESTART_DELAYS = (1.0, 3.0, 10.0)   # after a crash; more crashes than this: broken

OFF, STARTING, RUNNING, STOPPING, CRASHED, BROKEN = (
    'off', 'starting', 'running', 'stopping', 'crashed', 'broken')


class PluginRunner:
    def __init__(self, manifest, backend, data_dir, services, clock):
        self.manifest = manifest
        self.backend = backend
        self.data_dir = data_dir          # the plugin's own folder (/work inside)
        self.services = services          # robo.plugins.services.Services
        self.clock = clock
        self.state = OFF
        self.problem = ''
        self.proc = None
        self.commands, self.tools, self.menus = [], [], []
        self.crashes = 0
        self._pending = {}                # rid -> (on_result, deadline)
        self._rid = 0
        self._deadline = None             # start / stop timeout
        self._restart_at = None
        self._want = False                # should be running

    @property
    def id(self):
        return self.manifest.id

    @property
    def running(self):
        return self.state == RUNNING

    # ------------------------------------------------------------ life
    def start(self):
        self._want = True
        if self.proc is not None:
            return
        self.problem = ''
        try:
            os.makedirs(self.data_dir, mode=0o700, exist_ok=True)
            mounts = self._place_code()
            spec = LaunchSpec(work_dir=self.data_dir, read_only=mounts,
                              log_path=os.path.join(self.data_dir, 'plugin.log'),
                              limits=LIMITS, entry='plugin_host.py')
            self._trim_log(spec.log_path)
            self.proc = self.backend.launch(spec)
        except Exception as e:            # noqa: BLE001 - one plugin must never take Robo down
            self.proc = None
            self.state = BROKEN
            self.problem = f'could not start: {e}'
            log.warning('plugin %s: %s', self.id, self.problem)
            return
        self.proc.send({'type': 'start', 'manifest': self.manifest.to_dict()})
        self.state = STARTING
        self._deadline = self.clock() + START_TIMEOUT
        log.info('plugin %s starting', self.id)

    def _place_code(self):
        """The plugin's code goes in ./plugin, read-only (copied if the sandbox
        can't mount)."""
        target = os.path.join(self.data_dir, 'plugin')
        if getattr(self.backend, 'supports_mounts', True):
            os.makedirs(target, exist_ok=True)
            return (Mount(self.manifest.folder, 'plugin'),)
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(self.manifest.folder, target,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.*'))
        return ()

    @staticmethod
    def _trim_log(path, keep=200_000):
        try:
            if os.path.getsize(path) > keep:
                with open(path, 'rb') as f:
                    f.seek(-keep // 2, os.SEEK_END)
                    tail = f.read()
                with open(path, 'wb') as f:
                    f.write(tail)
        except OSError:
            pass

    def stop(self, reason='switched off'):
        """Ask it to finish; it's killed if it doesn't within STOP_GRACE."""
        self._want = False
        self._restart_at = None
        self._halt(reason)

    def _halt(self, reason):
        if self.proc is None:
            self.state = OFF if not self._want else self.state
            return
        self.services.plugin_stopping(self, reason)
        self.proc.send({'type': 'stop'})
        self.state = STOPPING
        self._deadline = self.clock() + STOP_GRACE
        self._fail_pending('the plugin stopped')

    def reload(self):
        """Its files changed: start it again with the new code (crashes forgiven)."""
        self.crashes = 0
        want = self._want
        self.kill('reloading')
        if want:
            self.start()

    def kill(self, reason='killed'):
        if self.proc is not None:
            self.services.plugin_stopping(self, reason)
            self.proc.kill()
            self.proc = None
        self._fail_pending('the plugin stopped')
        self.commands, self.tools, self.menus = [], [], []
        self.state = OFF

    # ------------------------------------------------------------ talking to it
    def invoke(self, kind, name, on_result, text='', args=None, timeout=INVOKE_TIMEOUT):
        """Run one of its handlers; on_result(value, error) later, on the main thread."""
        if not self.running:
            on_result(None, f'{self.manifest.name} is not running')
            return
        self._rid += 1
        self._pending[self._rid] = (on_result, self.clock() + timeout)
        self.proc.send({'type': 'invoke', 'rid': self._rid, 'kind': kind, 'name': name,
                        'text': text, 'args': args or {}})

    def event(self, name, *args):
        if self.running:
            self.invoke('event', name, lambda *_: None, args=list(args))

    def reply(self, call_id, value=None, error=None):
        if self.proc is not None:
            self.proc.send({'type': 'reply', 'id': call_id, 'value': value, 'error': error})

    def _fail_pending(self, error):
        pending, self._pending = self._pending, {}
        for on_result, _deadline in pending.values():
            on_result(None, error)

    # ------------------------------------------------------------ every frame
    def update(self, now):
        if self.proc is None:
            if self._want and self._restart_at is not None and now >= self._restart_at:
                self._restart_at = None
                self.start()
            return
        for msg in self.proc.receive():
            self._handle(msg)
        for rid, (on_result, deadline) in list(self._pending.items()):
            if now > deadline:
                del self._pending[rid]
                on_result(None, f'{self.manifest.name} took too long')
        if self.proc is None:
            return
        code = self.proc.exit_code()
        if code is not None:
            self._exited(code)
        elif self._deadline is not None and now > self._deadline:
            if self.state == STARTING:
                self.problem = 'it did not start in time'
                self._crashed()
            elif self.state == STOPPING:
                self.kill('stopped')

    def _handle(self, msg):
        kind = msg.get('type')
        if kind == 'ready':
            self.commands = [c for c in msg.get('commands') or () if isinstance(c, dict)]
            self.tools = [t for t in msg.get('tools') or () if isinstance(t, dict)]
            self.menus = [m for m in msg.get('menus') or () if isinstance(m, dict)]
            self.state = RUNNING
            self._deadline = None
            self.problem = ''
            log.info('plugin %s running (%d commands, %d tools, %d menu items)', self.id,
                     len(self.commands), len(self.tools), len(self.menus))
            self.services.plugin_started(self)
        elif kind == 'result':
            entry = self._pending.pop(msg.get('rid'), None)
            if entry:
                entry[0](msg.get('value'), msg.get('error'))
        elif kind == 'call':
            self.services.call(self, msg.get('id'), str(msg.get('method') or ''),
                               msg.get('args') if isinstance(msg.get('args'), dict) else {})
        elif kind == 'error':
            self.problem = str(msg.get('message') or 'it failed')[:300]
            log.warning('plugin %s: %s', self.id, self.problem)

    def _exited(self, code):
        stopping = self.state == STOPPING
        self.proc = None
        self.commands, self.tools, self.menus = [], [], []
        self._fail_pending('the plugin stopped')
        if stopping or not self._want:
            self.state = OFF
            self.services.plugin_stopping(self, 'stopped')
            return
        if not self.problem:
            self.problem = f'it stopped unexpectedly (exit code {code}); see its log'
        self._crashed()

    def _crashed(self):
        if self.proc is not None:
            self.proc.kill()
            self.proc = None
        self.services.plugin_stopping(self, 'crashed')
        self._fail_pending('the plugin crashed')
        self.crashes += 1
        if self.crashes > len(RESTART_DELAYS):
            self.state = BROKEN
            log.warning('plugin %s keeps crashing; waiting for its files to change', self.id)
            return
        self.state = CRASHED
        self._restart_at = self.clock() + RESTART_DELAYS[self.crashes - 1]
        log.warning('plugin %s crashed (%s); restarting', self.id, self.problem)

    def log_tail(self, lines=40):
        try:
            with open(os.path.join(self.data_dir, 'plugin.log'), encoding='utf-8',
                      errors='replace') as f:
                return ''.join(f.readlines()[-lines:])
        except OSError:
            return ''
