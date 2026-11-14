"""Agent tasks: an AI agent works through Robo's sandboxed MCP tools.

The agent CLI is faked (a script that speaks MCP to the real tool server), so
no login or network is needed. The last test runs the tool server in the real
bubblewrap sandbox when it's available.

Run with:  python3 -m unittest discover -s tests
"""
import json
import os
import random
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from robo.agents import make_backend  # noqa: E402
from robo.app import build_companion  # noqa: E402
from robo.config import Settings  # noqa: E402
from robo.conversation import AgentBrain, RuleBrain  # noqa: E402
from robo.conversation.agent import parse_reply  # noqa: E402
from robo.conversation.brain import Context  # noqa: E402
from robo.platform.headless import HeadlessPlatform  # noqa: E402
from robo.sandbox import Approver, LaunchSpec  # noqa: E402
from robo.sandbox.backend import WORKER_DIR  # noqa: E402
from robo.tasks import agent_task  # noqa: E402
from robo.tasks.agent_task import TaskRefused, resolve_paths  # noqa: E402

SERVER = os.path.join(WORKER_DIR, 'mcp_server.py')

# A fake `claude`: reads the MCP config it was given, starts that server, calls
# the tools listed in $FAKE_PLAN (JSON), then prints a stream-json result.
FAKE_CLAUDE = r'''
args = sys.argv[1:]
if args[:2] == ['auth', 'status']:
    print(json.dumps({"loggedIn": True})); sys.exit()
assert args[args.index('--tools') + 1] == '', 'its own tools must be off'
assert '--strict-mcp-config' in args
cfg = json.load(open(args[args.index('--mcp-config') + 1]))['mcpServers']['robo']
import subprocess
srv = subprocess.Popen([cfg['command']] + cfg['args'], stdin=subprocess.PIPE,
                       stdout=subprocess.PIPE, text=True, env={**os.environ, **cfg['env']})
def rpc(i, method, params):
    srv.stdin.write(json.dumps({"jsonrpc": "2.0", "id": i, "method": method, "params": params}) + "\n")
    srv.stdin.flush()
    return json.loads(srv.stdout.readline())
rpc(0, "initialize", {"protocolVersion": "2025-06-18"})
print(json.dumps({"type": "system", "subtype": "init",
                  "mcp_servers": [{"name": "robo", "status": "connected"}]}), flush=True)
import time
for i, (name, a) in enumerate(json.loads(os.environ.get("FAKE_PLAN", "[]")), 1):
    print(json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "mcp__robo__" + name, "input": a}]}}), flush=True)
    r = rpc(i, "tools/call", {"name": name, "arguments": a})
    if name == "sleep":
        time.sleep(30)
srv.stdin.close()
print(json.dumps({"type": "result", "subtype": "success", "is_error": False,
                  "result": os.environ.get("FAKE_SAY", "All done, boop!")}), flush=True)
'''


class Yes(Approver):
    def __init__(self):
        self.asked = []

    def ask_permissions(self, title, lines, on_answer):
        self.asked.append(('permissions', lines))
        on_answer(True)

    def review_changes(self, title, lines, on_answer):
        self.asked.append(('review', lines))
        on_answer(True)

    def show_results(self, title, summary, files, folder):
        self.asked.append(('results', (summary, files, folder)))

    def open_path(self, path):
        self.asked.append(('open', path))
        return True


class Tmp:
    """A temporary folder inside the home folder (so it may be granted)."""

    def __enter__(self):
        self.path = tempfile.mkdtemp(prefix='robo-test-', dir=os.path.expanduser('~'))
        return self.path

    def __exit__(self, *exc):
        shutil.rmtree(self.path, ignore_errors=True)


