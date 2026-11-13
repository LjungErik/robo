"""Permissions: everything a task may touch beyond its own scratch folder.

A task declares what it needs up front. Robo asks you before starting a
task that needs anything (robo.sandbox.approval), and the grant only lives
as long as that task. With the default (empty) Permissions a task can only
see its own workspace: no files of yours, no network.
"""
import os
from dataclasses import dataclass
from typing import List, Tuple
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Permissions:
    read: Tuple[str, ...] = ()        # files / folders it may read (never change)
    write: Tuple[str, ...] = ()       # files / folders it may change: it works on a copy,
                                      #   and you review the changes before they're applied
    hosts: Tuple[str, ...] = ()       # where it may download from (see allows_url)
    max_seconds: float = 15 * 60      # working time before it is stopped
    memory_mb: int = 1024
    max_processes: int = 64
    max_file_mb: int = 512            # largest file it may write
    max_download_mb: int = 50         # per download
    max_copy_mb: int = 500            # total size of the folders it may change

    @property
    def needs_approval(self):
        return bool(self.read or self.write or self.hosts)

    def describe(self) -> List[str]:
        """One line per permission, for the approval dialog."""
        lines = [f'Read: {p}' for p in self.read]
        lines += [f'Change (you review first): {p}' for p in self.write]
        lines += [f'Download from: {h}' for h in self.hosts]
        return lines

    def validate(self) -> List[str]:
        """Problems that make this request unusable (empty = fine)."""
        errors = []
        for p in self.read + self.write:
            if not os.path.isabs(p):
                errors.append(f'not an absolute path: {p}')
            elif not os.path.exists(p):
                errors.append(f'does not exist: {p}')
            elif os.path.realpath(p) == os.path.sep:
                errors.append('the whole disk can not be granted')
        for h in self.hosts:
            if not _parse_host_rule(h):
                errors.append(f'not a valid host: {h}')
        return errors

    def allows_url(self, url):
        """May the task download `url`?

        Host rules: 'example.com' (https only), '*.example.com' (its
        subdomains, https only) or 'http://127.0.0.1:8000' (exactly that
        scheme, host and port)."""
        try:
            u = urlsplit(url)
            port = u.port
        except ValueError:
            return False
        host = (u.hostname or '').lower()
        if u.scheme not in ('http', 'https') or not host or u.username or u.password:
            return False
        for rule in self.hosts:
            scheme, rule_host, rule_port = _parse_host_rule(rule) or (None, None, None)
            if rule_host is None:
                continue
            if scheme is not None:
                if (u.scheme, host, port or _default_port(u.scheme)) == \
                        (scheme, rule_host, rule_port or _default_port(scheme)):
                    return True
            elif u.scheme == 'https' and port in (None, 443):
                if rule_host.startswith('*.'):
                    if host.endswith(rule_host[1:]):
                        return True
                elif host == rule_host:
                    return True
        return False


def _default_port(scheme):
    return 443 if scheme == 'https' else 80


def _parse_host_rule(rule):
    """-> (scheme or None, host, port or None), or None if invalid."""
    rule = rule.strip().lower()
    if '://' in rule:
        try:
            u = urlsplit(rule)
            port = u.port
        except ValueError:
            return None
        if u.scheme not in ('http', 'https') or not u.hostname or u.path not in ('', '/'):
            return None
        return u.scheme, u.hostname, port
    if not rule or '/' in rule or ':' in rule or rule in ('*', '*.'):
        return None
    return None, rule, None
