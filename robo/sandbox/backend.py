"""The contract every OS-specific sandbox implements.

A SandboxBackend starts the task worker (robo/sandbox/worker/main.py) in
isolation and hands back a SandboxProcess to talk to it. Linux uses
bubblewrap (robo/platform/linux/sandbox.py). A port registers its backend
by returning it from Platform.sandbox().

Every backend MUST make sure the worker:
  1. runs as the normal user, and can never gain more rights (no root, no
     setuid, no sudo/pkexec, no capabilities);
  2. can read and write only its work folder (LaunchSpec.work_dir), read the
     worker code, read the files in LaunchSpec.read_only, and read whatever
     system libraries the Python interpreter needs. Nothing else of yours:
     no home folder, no other disks;
  3. has no network at all (downloads go through robo.sandbox.broker);
  4. can't reach your desktop session: no display server, no D-Bus, no
     keychain / keyring, no ssh-agent, no environment variables of yours;
  5. stays inside the memory / process / file-size Limits;
  6. can be paused, resumed and killed as a whole (child processes too).

tests/test_sandbox.py has a conformance suite (SandboxConformance) that
checks these rules from inside the sandbox. Run it against a new backend.

Ideas for other systems (not built yet):
  Windows  an AppContainer process (CreateProcess with SECURITY_CAPABILITIES
           and no capabilities = no network, no user files), the work folder
           granted to the AppContainer SID by ACL, read-only inputs copied in
           (supports_mounts = False), and a Job Object for the limits,
           kill-on-close and suspend / resume.
  macOS    sandbox-exec with a deny-by-default profile (allow reading the
           system and Python, writing only the work folder, no network),
           setrlimit for the limits, PipeProcess for pause / resume / kill.
"""
import json
import os
import queue
import signal
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Tuple

# The code that runs inside the sandbox. Backends expose this folder
# read-only and run main.py from it with the system Python.
WORKER_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'worker')
MAX_MESSAGE_BYTES = 1 << 20


@dataclass(frozen=True)
class Mount:
    source: str              # absolute path on your computer
    target: str              # path relative to the work folder, e.g. 'input/notes.txt'


@dataclass(frozen=True)
class Limits:
    memory_mb: int = 1024
    max_processes: int = 64
    max_file_mb: int = 512


@dataclass(frozen=True)
class LaunchSpec:
    work_dir: str                        # becomes the worker's (only writable) current folder
    read_only: Tuple[Mount, ...] = ()    # extra files it may read, shown inside work_dir
    log_path: Optional[str] = None       # where the worker's stderr goes
    limits: Limits = Limits()
    entry: str = 'main.py'               # which worker program: main.py, or mcp_server.py
                                         #   (the tools an AI agent task uses)


class SandboxProcess(ABC):
    """A running worker. Messages are dicts (JSON). Used on the main thread."""

    @abstractmethod
    def send(self, message: dict) -> None: ...

    @abstractmethod
    def receive(self) -> List[dict]:
        """Every message that arrived since the last call (never blocks)."""

    @abstractmethod
    def pause(self) -> None: ...

    @abstractmethod
    def resume(self) -> None: ...

    @abstractmethod
    def kill(self) -> None:
        """Stop the worker and everything it started, right now."""

    @abstractmethod
    def exit_code(self) -> Optional[int]:
        """None while running."""


class SandboxBackend(ABC):
    name = 'sandbox'
    supports_mounts = True     # False: read-only inputs are copied into the work folder

    @abstractmethod
    def check(self) -> Optional[str]:
        """None if tasks can run safely here, otherwise why not (plain words)."""

    @abstractmethod
    def launch(self, spec: LaunchSpec) -> SandboxProcess: ...

    def stdio_command(self, spec: LaunchSpec):
        """(argv, env) that start the worker in the sandbox when SOMEONE ELSE runs it,
        talking over stdin / stdout: an AI agent's CLI launches Robo's MCP tool
        server this way (robo/tasks/agent_task.py). None if not supported."""
        return None


class PipeProcess(SandboxProcess):
    """A subprocess.Popen talking JSON lines over stdin / stdout.

    The Popen must be started in its own process group (start_new_session
    on POSIX) so pause / resume / kill reach every process it started.
    POSIX signals are used; a Windows backend overrides pause / resume /
    kill (e.g. with a Job Object).
    """

    def __init__(self, popen):
        self.popen = popen
        self._inbox = queue.Queue()
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()

    def _read(self):
        out = self.popen.stdout
        while True:
            line = out.readline(MAX_MESSAGE_BYTES + 1)
            if not line:
                return
            if len(line) > MAX_MESSAGE_BYTES or not line.endswith('\n'):
                self._inbox.put({'type': 'error', 'message': 'message too long'})
                self.kill()
                return
            try:
                msg = json.loads(line)
            except ValueError:
                msg = None
            if not isinstance(msg, dict):
                self._inbox.put({'type': 'error', 'message': 'garbled message from the worker'})
                self.kill()
                return
            self._inbox.put(msg)

    def send(self, message):
        try:
            self.popen.stdin.write(json.dumps(message) + '\n')
            self.popen.stdin.flush()
        except (OSError, ValueError):
            pass                         # it died; exit_code() tells

    def receive(self):
        msgs = []
        while True:
            try:
                msgs.append(self._inbox.get_nowait())
            except queue.Empty:
                return msgs

    def _signal(self, sig):
        try:
            os.killpg(self.popen.pid, sig)
        except (ProcessLookupError, PermissionError):
            pass

    def pause(self):
        self._signal(signal.SIGSTOP)

    def resume(self):
        self._signal(signal.SIGCONT)

    def kill(self):
        if self.popen.poll() is None:
            self._signal(signal.SIGKILL)
            self._signal(signal.SIGCONT)      # a stopped group must wake up to die
        try:
            self.popen.wait(timeout=2)
        except Exception:
            pass
        for f in (self.popen.stdin, self.popen.stdout):
            try:
                f.close()
            except Exception:
                pass

    def exit_code(self):
        code = self.popen.poll()
        if code is not None and self._reader.is_alive():
            self._reader.join(timeout=0.5)    # don't lose its last words
        return code
