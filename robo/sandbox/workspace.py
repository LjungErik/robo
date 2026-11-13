"""Workspace: a task's own folder, and the change review.

    <root>/<id>/
        worker.log           what the worker printed (outside its reach)
        work/                the worker's current folder, its only writable place
            input/<name>     files / folders you let it read
            files/<name>     COPIES of what you let it change
            downloads/       what the broker fetched for it

Files you let it change are never touched directly. The task edits copies,
and when it's done changes() compares them with how things were. You see
the list and only then does ChangeSet.apply() copy the edits back. Edits
are skipped if you changed the same file meanwhile, and symlinks or other
special files the task made are never copied out.
"""
import hashlib
import os
import shutil
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .backend import Mount

ADDED, MODIFIED, DELETED = 'added', 'modified', 'deleted'


class WorkspaceError(Exception):
    pass


def _sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 16), b''):
            h.update(chunk)
    return h.hexdigest()


def _regular_files(root):
    """rel path -> abs path of every regular file under root (symlinks skipped)."""
    if os.path.isfile(root) and not os.path.islink(root):
        return {'': root}
    found = {}
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if not os.path.islink(os.path.join(dirpath, d))]
        for name in filenames:
            p = os.path.join(dirpath, name)
            if os.path.isfile(p) and not os.path.islink(p):
                found[os.path.relpath(p, root)] = p
    return found


def _unique_name(path, taken):
    base = os.path.basename(os.path.normpath(path)) or 'item'
    name, i = base, 2
    while name in taken:
        name, i = f'{base}-{i}', i + 1
    taken.add(name)
    return name


@dataclass
class Grant:
    """One file / folder you let the task change."""
    original: str                        # real path on your computer
    staged: str                          # the copy inside the workspace
    snapshot: Dict[str, str] = field(default_factory=dict)   # rel -> sha256 when copied


@dataclass(frozen=True)
class Change:
    kind: str                            # added / modified / deleted
    grant: Grant
    rel: str

    @property
    def original_path(self):
        return os.path.join(self.grant.original, self.rel) if self.rel else self.grant.original

    @property
    def staged_path(self):
        return os.path.join(self.grant.staged, self.rel) if self.rel else self.grant.staged


@dataclass
class ChangeSet:
    changes: List[Change]

    def __bool__(self):
        return bool(self.changes)

    def describe(self, limit=20) -> List[str]:
        lines = [f'{c.kind}: {c.original_path}' for c in self.changes[:limit]]
        if len(self.changes) > limit:
            lines.append(f'... and {len(self.changes) - limit} more')
        return lines

    def apply(self) -> Tuple[List[Change], List[Tuple[Change, str]]]:
        """Copy the task's edits to your files. Returns (applied, skipped with reason)."""
        applied, skipped = [], []
        for c in self.changes:
            reason = self._check(c)
            if reason:
                skipped.append((c, reason))
                continue
            target = c.original_path
            if c.kind == DELETED:
                os.remove(target)
            else:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                shutil.copy2(c.staged_path, target)
            applied.append(c)
        return applied, skipped

    @staticmethod
    def _check(c):
        root = os.path.realpath(c.grant.original)
        target = c.original_path
        parent = os.path.realpath(os.path.dirname(target)) if c.rel else os.path.dirname(root)
        if c.rel and not (parent == root or parent.startswith(root + os.sep)):
            return 'outside the folder you allowed'
        if os.path.islink(target):
            return 'is a symlink'
        before = c.grant.snapshot.get(c.rel)
        now = _sha256(target) if os.path.isfile(target) else None
        if now != before:
            return 'you changed it meanwhile'
        if c.kind != DELETED:
            src = c.staged_path
            if os.path.islink(src) or not os.path.isfile(src):
                return 'not a regular file'
        return None


class Workspace:
    def __init__(self, path):
        self.path = path
        self.work = os.path.join(path, 'work')
        self.log_path = os.path.join(path, 'worker.log')
        self.read_only: List[Mount] = []     # for backends that can mount
        self.inputs: Dict[str, str] = {}     # name -> path relative to work/
        self.files: Dict[str, str] = {}
        self.grants: List[Grant] = []

    @classmethod
    def create(cls, root, permissions, copy_inputs=False):
        """Make a fresh workspace and stage what `permissions` grants."""
        wid = time.strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:6]
        ws = cls(os.path.join(root, wid))
        for sub in ('input', 'files', 'downloads'):
            os.makedirs(os.path.join(ws.work, sub), mode=0o700)
        try:
            ws._stage(permissions, copy_inputs)
        except Exception:
            ws.discard()
            raise
        return ws

    def _stage(self, permissions, copy_inputs):
        taken = set()
        for p in permissions.read:
            src = os.path.realpath(p)
            name = _unique_name(src, taken)
            rel = os.path.join('input', name)
            dest = os.path.join(self.work, rel)
            if copy_inputs:
                self._copy(src, dest, permissions.max_copy_mb)
            else:                            # mount point for the backend
                if os.path.isdir(src):
                    os.makedirs(dest)
                else:
                    open(dest, 'w').close()
                self.read_only.append(Mount(src, rel))
            self.inputs[name] = rel
        taken = set()
        for p in permissions.write:
            src = os.path.realpath(p)
            name = _unique_name(src, taken)
            rel = os.path.join('files', name)
            dest = os.path.join(self.work, rel)
            snapshot = self._copy(src, dest, permissions.max_copy_mb)
            self.grants.append(Grant(src, dest, snapshot))
            self.files[name] = rel

    @staticmethod
    def _copy(src, dest, max_mb):
        """Copy regular files only. Returns rel -> sha256 of the originals."""
        files = _regular_files(src)
        total = sum(os.path.getsize(p) for p in files.values())
        if total > max_mb * 1024 * 1024:
            raise WorkspaceError(f'{src} is bigger than {max_mb} MB')
        snapshot = {}
        if os.path.isdir(src):
            os.makedirs(dest, exist_ok=True)
        for rel, p in files.items():
            target = os.path.join(dest, rel) if rel else dest
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(p, target)
            snapshot[rel] = _sha256(p)
        return snapshot

    def changes(self) -> ChangeSet:
        """What the task changed in the copies, compared to when they were made."""
        out = []
        for g in self.grants:
            now = {rel: p for rel, p in _regular_files(g.staged).items()} \
                if os.path.exists(g.staged) else {}
            for rel, p in sorted(now.items()):
                if rel not in g.snapshot:
                    out.append(Change(ADDED, g, rel))
                elif _sha256(p) != g.snapshot[rel]:
                    out.append(Change(MODIFIED, g, rel))
            for rel in sorted(g.snapshot):
                if rel not in now:
                    out.append(Change(DELETED, g, rel))
        return ChangeSet(out)

    def discard(self):
        """Delete the workspace (it only ever holds copies)."""
        shutil.rmtree(self.path, ignore_errors=True)

    @staticmethod
    def prune(root, keep=20):
        """Keep only the newest `keep` workspaces."""
        try:
            entries = sorted(e for e in os.listdir(root) if os.path.isdir(os.path.join(root, e)))
        except OSError:
            return
        for e in entries[:-keep] if keep else entries:
            shutil.rmtree(os.path.join(root, e), ignore_errors=True)