def call_server(root, *calls):
    """Talk MCP to the tool server (no sandbox) in `root`; returns the results."""
    p = subprocess.Popen([sys.executable, '-I', SERVER, '--root', root], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, text=True)
    out = []
    msgs = [{'jsonrpc': '2.0', 'id': 0, 'method': 'initialize', 'params': {}},
            {'jsonrpc': '2.0', 'method': 'notifications/initialized'}]
    msgs += [{'jsonrpc': '2.0', 'id': i, 'method': 'tools/call',
              'params': {'name': n, 'arguments': a}} for i, (n, a) in enumerate(calls, 1)]
    stdout, _ = p.communicate('\n'.join(json.dumps(m) for m in msgs) + '\n', timeout=30)
    for line in stdout.splitlines()[1:]:
        msg = json.loads(line)
        if 'error' in msg:                        # e.g. an unknown tool
            out.append((True, msg['error']['message']))
            continue
        r = msg['result']
        out.append((r['isError'], r['content'][0]['text']))
    return out


def make_pdf(path, pages, compress=False):
    """A small but real PDF (Helvetica text, one line per item), standard library only."""
    import zlib
    objs = ['<< /Type /Catalog /Pages 2 0 R >>', None,
            '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    kids = []
    for lines in pages:
        ops = 'BT /F1 14 Tf 72 720 Td ' + ' '.join(
            '(%s) Tj 0 -20 Td' % l.replace('(', '\\(').replace(')', '\\)') for l in lines) + ' ET'
        data = ops.encode('latin-1')
        if compress:
            data = zlib.compress(data)
        objs.append((('<< /Length %d /Filter /FlateDecode >>' if compress else
                      '<< /Length %d >>') % len(data), data))
        objs.append('<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] '
                    '/Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>' % len(objs))
        kids.append(len(objs))
    objs[1] = '<< /Type /Pages /Kids [%s] /Count %d >>' % (
        ' '.join('%d 0 R' % k for k in kids), len(kids))
    out, offsets = bytearray(b'%PDF-1.4\n'), []
    for n, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += b'%d 0 obj\n' % n
        if isinstance(o, tuple):
            out += o[0].encode() + b'\nstream\n' + o[1] + b'\nendstream'
        else:
            out += o.encode()
        out += b'\nendobj\n'
    xref = len(out)
    out += b'xref\n0 %d\n0000000000 65535 f \n' % (len(objs) + 1)
    out += b''.join(b'%010d 00000 n \n' % o for o in offsets)
    out += b'trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n' % (len(objs) + 1, xref)
    with open(path, 'wb') as f:
        f.write(bytes(out))


def load_server():
    import importlib.util
    spec = importlib.util.spec_from_file_location('robo_mcp_server_test', SERVER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ToolServerTest(unittest.TestCase):
    def test_tools_work_inside_their_folder(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, 'files', 'results'))
            res = call_server(root,
                              ('write_file', {'path': 'files/results/a.txt', 'content': 'hello'}),
                              ('edit_file', {'path': 'files/results/a.txt', 'old': 'hello',
                                             'new': 'hi there'}),
                              ('read_file', {'path': 'files/results/a.txt'}),
                              ('run_command', {'command': 'ls files/results'}),
                              ('list_files', {}),
                              ('report_progress', {'note': 'halfway', 'fraction': 0.5}))
            self.assertEqual([e for e, _ in res], [False] * 6)
            self.assertEqual(res[2][1], 'hi there')
            self.assertIn('a.txt', res[3][1])
            with open(os.path.join(root, '.robo', 'events.jsonl')) as f:
                events = f.read()
            self.assertIn('halfway', events)

    def test_reads_pdfs(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, 'input'))
            pdf = os.path.join(root, 'input', 'report.pdf')
            make_pdf(pdf, [['Quarterly report', 'Sales went up (a lot)'], ['Page two here']],
                     compress=True)
            res = call_server(root, ('read_pdf', {'path': 'input/report.pdf'}),
                              ('read_pdf', {'path': 'input/report.pdf', 'first_page': 2}),
                              ('read_file', {'path': 'input/report.pdf'}),
                              ('read_pdf', {'path': 'input/report.pdf', 'first_page': 9}))
            self.assertEqual([e for e, _ in res], [False, False, False, True])
            self.assertIn('Sales went up (a lot)', res[0][1])
            self.assertIn('Page two here', res[0][1])
            self.assertIn('2 pages', res[0][1])
            self.assertNotIn('Quarterly', res[1][1])
            self.assertIn('Page two here', res[1][1])
            self.assertIn('Quarterly report', res[2][1])          # read_file reads PDFs too
            self.assertIn('only 2 pages', res[3][1])

    def test_reads_pdfs_without_any_pdf_programs(self):
        server = load_server()
        with tempfile.TemporaryDirectory() as root:
            for compress in (False, True):
                pdf = os.path.join(root, f'doc{compress}.pdf')
                make_pdf(pdf, [['Hello (world)', 'second line'], ['Next page']], compress)
                pages = server._pdf_text_builtin(pdf, 1, None)
                self.assertEqual(len(pages), 2)
                self.assertEqual(pages[0].split('\n')[:2], ['Hello (world)', 'second line'])
                self.assertEqual(server._pdf_text_builtin(pdf, 2, 2), ['Next page'])

    @unittest.skipUnless(shutil.which('pdftoppm'), 'poppler-utils is not installed')
    def test_looks_at_pdf_pages(self):
        with tempfile.TemporaryDirectory() as root:
            make_pdf(os.path.join(root, 'a.pdf'), [['Look at me']])
            p = subprocess.Popen([sys.executable, '-I', SERVER, '--root', root],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
            msg = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                   'params': {'name': 'look_at_pdf_page', 'arguments': {'path': 'a.pdf'}}}
            out, _ = p.communicate(json.dumps(msg) + '\n', timeout=60)
            content = json.loads(out)['result']['content'][0]
            self.assertEqual((content['type'], content['mimeType']), ('image', 'image/png'))

    def test_no_escaping_the_folder(self):
        with tempfile.TemporaryDirectory() as root:
            res = call_server(root, ('read_file', {'path': '../../etc/passwd'}),
                              ('write_file', {'path': '/tmp/robo-evil.txt', 'content': 'x'}),
                              ('move', {'source': '.', 'target': '../x'}),
                              ('write_file', {'path': '.robo/events.jsonl', 'content': 'fake'}),
                              ('nope', {}))
            self.assertTrue(all(err for err, _ in res))
            self.assertFalse(os.path.exists('/tmp/robo-evil.txt'))

    def test_speaks_mcp(self):
        p = subprocess.run([sys.executable, '-I', SERVER, '--root', tempfile.gettempdir()],
                           input=json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})
                           + '\n', capture_output=True, text=True, timeout=10)
        tools = {t['name'] for t in json.loads(p.stdout)['result']['tools']}
        self.assertTrue({'read_file', 'write_file', 'run_command', 'list_files',
                         'read_pdf', 'look_at_pdf_page'} <= tools)


