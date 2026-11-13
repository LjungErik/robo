"""SandboxedTask: a Task whose work runs in a sandboxed worker process.

    start   make a Workspace (stage what Permissions grant), launch the worker
            through the platform's SandboxBackend, send it the job
    pause   freeze the worker (and everything it started)
    resume  thaw it
    abort   kill it and delete its workspace (it only holds copies)
    done    the worker said 'done': `changes` holds what it changed in its
            copies of your files, for you to review (nothing is applied yet)

Every frame (is_done) it reads the worker's messages: progress, log lines,
requests (checked by the Broker) and the final result.
"""
import logging
import os
from dataclasses import dataclass, field
from typing import Optional

from robo.sandbox import DenyAll, Limits, LaunchSpec, Permissions, Workspace
from robo.sandbox.broker import Broker

from .base import Task

log = logging.getLogger(__name__)


def default_workspace_root():
    base = os.environ.get('XDG_DATA_HOME') or os.path.expanduser('~/.local/share')
    return os.path.join(base, 'robo', 'tasks')


@dataclass
class TaskEnvironment:
    """What tasks need from the platform (set up in robo/app.py)."""
    sandbox: Optional[object] = None             # robo.sandbox.SandboxBackend
    approver: object = field(default_factory=DenyAll)
    workspace_root: str = field(default_factory=default_workspace_root)

    def unavailable_reason(self):
        """None if tasks can run safely, else why not."""
        if self.sandbox is None:
            return "there's no sandbox for this kind of computer yet"
        return self.sandbox.check()


class SandboxedTask(Task):
    kind = 'sandboxed'

    def __init__(self, job, title, env, args=None, permissions=None):
        super().__init__(title)
        self.job = job
        self.args = dict(args or {})
        self.env = env
        self.permissions = permissions or Permissions()
        self.workspace: Optional[Workspace] = None
        self.process = None
        self.broker = None
        self.changes = None                  # ChangeSet once done
        self.output = None                   # whatever the job returned
        self._progress = 0.0

    def progress(self, now):
        return self._progress

    # ------------------------------------------------------------ lifecycle hooks
    def on_start(self, now):
        problem = self.env.unavailable_reason()
        errors = self.permissions.validate()
        if problem or errors:
            self.fail(now, problem or '; '.join(errors))
            return
        backend = self.env.sandbox
        try:
            os.makedirs(self.env.workspace_root, mode=0o700, exist_ok=True)
            self.workspace = Workspace.create(self.env.workspace_root, self.permissions,
                                              copy_inputs=not backend.supports_mounts)
            p = self.permissions
            spec = LaunchSpec(work_dir=self.workspace.work,
                              read_only=tuple(self.workspace.read_only),
                              log_path=self.workspace.log_path,
                              limits=Limits(p.memory_mb, p.max_processes, p.max_file_mb))
            self.process = backend.launch(spec)
        except Exception as e:
            log.exception('could not start task %s', self.id)
            self.fail(now, f'could not start: {e}')
            return
        self.broker = Broker(self.permissions, self.workspace)
        self.process.send({'type': 'start', 'job': self.job, 'args': self.args,
                           'inputs': self.workspace.inputs, 'files': self.workspace.files})
        log.info('task %s runs in %s (%s)', self.id, self.workspace.path, backend.name)

    def on_pause(self, now):
        if self.process:
            self.process.pause()

    def on_resume(self, now):
        if self.process:
            self.process.resume()

    def on_abort(self, now):
        self._stop(discard=True)

    def on_fail(self, now):
        log.warning('task %s failed: %s', self.id, self.error)
        self._stop(discard=True)

    def on_done(self, now):
        self._stop(discard=False)
        if self.workspace is not None:
            self.changes = self.workspace.changes()

    def _stop(self, discard):
        if self.process is not None:
            self.process.kill()
        if discard and self.workspace is not None:
            self.workspace.discard()

    # ------------------------------------------------------------ per frame
    def is_done(self, now):
        if self.process is None:
            return False
        if self.worked_seconds(now) > self.permissions.max_seconds:
            self.fail(now, f'took longer than {self.permissions.max_seconds:.0f} seconds')
            return False
        for reply in self.broker.take_replies():
            self.process.send(reply)
        exited = self.process.exit_code() is not None   # check before reading: no lost words
        for msg in self.process.receive():
            kind = msg.get('type')
            if kind == 'progress':
                try:
                    self._progress = max(0.0, min(1.0, float(msg.get('value', 0))))
                except (TypeError, ValueError):
                    pass
            elif kind == 'log':
                log.info('task %s: %s', self.id, str(msg.get('text', ''))[:500])
            elif kind == 'request':
                self.broker.handle(msg)
            elif kind == 'done':
                result = msg.get('result')
                self.result = result if isinstance(result, str) else None
                self.output = result
                self._progress = 1.0
                return True
            elif kind == 'error':
                self.fail(now, str(msg.get('message', 'unknown error'))[:300])
                return False
        if exited:
            self.fail(now, f'the worker stopped unexpectedly (exit code {self.process.exit_code()})')
        return False
