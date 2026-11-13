"""Linux sandbox: bubblewrap (bwrap), the sandbox Flatpak uses.

Each task worker runs as

    systemd-run --user --scope -p MemoryMax=.. -p TasksMax=.. -p CPUQuota=..   (limits)
      prlimit --fsize=.. --core=0                                               (file size)
        bwrap --unshare-all --disable-userns --cap-drop ALL --clearenv ...       (isolation)
          /usr/bin/python3 -I /opt/robo-worker/main.py

What the worker sees: /usr read-only (for Python), its work folder as
/work (read-write, current folder), the worker code at /opt/robo-worker
and the files you granted, both read-only, plus private /tmp, /proc and
/dev. Not your home folder, the network, D-Bus, the display, the keyring
or any of your environment variables. It runs as you (never root) and
bwrap sets no_new_privs, so sudo / pkexec / setuid programs can't elevate.

It deliberately does NOT use bwrap --new-session: the worker is started
in its own session by Popen (so it has no terminal to inject keys into)
and stays in that process group, so pause / resume / kill reach it.
"""
import logging
import os
import shutil
import subprocess

from robo.sandbox.backend import WORKER_DIR, PipeProcess, SandboxBackend

log = logging.getLogger(__name__)

PYTHON = '/usr/bin/python3'
SANDBOX_WORKER = '/opt/robo-worker'
CPU_QUOTA = '100%'           # at most one core
PROBE_TIMEOUT = 10


def _works(argv):
    try:
        return subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=PROBE_TIMEOUT).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


class BubblewrapBackend(SandboxBackend):
    name = 'bubblewrap'

    def __init__(self):
        self._checked = False
        self._problem = None
        self._systemd = False
        self._prlimit = None

    def check(self):
        if self._checked:
            return self._problem
        self._checked = True
        bwrap = shutil.which('bwrap')
        if not bwrap:
            self._problem = 'bubblewrap is not installed (sudo apt install bubblewrap)'
        elif not os.path.exists(PYTHON):
            self._problem = f'{PYTHON} is missing'
        elif not _works([bwrap, '--unshare-all', '--unshare-user', '--disable-userns',
                         '--die-with-parent',
                         '--ro-bind', '/', '/', 'true']):
            self._problem = ('bubblewrap is not allowed to create a sandbox here '
                             '(user namespaces may be blocked by AppArmor)')
        self._systemd = bool(shutil.which('systemd-run')) and _works(
            ['systemd-run', '--user', '--scope', '-q', '--collect', 'true'])
        self._prlimit = shutil.which('prlimit')
        if self._problem is None and not (self._systemd and self._prlimit):
            self._problem = ('systemd-run --user and prlimit are needed to limit memory, '
                             'processes and file sizes')
        if self._problem:
            log.warning('tasks are disabled: %s', self._problem)
        return self._problem

    def command(self, spec):
        """The full command line for a LaunchSpec (separate so tests can read it)."""
        lim = spec.limits
        argv = ['systemd-run', '--user', '--scope', '-q', '--collect',
                '-p', f'MemoryMax={lim.memory_mb}M', '-p', 'MemorySwapMax=0',
                '-p', f'TasksMax={lim.max_processes}', '-p', f'CPUQuota={CPU_QUOTA}',
                self._prlimit, f'--fsize={lim.max_file_mb * 1024 * 1024}', '--core=0', '--',
                'bwrap',
                '--unshare-all', '--unshare-user', '--disable-userns',
                '--die-with-parent', '--cap-drop', 'ALL',
                '--hostname', 'robo-task',
                '--clearenv', '--setenv', 'HOME', '/work', '--setenv', 'PATH', '/usr/bin',
                '--setenv', 'PYTHONDONTWRITEBYTECODE', '1', '--setenv', 'LANG', 'C.UTF-8',
                '--ro-bind', '/usr', '/usr',
                '--symlink', 'usr/bin', '/bin', '--symlink', 'usr/lib', '/lib',
                '--symlink', 'usr/lib64', '/lib64', '--symlink', 'usr/sbin', '/sbin',
                '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp',
                '--bind', spec.work_dir, '/work',
                '--ro-bind', WORKER_DIR, SANDBOX_WORKER]
        for m in spec.read_only:
            argv += ['--ro-bind', m.source, '/work/' + m.target]
        argv += ['--remount-ro', '/', '--chdir', '/work',
                 PYTHON, '-I', SANDBOX_WORKER + '/main.py']
        return argv

    def launch(self, spec):
        problem = self.check()
        if problem:
            raise RuntimeError(problem)
        env = {k: os.environ[k] for k in ('PATH', 'XDG_RUNTIME_DIR', 'DBUS_SESSION_BUS_ADDRESS')
               if k in os.environ}        # for systemd-run only; bwrap clears it
        logfile = open(spec.log_path or os.devnull, 'ab')
        try:
            popen = subprocess.Popen(self.command(spec), stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=logfile, env=env,
                                     text=True, start_new_session=True, close_fds=True)
        finally:
            logfile.close()
        return PipeProcess(popen)
