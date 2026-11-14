"""AgentTask: a task done by an AI agent, safely.

    brain  the agent's CLI (Claude Code, logged in with your account) runs
           OUTSIDE the sandbox, like when you chat, with ALL of its own tools
           switched off;
    hands  its only tools are Robo's (robo/sandbox/worker/mcp_server.py), which
           the CLI starts through the platform's sandbox: no network, nothing of
           yours but what you granted.

So whatever the agent decides, it can only touch the task's workspace: the
files you let it read (read-only), COPIES of the folders you let it change,
and a fresh results folder for new things it makes. When it's done you see
the list of changes and only then are they applied (the usual review).
Your login never goes into the sandbox, and nothing in the sandbox can reach
the internet.

Everything the agent reads is sent to its provider (that's how it thinks),
which is why you choose exactly what it may read, and hidden folders in your
home (keys, passwords, browser profiles) can never be granted.
"""
import json
import logging
import os
import queue
import re
import shutil
import signal
import subprocess
import threading
import time

from robo.sandbox import LaunchSpec, Limits, Permissions, Workspace

from .base import Task

log = logging.getLogger(__name__)

MAX_TURNS = 60
TASK_SECONDS = 30 * 60
RESULTS_ROOT = os.path.expanduser('~/Robo')

SYSTEM_PROMPT = """\
You are the hands of Robo, a little desktop robot, doing a task the user asked for.
You work ONLY through the "robo" tools. They run in a sandbox:
  input/          files the user let you read (read-only)
  files/<name>/   COPIES of what the user let you change. Edit these in place; the
                  user reviews every change before it is applied to the real files.
  files/results/  put NEW things you make for the user here (reports, notes, lists...)
There is no internet. Python 3 and the usual command-line tools work in run_command.
PDFs: read_pdf gives you their text (a few pages at a time for long ones), and
look_at_pdf_page shows you a page as a picture (scanned PDFs, charts, tables).

Work carefully and stick to what was asked. Don't delete or rewrite more than the task
needs. Call report_progress now and then with a few words on what you're doing.
When you are done, end with a short spoken summary for Robo to say out loud: one or
two plain sentences, no markdown, no file paths longer than a name."""


def _die_with_robo():
    """(Linux) If Robo itself dies, the agent he started is stopped too."""
    try:
        import ctypes
        ctypes.CDLL('libc.so.6', use_errno=True).prctl(1, signal.SIGTERM)   # PR_SET_PDEATHSIG
    except Exception:
        pass


class TaskRefused(ValueError):
    """The request can't be granted (a path is missing or not allowed)."""


def _forbidden(path):
    """Paths an agent task may never be given: your home folder itself and the
    hidden folders in it (ssh keys, keyrings, browser profiles, app logins)."""
    home = os.path.realpath(os.path.expanduser('~'))
    p = os.path.realpath(path)
    if p in (home, os.path.sep):
        return 'the whole home folder'
    if p.startswith(home + os.sep):
        first = os.path.relpath(p, home).split(os.sep)[0]
        if first.startswith('.'):
            return f'hidden folders like ~/{first}'
    for secret in ('/etc/shadow', '/root', '/proc', '/sys', '/dev'):
        if p == secret or p.startswith(secret + os.sep):
            return p
    return None


def resolve_paths(paths):
    """'~/Downloads' -> absolute, existing, allowed paths (raises TaskRefused)."""
    out = []
    for raw in paths or ():
        p = os.path.realpath(os.path.expanduser(str(raw).strip()))
        if not os.path.exists(p):
            raise TaskRefused(f"I couldn't find {raw}")
        why = _forbidden(p)
        if why:
            raise TaskRefused(f"I'm not allowed to touch {why}")
        if p not in out:
            out.append(p)
    return tuple(out)


def short_title(goal, limit=48):
    goal = ' '.join(str(goal).split())
    return goal if len(goal) <= limit else goal[:limit].rsplit(' ', 1)[0] + '…'