class AgentTaskTest(unittest.TestCase):
    def setUp(self):
        self.bin = tempfile.mkdtemp()
        path = os.path.join(self.bin, 'claude')
        with open(path, 'w') as f:
            f.write(f'#!{sys.executable}\nimport json, os, sys\n' + textwrap.dedent(FAKE_CLAUDE))
        os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
        self.old_path = os.environ['PATH']
        os.environ['PATH'] = self.bin + os.pathsep + self.old_path
        self.results = tempfile.mkdtemp()
        self.old_results = agent_task.RESULTS_ROOT
        agent_task.RESULTS_ROOT = self.results
        self.p = HeadlessPlatform()
        self.robot = build_companion(Settings(agent='claude', dress_up_every=0, evil_after=0,
                                              chattiness='off'),
                                     self.p)
        self.approver = self.robot.task_env.approver = Yes()

    def tearDown(self):
        os.environ['PATH'] = self.old_path
        for k in ('FAKE_PLAN', 'FAKE_SAY'):
            os.environ.pop(k, None)
        agent_task.RESULTS_ROOT = self.old_results
        shutil.rmtree(self.bin, ignore_errors=True)
        shutil.rmtree(self.results, ignore_errors=True)

    def run_task(self, args, plan, limit=20):
        os.environ['FAKE_PLAN'] = json.dumps(plan)
        said = []
        self.robot.conversation.announce = lambda text, mood='happy': said.append(text)
        result = self.robot.start_task('agent', args)
        t0 = time.time()
        while self.robot.tasks.busy and time.time() - t0 < limit:
            self.p.scheduler.advance(0.1)
            time.sleep(0.01)
        return result, said

    def test_a_task_from_start_to_review(self):
        with Tmp() as home_dir:
            notes = os.path.join(home_dir, 'notes.txt')
            open(notes, 'w').write('b\na\n')
            result, said = self.run_task(
                {'goal': 'sort my notes and write a summary', 'write': [notes]},
                [['read_file', {'path': 'files/notes.txt'}],
                 ['write_file', {'path': 'files/notes.txt', 'content': 'a\nb\n'}],
                 ['report_progress', {'note': 'sorting'}],
                 ['write_file', {'path': 'files/results/summary.txt', 'content': 'sorted 2'}]])
            self.assertEqual(result, 'asking')
            kind, lines = self.approver.asked[0]
            self.assertEqual(kind, 'permissions')
            self.assertTrue(any('sort my notes' in l for l in lines))
            self.assertTrue(any('sent to Claude' in l for l in lines))
            kind, lines = self.approver.asked[1]
            self.assertEqual(kind, 'review')
            self.assertEqual(open(notes).read(), 'a\nb\n')            # applied after review
            made = [os.path.join(d, f) for d, _, fs in os.walk(self.results) for f in fs]
            self.assertEqual([open(m).read() for m in made], ['sorted 2'])
            self.assertEqual(said, ['All done, boop!'])               # he tells you
            self.assertTrue(any(l.startswith('Summary: All done') for l in lines))
            kind, (summary, files, folder) = self.approver.asked[2]  # then shows what he made
            self.assertEqual(kind, 'results')
            self.assertEqual(summary, 'All done, boop!')
            self.assertEqual(sorted(files), sorted(made + [notes]))
            self.assertEqual(os.path.dirname(made[0]), folder)        # his results folder

    def test_reading_only_changes_nothing_of_yours(self):
        with Tmp() as home_dir:
            notes = os.path.join(home_dir, 'notes.txt')
            open(notes, 'w').write('keep me')
            self.run_task({'goal': 'look at my notes', 'read': [notes]},
                          [['write_file', {'path': 'input/notes.txt/x', 'content': 'nope'}],
                           ['run_command', {'command': 'echo hacked > input/notes.txt'}]])
            self.assertEqual(open(notes).read(), 'keep me')
            self.assertEqual(os.listdir(self.results), [])            # nothing made: no folder

    def test_rejected_changes_are_thrown_away(self):
        class No(Yes):
            def review_changes(self, title, lines, on_answer):
                on_answer(False)
        self.robot.task_env.approver = No()
        self.run_task({'goal': 'make a file'},
                      [['write_file', {'path': 'files/results/x.txt', 'content': 'x'}]])
        self.assertEqual(os.listdir(self.results), [])

    def test_aborting_stops_the_agent(self):
        os.environ['FAKE_PLAN'] = json.dumps([['sleep', {}]])
        self.robot.start_task('agent', {'goal': 'take forever'})
        for _ in range(20):
            self.p.scheduler.advance(0.1)
            time.sleep(0.02)
        task = self.robot.tasks.current
        self.robot.abort_task()
        self.assertEqual(task.state, 'aborted')
        self.assertTrue(task._proc.poll() is not None)

    def test_secrets_and_missing_paths_are_refused(self):
        for bad in ('~', '~/.ssh', '~/.claude', '~/no-such-folder-robo'):
            with self.assertRaises(TaskRefused, msg=bad):
                resolve_paths([bad])
        self.assertEqual(self.robot.start_task('agent', {'goal': 'x', 'read': ['~/.ssh']}),
                         'refused')

    def test_only_agents_that_can_switch_their_tools_off(self):
        self.assertTrue(make_backend('claude', '/tmp').supports_tasks)
        for chat_only in ('codex', 'gemini'):
            self.assertFalse(make_backend(chat_only, '/tmp').supports_tasks)
        r = build_companion(Settings(agent='codex', dress_up_every=0), HeadlessPlatform())
        self.assertEqual(r.start_task('agent', {'goal': 'x'}), 'refused')
        self.assertIn('chat', r.last_task_problem)

    def test_the_task_form_counts_as_approval(self):
        class Form(Yes):
            def ask_task(self, agent_name, on_answer):
                on_answer({'goal': 'write a poem', 'read': [], 'write': [], 'approved': True})
                return True
        self.robot.task_env.approver = form = Form()
        os.environ['FAKE_PLAN'] = '[]'
        self.robot.ask_for_task()
        self.assertTrue(self.robot.tasks.busy)
        self.assertEqual(form.asked, [])                              # no second question

    def test_menu_offers_the_task_form(self):
        from robo.platform.base import PointerEvent
        self.robot.pointer_press(PointerEvent(3, 85, 200, 0, 0))
        labels = [i.label or '' for i in self.p.window.menus[-1]]
        self.assertTrue(any('Give me a task' in l for l in labels))

    def test_menu_opens_the_results_folder(self):
        from robo.platform.base import PointerEvent
        os.rmdir(self.results)                                  # nothing made yet: no entry
        self.robot.pointer_press(PointerEvent(3, 85, 200, 0, 0))
        labels = [i.label or '' for i in self.p.window.menus[-1]]
        self.assertFalse(any('task results' in l for l in labels))
        os.makedirs(self.results)
        self.robot.pointer_press(PointerEvent(3, 85, 200, 0, 0))
        item = next(i for i in self.p.window.menus[-1] if 'task results' in (i.label or ''))
        item.action()
        self.assertEqual(self.approver.asked[-1], ('open', self.results))

    def test_review_lines_are_grouped_for_the_popup(self):
        from robo.sandbox.approval import group_lines
        sections, notes = group_lines(['Do: sort: my notes', 'Read: /a/b.pdf', 'Read: /c',
                                       'added: /r/x.md', '... and 3 more', '',
                                       'Nothing has been changed yet.'])
        self.assertEqual([(s.heading, s.items) for s in sections],
                         [("What I'll do", ['sort: my notes']),
                          ("I'd like to look at", ['/a/b.pdf', '/c']),
                          ('New files', ['/r/x.md', '... and 3 more'])])
        self.assertTrue(sections[1].paths)
        self.assertEqual(notes, ['Nothing has been changed yet.'])


