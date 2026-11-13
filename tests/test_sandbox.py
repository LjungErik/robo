"""Sandbox tests. The real-sandbox ones need bubblewrap (skipped otherwise).

To check a new backend (Windows, macOS...), subclass SandboxConformance
with make_backend() returning it: the same rules must hold everywhere.
"""
import http.server
import os
import random
import shutil
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from robo.sandbox import Permissions, Workspace  # noqa: E402
from robo.sandbox.broker import Broker  # noqa: E402
from robo.tasks import SandboxedTask, TaskEnvironment, make_task  # noqa: E402


class PermissionsTest(unittest.TestCase):
    def test_host_rules(self):
        p = Permissions(hosts=('example.com', '*.github.com', 'http://127.0.0.1:8000'))
        self.assertTrue(p.allows_url('https://example.com/a.csv'))
        self.assertFalse(p.allows_url('http://example.com/a.csv'))          # https only
        self.assertFalse(p.allows_url('https://evil.example.com/'))
        self.assertFalse(p.allows_url('https://example.com.evil.net/'))
        self.assertTrue(p.allows_url('https://api.github.com/x'))
        self.assertTrue(p.allows_url('http://127.0.0.1:8000/x'))
        self.assertFalse(p.allows_url('http://127.0.0.1:8001/x'))
        self.assertFalse(p.allows_url('https://user:pw@example.com/'))
        self.assertFalse(p.allows_url('file:///etc/passwd'))
        self.assertFalse(Permissions().allows_url('https://example.com/'))

    def test_validate(self):
        self.assertTrue(Permissions(read=('relative/path',)).validate())
        self.assertTrue(Permissions(read=('/',)).validate())
        self.assertTrue(Permissions(hosts=('*',)).validate())
        self.assertEqual(Permissions(read=(os.path.abspath(__file__),)).validate(), [])


class TempDirTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='robo-test-')
        self.root = os.path.join(self.tmp, 'tasks')
        os.makedirs(self.root)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def make(self, rel, text='hello'):
        path = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            f.write(text)
        return path


class WorkspaceTest(TempDirTest):
    def test_changes_are_reviewed_before_touching_originals(self):
        self.make('docs/a.txt', 'a')
        self.make('docs/b.txt', 'b')
        docs = os.path.join(self.tmp, 'docs')
        ws = Workspace.create(self.root, Permissions(write=(docs,)))
        copy = os.path.join(ws.work, ws.files['docs'])
        with open(os.path.join(copy, 'a.txt'), 'w') as f:
            f.write('A!')
        os.remove(os.path.join(copy, 'b.txt'))
        with open(os.path.join(copy, 'c.txt'), 'w') as f:
            f.write('new')
        changes = ws.changes()
        self.assertEqual(sorted((c.kind, c.rel) for c in changes.changes),
                         [('added', 'c.txt'), ('deleted', 'b.txt'), ('modified', 'a.txt')])
        self.assertEqual(open(os.path.join(docs, 'a.txt')).read(), 'a')   # untouched so far
        applied, skipped = changes.apply()
        self.assertEqual((len(applied), skipped), (3, []))
        self.assertEqual(sorted(os.listdir(docs)), ['a.txt', 'c.txt'])
        self.assertEqual(open(os.path.join(docs, 'a.txt')).read(), 'A!')

    def test_your_own_edits_win_and_symlinks_never_leave(self):
        a = self.make('docs/a.txt', 'a')
        secret = self.make('secret.txt', 'secret')
        docs = os.path.dirname(a)
        ws = Workspace.create(self.root, Permissions(write=(docs,)))
        copy = os.path.join(ws.work, ws.files['docs'])
        with open(os.path.join(copy, 'a.txt'), 'w') as f:
            f.write('task edit')
        os.symlink(secret, os.path.join(copy, 'link.txt'))
        with open(a, 'w') as f:
            f.write('my edit')                            # you edited it meanwhile
        applied, skipped = ws.changes().apply()
        self.assertEqual(applied, [])
        self.assertEqual([r for _, r in skipped], ['you changed it meanwhile'])
        self.assertEqual(open(a).read(), 'my edit')
        self.assertFalse(os.path.exists(os.path.join(docs, 'link.txt')))

    def test_symlinks_in_granted_folders_are_not_copied_in(self):
        secret = self.make('secret.txt', 'secret')
        self.make('docs/a.txt')
        docs = os.path.join(self.tmp, 'docs')
        os.symlink(secret, os.path.join(docs, 'sneaky'))
        ws = Workspace.create(self.root, Permissions(write=(docs,)))
        self.assertEqual(os.listdir(os.path.join(ws.work, ws.files['docs'])), ['a.txt'])

    def test_too_big_to_copy(self):
        self.make('big/x.bin', 'x' * 2048)
        with self.assertRaises(Exception):
            Workspace.create(self.root, Permissions(write=(os.path.join(self.tmp, 'big'),),
                                                    max_copy_mb=0))
        self.assertEqual(os.listdir(self.root), [])       # nothing left behind


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/redirect'):
            self.send_response(302)
            self.send_header('Location', 'http://localhost:%d/data.txt' % self.server.server_port)
            self.end_headers()
            return
        body = b'x' * (2 * 1024 * 1024) if self.path == '/big' else b'downloaded!'
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


