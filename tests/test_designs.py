"""Robo designs his own outfits with his AI agent (robo/tasks/design_task.py).

The agent CLI is faked (tests/test_agent_tasks.py's fake `claude`, which speaks
MCP to the real tool server), so no login or network is needed.
"""
import json
import os
import random
import re
import shutil
import stat
import sys
import tempfile
import textwrap
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.dirname(__file__))

from robo.app import build_companion  # noqa: E402
from robo.config import Settings  # noqa: E402
from robo.conversation import Context, RuleBrain  # noqa: E402
from robo.conversation.agent import parse_reply  # noqa: E402
from robo.core import characters  # noqa: E402
from robo.design import REGISTRY  # noqa: E402
from robo.platform.headless import HeadlessPlatform  # noqa: E402
from robo.tasks import agent_task  # noqa: E402
from robo.tasks.design_task import BUILTIN_CHARACTERS, designs, install_design  # noqa: E402
from test_agent_tasks import FAKE_CLAUDE, Yes, call_server  # noqa: E402


def outfit(cid='disco', name='Disco Robo', broken=False):
    """A valid costume file (the pirate, renamed), or one with a typo in a colour."""
    with open(os.path.join(BUILTIN_CHARACTERS, 'pirate.yaml'), encoding='utf-8') as f:
        text = f.read()
    text = re.sub(r'^id: .*$', f'id: {cid}', text, count=1, flags=re.M)
    text = re.sub(r'^name: .*$', f'name: {name}', text, count=1, flags=re.M)
    text = re.sub(r'^words: .*$', f'words: [{cid}]', text, count=1, flags=re.M)
    if broken:
        text = text.replace('fill: gold', 'fill: not_a_colour', 1)
    return text


class _Dirs(unittest.TestCase):
    def setUp(self):
        self.designs = tempfile.mkdtemp()
        self.dirs = list(REGISTRY.directories)

    def tearDown(self):
        REGISTRY.directories[:] = self.dirs
        REGISTRY.reload()
        shutil.rmtree(self.designs, ignore_errors=True)


class InstallTest(_Dirs):
    def write(self, text, name='x.yaml'):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        path = os.path.join(d, name)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)
        return path

    def test_a_good_design_is_installed(self):
        problems = []
        cid = install_design(self.write(outfit()), self.designs, problems, idea='disco')
        self.assertEqual((cid, problems), ('disco', []))
        self.assertEqual(designs(self.designs), [('disco', os.path.join(self.designs,
                                                                         'disco.yaml'))])
        self.assertIn('disco', characters.costume_ids())
        with open(os.path.join(self.designs, 'disco.yaml'), encoding='utf-8') as f:
            self.assertTrue(f.readline().startswith('# Designed by Robo himself'))

    def test_a_taken_id_gets_a_new_one(self):
        cid = install_design(self.write(outfit('pirate', 'Space Pirate')), self.designs, [])
        self.assertEqual(cid, 'pirate_2')
        self.assertEqual(characters.get('pirate_2').title, 'Space Pirate')
        self.assertEqual(characters.get('pirate').title, 'Pirate')      # the original stays

    def test_broken_designs_are_turned_down(self):
        for text in (outfit(broken=True), 'id: [oops', outfit().replace('id: disco',
                                                                        'id: disco\nrole: base')):
            problems = []
            self.assertIsNone(install_design(self.write(text), self.designs, problems))
            self.assertTrue(problems)
        self.assertEqual(designs(self.designs), [])
        self.assertNotIn('disco', characters.costume_ids())