class VoiceTaskTest(unittest.TestCase):
    CTX = Context(agent_tasks=True)

    def test_agent_can_start_a_task(self):
        with Tmp() as d:
            raw = json.dumps({'say': 'On it!', 'action': 'agent_task',
                              'arg': {'goal': 'tidy', 'read': [d], 'approved': True}})
            r = parse_reply(raw, self.CTX)
            self.assertEqual(r.action, 'agent_task')
            self.assertTrue(r.end)                                    # off to work
            arg = json.loads(r.action_arg)
            self.assertNotIn('approved', arg)                         # can't skip asking you
            self.assertEqual(arg['read'], [d])

    def test_bad_paths_get_a_question_back(self):
        r = parse_reply(json.dumps({'say': 'ok', 'action': 'agent_task',
                                    'arg': {'goal': 'x', 'read': ['~/.ssh']}}), self.CTX)
        self.assertIsNone(r.action)
        self.assertIn('Which folder', r.text)

    def test_no_tasks_without_a_capable_agent(self):
        r = parse_reply(json.dumps({'say': 'ok', 'action': 'agent_task', 'arg': {'goal': 'x'}}),
                        Context(agent_tasks=False))
        self.assertIsNone(r.action)

    def test_do_a_task_goes_to_the_agent_when_it_can(self):
        b = AgentBrain(RuleBrain(random.Random(1)), tempfile.gettempdir())
        self.assertFalse(b._local('do a task for me', Context(agent_tasks=True)))
        self.assertTrue(b._local('do a task for me', Context(agent_tasks=False)))


