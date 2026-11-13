"""Broker: the only way out of the sandbox.

The worker has no network and sees none of your files. When it needs
something from outside it sends a request and Robo (outside the sandbox)
checks it against the task's Permissions before doing it. Today there is
one request:

    {'type': 'request', 'id': 7, 'op': 'fetch', 'url': 'https://...'}
        Download a file into work/downloads/. Allowed only for hosts in
        Permissions.hosts. Redirects to other hosts are refused too.

Answers go back as {'type': 'reply', 'id': 7, 'ok': true, 'value': ...}
or {'ok': false, 'error': '...'}. Slow work happens on a thread; the
replies are collected with take_replies() on the main thread.
"""
import os
import queue
import re
import threading
import urllib.error
import urllib.request
from urllib.parse import unquote, urlsplit

FETCH_TIMEOUT = 30
USER_AGENT = 'robo-task/1.0'


class Denied(Exception):
    pass


class _CheckedRedirects(urllib.request.HTTPRedirectHandler):
    def __init__(self, permissions):
        self.permissions = permissions

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not self.permissions.allows_url(newurl):
            raise Denied(f'redirect to a host you did not allow: {urlsplit(newurl).netloc}')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Broker:
    def __init__(self, permissions, workspace):
        self.permissions = permissions
        self.workspace = workspace
        self._replies = queue.Queue()
        self._lock = threading.Lock()

    def handle(self, msg):
        """A request from the worker (main thread). The reply comes via take_replies()."""
        rid = msg.get('id')
        op = msg.get('op')
        if op == 'fetch':
            url = str(msg.get('url', ''))
            if not self.permissions.allows_url(url):
                self._reply(rid, error=f'not allowed to download from {urlsplit(url).netloc or url}')
                return
            threading.Thread(target=self._fetch, args=(rid, url), daemon=True).start()
        else:
            self._reply(rid, error=f'unknown request: {op}')

    def take_replies(self):
        out = []
        while True:
            try:
                out.append(self._replies.get_nowait())
            except queue.Empty:
                return out

    def _reply(self, rid, value=None, error=None):
        if error is None:
            self._replies.put({'type': 'reply', 'id': rid, 'ok': True, 'value': value})
        else:
            self._replies.put({'type': 'reply', 'id': rid, 'ok': False, 'error': error})

    # ------------------------------------------------------------ fetch (thread)
    def _fetch(self, rid, url):
        limit = self.permissions.max_download_mb * 1024 * 1024
        rel = None
        try:
            opener = urllib.request.build_opener(_CheckedRedirects(self.permissions))
            req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
            with opener.open(req, timeout=FETCH_TIMEOUT) as resp:
                rel = self._target(url)
                path = os.path.join(self.workspace.work, rel)
                size = 0
                with open(path, 'wb') as f:
                    for chunk in iter(lambda: resp.read(1 << 16), b''):
                        size += len(chunk)
                        if size > limit:
                            raise Denied(f'bigger than {self.permissions.max_download_mb} MB')
                        f.write(chunk)
            self._reply(rid, value=rel)
        except (Denied, urllib.error.URLError, OSError, ValueError) as e:
            if rel:
                try:
                    os.remove(os.path.join(self.workspace.work, rel))
                except OSError:
                    pass
            reason = getattr(e, 'reason', None) or e
            self._reply(rid, error=f'download failed: {reason}')

    def _target(self, url):
        name = os.path.basename(unquote(urlsplit(url).path)) or 'download'
        name = re.sub(r'[^A-Za-z0-9._-]', '_', name).lstrip('.') or 'download'
        folder = os.path.join(self.workspace.work, 'downloads')
        with self._lock:
            base, ext = os.path.splitext(name)
            candidate, i = name, 2
            while os.path.exists(os.path.join(folder, candidate)):
                candidate, i = f'{base}-{i}{ext}', i + 1
            open(os.path.join(folder, candidate), 'wb').close()   # reserve it
        return os.path.join('downloads', candidate)
