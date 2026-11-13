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
        self.assertTrue({'read_file', 'write_file', 'run_command', 'list_files'} <= tools)


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


if __name__ == '__main__':
    unittest.main()