@unittest.skipUnless(shutil.which('bwrap'), 'bubblewrap is not installed')
class SandboxedToolsTest(unittest.TestCase):
    def test_tool_server_runs_locked_in(self):
        from robo.platform.linux.sandbox import BubblewrapBackend
        backend = BubblewrapBackend()
        if backend.check():
            self.skipTest(backend.check())
        work = tempfile.mkdtemp()
        os.makedirs(os.path.join(work, '.robo'))
        argv, env = backend.stdio_command(LaunchSpec(work_dir=work, entry='mcp_server.py'))
        home = os.path.expanduser('~')
        cmds = [f'ls {home}', 'python3 -c "import socket; socket.create_connection((\'1.1.1.1\', 443), 3)"',
                'touch /usr/robo-evil', 'echo ok > mine.txt']
        msgs = [{'jsonrpc': '2.0', 'id': 0, 'method': 'initialize', 'params': {}}] + [
            {'jsonrpc': '2.0', 'id': i, 'method': 'tools/call',
             'params': {'name': 'run_command', 'arguments': {'command': c}}}
            for i, c in enumerate(cmds, 1)]
        out = subprocess.run(argv, env=env, input='\n'.join(json.dumps(m) for m in msgs) + '\n',
                             capture_output=True, text=True, timeout=60).stdout.splitlines()
        codes = [json.loads(l)['result']['content'][0]['text'].split('\n')[0] for l in out[1:]]
        self.assertEqual(codes[:3], ['exit code 2', 'exit code 1', 'exit code 1'])   # all refused
        self.assertEqual(codes[3], 'exit code 0')
        self.assertTrue(os.path.exists(os.path.join(work, 'mine.txt')))
        shutil.rmtree(work, ignore_errors=True)

    @unittest.skipUnless(shutil.which('pdftotext'), 'poppler-utils is not installed')
    def test_pdfs_can_be_read_in_the_sandbox(self):
        from robo.platform.linux.sandbox import BubblewrapBackend
        backend = BubblewrapBackend()
        if backend.check():
            self.skipTest(backend.check())
        work = tempfile.mkdtemp()
        os.makedirs(os.path.join(work, '.robo'))
        make_pdf(os.path.join(work, 'doc.pdf'), [['Inside the box']], compress=True)
        argv, env = backend.stdio_command(LaunchSpec(work_dir=work, entry='mcp_server.py'))
        msgs = [{'jsonrpc': '2.0', 'id': 0, 'method': 'initialize', 'params': {}},
                {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                 'params': {'name': 'read_pdf', 'arguments': {'path': 'doc.pdf'}}},
                {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call',
                 'params': {'name': 'look_at_pdf_page', 'arguments': {'path': 'doc.pdf'}}}]
        out = subprocess.run(argv, env=env, input='\n'.join(json.dumps(m) for m in msgs) + '\n',
                             capture_output=True, text=True, timeout=60).stdout.splitlines()
        text = json.loads(out[1])['result']['content'][0]['text']
        self.assertIn('Inside the box', text)
        self.assertNotIn('rough extraction', text)              # pdftotext did it
        if shutil.which('pdftoppm'):
            self.assertEqual(json.loads(out[2])['result']['content'][0]['type'], 'image')
        shutil.rmtree(work, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