class AgentTask(Task):
    kind = 'agent'

    def __init__(self, goal, env, read=(), write=(), agent=None):
        super().__init__(short_title(goal))
        self.goal = ' '.join(str(goal).split())
        self.env = env
        self.agent = agent
        stamp = time.strftime('%Y-%m-%d %H%M')
        name = re.sub(r'[^\w .,-]', '', self.title.rstrip('…'))[:40].strip() or 'task'
        self.results_dir = os.path.join(RESULTS_ROOT, f'{stamp} {name}')
        self.permissions = Permissions(read=tuple(read), write=tuple(write),
                                       max_seconds=TASK_SECONDS)
        self.workspace = None
        self.changes = None
        self.note = ''                   # what it's doing now (from report_progress / tools)
        self.steps = 0
        self._proc = None
        self._events = queue.Queue()
        self._fraction = None
        self._events_seen = 0
        self.trusted = ()                # Robo's own folders it may read (see DesignTask)

    # ------------------------------------------------------------ what you're asked
    def approval_lines(self):
        lines = [f'Do: {self.goal}', f'With: {self.agent.name if self.agent else "?"} '
                 '(it can only use Robo\'s sandboxed tools; no internet)']
        lines += self.permissions.describe()
        lines.append(f'New files go to (you review first): {self.results_dir}')
        if self.permissions.read or self.permissions.write:
            lines.append(f'Note: what it reads is sent to {self.agent.name if self.agent else "the AI"}.')
        return lines

    def progress(self, now):
        return self._fraction

    # ------------------------------------------------------------ lifecycle
    def on_start(self, now):
        problem = self.env.unavailable_reason()
        if problem is None and (self.agent is None or not self.agent.supports_tasks):
            problem = (f'{self.agent.name} {self.agent.tasks_unsupported}' if self.agent
                       else 'no AI brain is set up (Settings → AI brain)')
        if problem is None and not self.agent.executable():
            problem = f'{self.agent.program} is not installed'
        if problem is None:
            for p in self.permissions.read + self.permissions.write:
                if _forbidden(p) and p not in self.trusted:
                    problem = f'not allowed: {p}'
        if problem:
            self.fail(now, problem)
            return
        backend = self.env.sandbox
        try:
            os.makedirs(self.results_dir, exist_ok=True)
            perms = Permissions(read=self.permissions.read,
                                write=self.permissions.write + (self.results_dir,),
                                max_seconds=self.permissions.max_seconds)
            errors = perms.validate()
            if errors:
                raise RuntimeError('; '.join(errors))
            os.makedirs(self.env.workspace_root, mode=0o700, exist_ok=True)
            self.workspace = Workspace.create(self.env.workspace_root, perms,
                                              copy_inputs=not backend.supports_mounts)
            # the results folder (granted last) is always files/results in the sandbox
            ws, g = self.workspace, self.workspace.grants[-1]
            name = next(n for n, rel in ws.files.items()
                        if os.path.join(ws.work, rel) == g.staged)
            if name != 'results':
                target = os.path.join(ws.work, 'files', 'results')
                os.rename(g.staged, target)
                g.staged = target
                del ws.files[name]
                ws.files['results'] = os.path.join('files', 'results')
            os.makedirs(os.path.join(self.workspace.work, '.robo'), exist_ok=True)
            spec = LaunchSpec(work_dir=self.workspace.work,
                              read_only=tuple(self.workspace.read_only),
                              log_path=self.workspace.log_path,
                              limits=Limits(perms.memory_mb, perms.max_processes,
                                            perms.max_file_mb),
                              entry='mcp_server.py')
            launch = backend.stdio_command(spec)
            if launch is None:
                raise RuntimeError(f"the {backend.name} sandbox can't run agent tools")
            argv, server_env = launch
            config = os.path.join(self.workspace.path, 'mcp.json')
            with open(config, 'w') as f:
                json.dump({'mcpServers': {'robo': {'type': 'stdio', 'command': argv[0],
                                                   'args': argv[1:], 'env': server_env}}}, f)
            cwd = os.path.join(self.workspace.path, 'agent')       # an empty folder
            os.makedirs(cwd, exist_ok=True)
            cmd = self.agent.task_command(self._prompt(), SYSTEM_PROMPT, config, MAX_TURNS)
            cmd[0] = self.agent.executable()
            with open(os.path.join(self.workspace.path, 'agent.log'), 'ab') as errlog:
                self._proc = subprocess.Popen(cmd, cwd=cwd, env=self.agent.env(),
                                              stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                              stderr=errlog, text=True, start_new_session=True,
                                              preexec_fn=_die_with_robo if os.name == 'posix'
                                              else None)
            threading.Thread(target=self._read, args=(self._proc,), daemon=True).start()
        except Exception as e:
            log.exception('could not start agent task %s', self.id)
            self.fail(now, f'could not start: {e}')
            return
        log.info('agent task %s (%s) in %s', self.id, self.agent.name, self.workspace.path)

    def _prompt(self):
        ws = self.workspace
        have = [f'input/{n} (read only)' for n in ws.inputs] + \
               [f'files/{n} (a copy you may change)' for n in ws.files if n != 'results']
        where = ('You have: ' + ', '.join(have) + '.') if have else \
            'The user gave you no files; make what they asked for in files/results/.'
        return f'The task: {self.goal}\n\n{where}'

    def _read(self, proc):
        for line in proc.stdout:
            ev = self.agent.task_event(line)
            if ev:
                for e in ev if isinstance(ev, list) else [ev]:
                    self._events.put(e)
        proc.wait()
        self._events.put({'kind': 'exit', 'code': proc.returncode})

    # pausing: the agent keeps thinking while you chat with Robo (stopping it
    # mid-request would just break its connection); the time doesn't count.
    def on_abort(self, now):
        self._stop()
        self._discard()

    def on_fail(self, now):
        log.warning('agent task %s failed: %s', self.id, self.error)
        self._stop()
        self._discard()

    def on_done(self, now):
        self._stop()
        if self.workspace is not None:
            self.changes = self.workspace.changes()
            if not self.changes:
                self.cleanup()

    def cleanup(self):
        """After the review: remove the results folder if nothing ended up in it."""
        try:
            if os.path.isdir(self.results_dir) and not os.listdir(self.results_dir):
                os.rmdir(self.results_dir)
        except OSError:
            pass

    def _discard(self):
        if self.workspace is not None:
            self.workspace.discard()
        self.cleanup()

    def _stop(self):
        p = self._proc
        if p is not None and p.poll() is None:
            for sig in (signal.SIGTERM, signal.SIGKILL):
                try:
                    os.killpg(p.pid, sig)
                except (ProcessLookupError, PermissionError):
                    break
                try:
                    p.wait(timeout=2)
                    break
                except subprocess.TimeoutExpired:
                    continue

    # ------------------------------------------------------------ per frame
    def is_done(self, now):
        if self._proc is None:
            return False
        if self.worked_seconds(now) > self.permissions.max_seconds:
            self.fail(now, f'took longer than {self.permissions.max_seconds / 60:.0f} minutes')
            return False
        self._read_progress()
        while True:
            try:
                ev = self._events.get_nowait()
            except queue.Empty:
                return False
            kind = ev.get('kind')
            if kind == 'tool':
                self.steps += 1
                if ev['name'] != 'report_progress':
                    self.note = self.note or ev['name'].replace('_', ' ')
                log.info('task %s: %s %s', self.id, ev['name'],
                         json.dumps(ev.get('input'))[:160])
            elif kind == 'text':
                log.info('task %s says: %s', self.id, ev['text'][:200])
            elif kind == 'result':
                from robo.agents.usage import LEDGER
                LEDGER.record('design' if self.kind == 'design' else 'task', ev.get('usage'))
                if ev['ok']:
                    self.result = ev['text'].strip()[:600] or 'All done!'
                    return True
                self.fail(now, ev['text'][:300] or 'the agent gave up')
                return False
            elif kind == 'exit':
                self.fail(now, f'{self.agent.name} stopped unexpectedly (exit code {ev["code"]})')
                return False

    def _read_progress(self):
        """report_progress notes, written by the tool server inside the sandbox."""
        path = os.path.join(self.workspace.work, '.robo', 'events.jsonl')
        try:
            with open(path, encoding='utf-8') as f:
                lines = f.readlines()[self._events_seen:self._events_seen + 200]
        except OSError:
            return
        self._events_seen += len(lines)
        for line in lines:
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if ev.get('tool') == 'report_progress':
                self.note = str(ev.get('note', ''))[:200]
                if isinstance(ev.get('fraction'), (int, float)):
                    self._fraction = max(0.0, min(1.0, float(ev['fraction'])))
                log.info('task %s: %s', self.id, self.note)