class ToolServerTest(unittest.TestCase):
    def test_look_at_image(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        os.makedirs(os.path.join(root, '.robo'))
        with open(os.path.join(root, 'a.png'), 'wb') as f:
            f.write(b'\x89PNG\r\n\x1a\n' + b'\0' * 20)
        with open(os.path.join(root, 'b.txt'), 'w') as f:
            f.write('hi')
        import subprocess
        from test_agent_tasks import SERVER
        msgs = [{'jsonrpc': '2.0', 'id': 0, 'method': 'initialize', 'params': {}},
                {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                 'params': {'name': 'look_at_image', 'arguments': {'path': 'a.png'}}}]
        out = subprocess.run([sys.executable, '-I', SERVER, '--root', root],
                             input='\n'.join(json.dumps(m) for m in msgs) + '\n',
                             capture_output=True, text=True, timeout=30).stdout.splitlines()
        content = json.loads(out[1])['result']['content'][0]
        self.assertEqual((content['type'], content['mimeType']), ('image', 'image/png'))
        (err, text), = call_server(root, ('look_at_image', {'path': 'b.txt'}))
        self.assertTrue(err)
        self.assertIn('not a PNG', text)


class DesignTaskTest(_Dirs):
    def setUp(self):
        super().setUp()
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
                                              chattiness='off'), self.p)
        self.approver = self.robot.task_env.approver = Yes()
        self.robot.task_env.designs_dir = self.designs
        self.said = []
        self.robot.conversation.announce = lambda text, mood='happy': self.said.append(text)

    def tearDown(self):
        os.environ['PATH'] = self.old_path
        for k in ('FAKE_PLAN', 'FAKE_SAY'):
            os.environ.pop(k, None)
        agent_task.RESULTS_ROOT = self.old_results
        shutil.rmtree(self.bin, ignore_errors=True)
        shutil.rmtree(self.results, ignore_errors=True)
        super().tearDown()

    def run_design(self, plan, idea='', say='I made a disco outfit! I call it Disco Robo!'):
        os.environ['FAKE_PLAN'] = json.dumps(plan)
        os.environ['FAKE_SAY'] = say
        result = self.robot.design_outfit(idea)
        t0 = time.time()
        while (self.robot.tasks.busy or self.robot.busy_working) and time.time() - t0 < 60:
            self.p.scheduler.advance(0.1)
            time.sleep(0.01)
        self.p.scheduler.advance(3)                     # out of the hacker clothes, into it
        return result

    def test_he_designs_checks_and_wears_a_new_outfit(self):
        result = self.run_design([
            ['read_file', {'path': 'input/outfit-kit/README.md', 'limit': 100}],
            ['read_file', {'path': 'input/outfit-kit/taken.txt'}],
            ['write_file', {'path': 'files/results/disco.yaml', 'content': outfit()}],
            ['run_command', {'command': 'python3 input/outfit-kit/check.py '
                                        'files/results/disco.yaml'}],
            ['look_at_image', {'path': 'files/results/disco.preview.png'}],
        ], idea='disco')
        self.assertEqual(result, 'started')
        self.assertEqual(self.approver.asked, [])       # nothing of yours: no need to ask
        self.assertEqual([c for c, _p in designs(self.designs)], ['disco'])
        self.assertIn('disco', self.robot.wardrobe.allowed)
        self.assertEqual(self.robot.wardrobe.current.id, 'disco')      # wearing it, proudly
        self.assertEqual(self.robot.wardrobe.choice.why, 'new')
        self.assertGreater(self.robot.taste.of('disco'), 0.4)
        self.assertIn('I call it Disco Robo', self.said[-1])
        self.assertEqual(os.listdir(self.results), [])                # no ~/Robo folder left
        self.assertFalse([n for n in os.listdir(self.p.task_dir()) if n.startswith('kit-')])

    def test_the_agent_saw_the_preview_and_a_clean_check(self):
        log = os.path.join(self.bin, 'events')
        self.run_design([
            ['write_file', {'path': 'files/results/disco.yaml', 'content': outfit()}],
            ['run_command', {'command': 'python3 input/outfit-kit/check.py files/results/'
                                        f'disco.yaml > {log} 2>&1; ls files/results >> {log}'}],
        ])
        with open(log) as f:
            out = f.read()
        self.assertIn('✓ disco', out)
        self.assertIn('disco.preview.png', out)

    def test_a_broken_design_is_not_installed(self):
        self.run_design([['write_file', {'path': 'files/results/disco.yaml',
                                         'content': outfit(broken=True)}]])
        self.assertEqual(designs(self.designs), [])
        self.assertIsNone(self.robot.wardrobe.current)
        self.assertIn("didn't come out right", self.said[-1])

    def test_no_design_without_a_capable_brain(self):
        robot = build_companion(Settings(agent='off', dress_up_every=0, evil_after=0), self.p)
        robot.task_env.designs_dir = self.designs
        self.assertFalse(robot.can_design())

    def test_on_his_own_only_when_switched_on_and_not_too_often(self):
        r = self.robot
        self.assertFalse(r.design_due())                      # off by default
        r.apply_settings(r.settings.with_changes(design_outfits=True, design_every=86400))
        self.assertTrue(r.design_due())
        r.taste.last_design = r.wall_clock() - 3600           # designed one an hour ago
        self.assertFalse(r.design_due())


