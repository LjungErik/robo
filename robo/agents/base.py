"""AgentBackend: one AI provider, reached through its own command-line agent.

Robo never handles API keys or tokens. Each backend runs the provider's
official CLI (Claude Code, OpenAI Codex, Gemini CLI), which keeps its own
login: you sign in once in a terminal with your Claude / ChatGPT / Google
account, and Robo just asks that program questions. So a Claude Pro
subscription works the same way it does in Claude Code.

The agent runs with no tools, in an empty folder of Robo's own: for now it
only talks, it can't read your files or run commands.

    status()            -> AgentStatus (installed? logged in? how to fix)
    ask(prompt, system) -> AgentAnswer (blocking: call it from a worker thread)
    cancel()            -> stop the request that is running (from any thread)
    forget()            -> start a fresh conversation next time
"""
import json
import logging
import os
import shutil
import signal
import subprocess
import threading
from dataclasses import dataclass
from typing import List, Optional, Tuple

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 120.0            # seconds for one answer
MAX_OUTPUT = 4 * 1024 * 1024       # bytes we read from the CLI (it only prints one answer)
# Never handed to the agent CLI: with these set it would bill an API key
# instead of using your subscription login.
SCRUBBED_ENV = ('ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN', 'OPENAI_API_KEY', 'CODEX_API_KEY',
                'GEMINI_API_KEY', 'GOOGLE_API_KEY')


class AgentError(Exception):
    """Something went wrong; `spoken` is what Robo says about it."""

    def __init__(self, message, spoken=None):
        super().__init__(message)
        self.spoken = spoken or "Hmm, I couldn't reach my AI brain just now."


@dataclass(frozen=True)
class AgentStatus:
    ready: bool
    installed: bool
    logged_in: Optional[bool]       # None = can't tell without trying
    detail: str                     # one line for the settings window / logs
    fix: str = ''                   # what to do about it (shown to you)


@dataclass(frozen=True)
class AgentAnswer:
    text: str
    session: Optional[str] = None   # provider session id, to continue the conversation


class AgentBackend:
    id = ''
    name = ''
    program = ''                    # the CLI to run
    install_hint = ''
    login_hint = ''
    remembers = False               # True: the CLI keeps the conversation (session ids)
    # Tasks: the CLI can be told to use ONLY Robo's sandboxed tools (MCP) and none of
    # its own. A CLI that can't switch its own file / shell tools off must say False.
    supports_tasks = False
    tasks_unsupported = 'can only chat for now'

    def __init__(self, workdir, model='', timeout=DEFAULT_TIMEOUT):
        self.workdir = workdir
        self.model = model
        self.timeout = timeout
        self.session = None          # provider session id while a conversation lasts
        self.history: List[Tuple[str, str]] = []   # (user, robo) for CLIs that don't remember
        self._proc = None
        self._lock = threading.Lock()
        self._cancelled = False

    # ------------------------------------------------------------ provider hooks
    def executable(self):
        return shutil.which(self.program)

    def status(self) -> AgentStatus:
        raise NotImplementedError

    def command(self, prompt, system) -> List[str]:
        """argv for one question."""
        raise NotImplementedError

    def parse(self, stdout, stderr, returncode) -> AgentAnswer:
        raise NotImplementedError

    def task_command(self, prompt, system, mcp_config, max_turns) -> List[str]:
        """argv that works on a task using only the MCP server in `mcp_config`."""
        raise NotImplementedError

    def task_event(self, line):
        """One line the task command printed -> dict or None:
        {'kind': 'tool', 'name': ...}, {'kind': 'text', 'text': ...},
        {'kind': 'result', 'text': ..., 'ok': bool}"""
        return None

    # ------------------------------------------------------------ public
    def ask(self, prompt, system):
        exe = self.executable()
        if not exe:
            raise AgentError(f'{self.program} is not installed',
                             f"I can't find {self.name} on this computer. "
                             f'Check my settings to set it up!')
        os.makedirs(self.workdir, exist_ok=True)
        argv = self.command(self._with_history(prompt), system)
        argv[0] = exe
        stdout, stderr, code = self._run(argv)
        answer = self.parse(stdout, stderr, code)
        if answer.session:
            self.session = answer.session
        if not self.remembers:
            self.history.append((prompt, answer.text))
            del self.history[:-12]
        return answer

    def cancel(self):
        with self._lock:
            self._cancelled = True
            proc = self._proc
        if proc is not None and proc.poll() is None:
            _kill(proc)

    def forget(self):
        self.session = None
        self.history.clear()

    # ------------------------------------------------------------ helpers
    def _with_history(self, prompt):
        """CLIs without sessions get the recent conversation in the prompt."""
        if self.remembers or not self.history:
            return prompt
        lines = ['Our conversation so far:']
        for said, answered in self.history:
            lines += [f'Human: {said}', f'Robo: {answered}']
        lines += ['', f'Human now says: {prompt}']
        return '\n'.join(lines)

    def env(self):
        env = {k: v for k, v in os.environ.items() if k not in SCRUBBED_ENV}
        env.setdefault('NO_COLOR', '1')
        return env

    def _run(self, argv):
        log.debug('agent: %s', ' '.join(argv[:3]))
        with self._lock:
            self._cancelled = False
            self._proc = proc = subprocess.Popen(
                argv, cwd=self.workdir, env=self.env(), stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        try:
            out, err = proc.communicate(timeout=self.timeout)
        except subprocess.TimeoutExpired:
            _kill(proc)
            proc.communicate()
            raise AgentError(f'{self.program} took longer than {self.timeout:.0f} s',
                             'My AI brain is taking way too long. Let us try again later!')
        finally:
            with self._lock:
                self._proc = None
        if self._cancelled:
            raise AgentCancelled()
        return (out[:MAX_OUTPUT].decode('utf-8', 'replace'),
                err[:MAX_OUTPUT].decode('utf-8', 'replace'), proc.returncode)

    def _quick(self, argv, timeout=10):
        """Run a short status command; (returncode, stdout) or (None, '')."""
        try:
            r = subprocess.run(argv, cwd=self.workdir if os.path.isdir(self.workdir) else None,
                               env=self.env(), stdin=subprocess.DEVNULL, capture_output=True,
                               timeout=timeout)
            return r.returncode, r.stdout.decode('utf-8', 'replace')
        except (OSError, subprocess.TimeoutExpired):
            return None, ''


class AgentCancelled(Exception):
    """The request was cancelled (he was hushed); nothing to say."""


def _kill(proc):
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass


def load_json(text):
    """The last JSON object printed (CLIs sometimes print a warning line first)."""
    text = text.strip()
    try:
        return json.loads(text)
    except ValueError:
        pass
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line.startswith('{'):
            try:
                return json.loads(line)
            except ValueError:
                continue
    return None