class LocalServer:
    def __enter__(self):
        self.httpd = http.server.HTTPServer(('127.0.0.1', 0), _Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = 'http://127.0.0.1:%d' % self.httpd.server_port
        return self

    def __exit__(self, *a):
        self.httpd.shutdown()
        self.httpd.server_close()


class BrokerTest(TempDirTest):
    def fetch(self, perms, url):
        ws = Workspace.create(self.root, perms)
        b = Broker(perms, ws)
        b.handle({'type': 'request', 'id': 1, 'op': 'fetch', 'url': url})
        for _ in range(100):
            replies = b.take_replies()
            if replies:
                return ws, replies[0]
            time.sleep(0.05)
        self.fail('no reply')

    def test_allowed_denied_redirect_and_size(self):
        with LocalServer() as srv:
            ok = Permissions(hosts=(srv.base,), max_download_mb=1)
            ws, r = self.fetch(ok, srv.base + '/data.txt')
            self.assertTrue(r['ok'], r)
            self.assertEqual(open(os.path.join(ws.work, r['value'])).read(), 'downloaded!')
            _, r = self.fetch(Permissions(), srv.base + '/data.txt')
            self.assertFalse(r['ok'])
            _, r = self.fetch(ok, srv.base + '/redirect')                  # to "localhost"
            self.assertFalse(r['ok'])
            self.assertIn('redirect', r['error'])
            ws, r = self.fetch(ok, srv.base + '/big')
            self.assertFalse(r['ok'])
            self.assertEqual(os.listdir(os.path.join(ws.work, 'downloads')), [])

    def test_unknown_request(self):
        ws = Workspace.create(self.root, Permissions())
        b = Broker(Permissions(), ws)
        b.handle({'type': 'request', 'id': 3, 'op': 'run_shell', 'cmd': 'rm -rf ~'})
        self.assertFalse(b.take_replies()[0]['ok'])


# ---------------------------------------------------------------- real sandboxes
class SandboxConformance:
    """The rules every SandboxBackend must follow (see robo/sandbox/backend.py)."""

    def make_backend(self):
        raise NotImplementedError

    def setUp(self):
        super().setUp()
        self.backend = self.make_backend()
        problem = self.backend.check()
        if problem:
            self.skipTest(problem)
        self.env = TaskEnvironment(sandbox=self.backend, workspace_root=self.root)

    def run_task(self, task, timeout=20, during=None):
        now = time.monotonic
        task.start(now())
        end = now() + timeout
        while not task.finished and now() < end:
            if during:
                during(task)
            task.poll(now())
            time.sleep(0.05)
        if not task.finished:
            task.abort(now())
            self.fail('task did not finish')
        return task

    def selftest(self, permissions=None, **args):
        task = SandboxedTask('selftest', 'selftest', self.env, args=args,
                             permissions=permissions)
        return self.run_task(task)

    def test_isolated_from_home_network_and_root(self):
        secret = self.make('secret.txt', 'secret')
        home = os.path.expanduser('~')
        bashrc = os.path.join(home, '.bashrc')
        t = self.selftest(probe_paths=[secret, home, bashrc, '/etc/passwd'],
                          write_paths=[secret, os.path.join(home, 'robo-was-here'),
                                       '/usr/robo', '/robo', 'out.txt'])
        self.assertEqual(t.state, 'done', t.error)
        r = t.output
        self.assertFalse(any(r['readable'].values()), r['readable'])
        self.assertEqual(r['writable'], {secret: False,
                                         os.path.join(home, 'robo-was-here'): False,
                                         '/usr/robo': False, '/robo': False,
                                         'out.txt': True})
        self.assertFalse(os.path.exists(os.path.join(home, 'robo-was-here')))
        self.assertEqual(open(secret).read(), 'secret')
        self.assertFalse(r['network'])
        self.assertFalse(r['root'])
        self.assertNotEqual(r['uid'], 0)
        for leaky in ('DISPLAY', 'WAYLAND_DISPLAY', 'DBUS_SESSION_BUS_ADDRESS',
                      'XDG_RUNTIME_DIR', 'SSH_AUTH_SOCK', 'USER'):
            self.assertNotIn(leaky, r['env'])

    def test_granted_files_are_read_only(self):
        notes = self.make('notes.txt', 'my notes')
        t = self.selftest(Permissions(read=(notes,)),
                          probe_paths=['input/notes.txt'], write_paths=['input/notes.txt'])
        self.assertEqual(t.state, 'done', t.error)
        self.assertEqual(t.output['readable'], {'input/notes.txt': True})
        self.assertEqual(t.output['writable'], {'input/notes.txt': False})
        self.assertEqual(open(notes).read(), 'my notes')

    def test_changes_wait_for_review(self):
        doc = self.make('doc.txt', 'v1')
        t = self.selftest(Permissions(write=(doc,)), write_paths=['files/doc.txt'])
        self.assertEqual(t.state, 'done', t.error)
        self.assertEqual(open(doc).read(), 'v1')
        self.assertEqual([c.kind for c in t.changes.changes], ['modified'])
        t.changes.apply()
        self.assertEqual(open(doc).read(), 'v1robo was here\n')

    def test_downloads_only_through_the_broker(self):
        with LocalServer() as srv:
            url = srv.base + '/data.txt'
            t = self.selftest(Permissions(hosts=(srv.base,)), fetch=[url])
            self.assertEqual(t.output['fetched'][url], 'downloaded!')
            t = self.selftest(fetch=[url])
            self.assertTrue(t.output['fetched'][url].startswith('denied'))

    def test_memory_limit(self):
        t = self.selftest(Permissions(memory_mb=128), allocate_mb=400)
        self.assertEqual(t.state, 'failed')

    def test_pause_resume_and_abort(self):
        task = SandboxedTask('selftest', 'selftest', self.env, args={'sleep': 30})
        now = time.monotonic
        task.start(now())
        time.sleep(1.0)
        task.poll(now())
        before = task.progress(now())
        self.assertGreater(before, 0)
        task.pause(now())
        time.sleep(1.0)
        task.process.receive()                  # drop anything sent before the freeze
        time.sleep(0.5)
        self.assertEqual(task.process.receive(), [])   # frozen: says nothing
        task.resume(now())
        time.sleep(0.5)
        task.poll(now())
        self.assertGreater(task.progress(now()), before)
        workspace = task.workspace.path
        task.abort(now())
        self.assertIsNotNone(task.process.exit_code())
        self.assertFalse(os.path.exists(workspace))

    def test_placeholder_task_runs(self):
        t = self.run_task(make_task('placeholder', random.Random(1), self.env, {'seconds': 0.6}))
        self.assertEqual(t.state, 'done', t.error)
        self.assertTrue(os.path.exists(os.path.join(t.workspace.work, 'report.txt')))


@unittest.skipUnless(sys.platform.startswith('linux'), 'bubblewrap is Linux only')
class BubblewrapTest(SandboxConformance, TempDirTest):
    def make_backend(self):
        from robo.platform.linux.sandbox import BubblewrapBackend
        return BubblewrapBackend()


if __name__ == '__main__':
    unittest.main()