@unittest.skipUnless(shutil.which('bwrap'), 'bubblewrap is not installed')
class SandboxedCheckTest(unittest.TestCase):
    def test_the_checker_runs_locked_in(self):
        """The design kit works in the real sandbox: Python, cairo, a preview picture."""
        import subprocess
        from robo.platform.linux.sandbox import BubblewrapBackend
        from robo.sandbox import LaunchSpec, Mount
        from robo.tasks import TaskEnvironment
        from robo.tasks.design_task import DesignTask
        backend = BubblewrapBackend()
        if backend.check():
            self.skipTest(backend.check())
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        task = DesignTask(TaskEnvironment(workspace_root=root), None, root)
        kit = task._make_kit()
        work = os.path.join(root, 'work')
        os.makedirs(os.path.join(work, '.robo'))
        os.makedirs(os.path.join(work, 'input', 'outfit-kit'))
        os.makedirs(os.path.join(work, 'files', 'results'))
        with open(os.path.join(work, 'files', 'results', 'disco.yaml'), 'w') as f:
            f.write(outfit())
        argv, env = backend.stdio_command(LaunchSpec(
            work_dir=work, read_only=(Mount(kit, 'input/outfit-kit'),), entry='mcp_server.py'))
        msgs = [{'jsonrpc': '2.0', 'id': 0, 'method': 'initialize', 'params': {}},
                {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {
                    'name': 'run_command', 'arguments': {
                        'command': 'python3 input/outfit-kit/check.py files/results/disco.yaml',
                        'timeout': 100}}},
                {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {
                    'name': 'look_at_image',
                    'arguments': {'path': 'files/results/disco.preview.png'}}}]
        out = subprocess.run(argv, env=env, input='\n'.join(json.dumps(m) for m in msgs) + '\n',
                             capture_output=True, text=True, timeout=150).stdout.splitlines()
        checked = json.loads(out[1])['result']['content'][0]['text']
        self.assertTrue(checked.startswith('exit code 0'), checked)
        self.assertIn('✓ disco', checked)
        self.assertEqual(json.loads(out[2])['result']['content'][0]['type'], 'image')


class ConversationTest(unittest.TestCase):
    def test_asking_him_to_design(self):
        brain = RuleBrain(random.Random(1))
        r = brain.respond('design yourself a disco knight outfit', Context(agent_tasks=True))
        self.assertEqual((r.action, r.action_arg), ('design_outfit', 'disco knight'))
        r = brain.respond('can you make a new costume', Context(agent_tasks=True))
        self.assertEqual((r.action, r.action_arg), ('design_outfit', ''))
        r = brain.respond('design yourself a new outfit', Context(agent_tasks=False))
        self.assertIsNone(r.action)
        self.assertIn('Claude', r.text)
        r = brain.respond('dress up as a pirate', Context(agent_tasks=True))
        self.assertEqual(r.action, 'dress_up')

    def test_the_ai_brain_can_start_a_design(self):
        reply = json.dumps({'say': 'Ooh!', 'action': 'design_outfit', 'arg': 'a deep sea diver'})
        r = parse_reply(reply, Context(agent_tasks=True))
        self.assertEqual((r.action, r.action_arg), ('design_outfit', 'a deep sea diver'))
        self.assertIsNone(parse_reply(reply, Context(agent_tasks=False)).action)


if __name__ == '__main__':
    unittest.main()
