"""Plugins (robo/plugins): found, switched on, hot reloaded, kept in their place.

The plugins run as real processes (robo/sandbox/worker/plugin_host.py) through
the headless platform's FakeSandbox, which starts them WITHOUT isolation; the
real sandbox is checked at the end (skipped where bubblewrap can't run).
"""
import json
import os
import shutil
import sys
import tempfile
import textwrap
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from robo.agents.base import AgentAnswer  # noqa: E402
from robo.app import build_companion  # noqa: E402
from robo.config import Settings  # noqa: E402
from robo.plugins import BUILTIN_DIR, ManifestError, load_manifest  # noqa: E402
from robo.platform.headless import HeadlessPlatform  # noqa: E402

PLUGIN = '''
from robo_plugin import plugin, RoboError

@plugin.command('say hello')
def hello(text):
    return 'Hello number one'
'''


class FakeAI:
    """Robo's AI brain for plugins: answers with what the test queued up."""
    supports_images = True

    def __init__(self, answers):
        self.answers = list(answers)
        self.asked = []

    def ask(self, prompt, system, kind='chat', image=None):
        self.asked.append((prompt, image, kind))
        return AgentAnswer(self.answers.pop(0) if self.answers else '{}')


class PluginTestCase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='robo-plugins-')
        self.addCleanup(shutil.rmtree, self.root, True)
        self.p = HeadlessPlatform()
        self.robot = build_companion(Settings(agent='claude', dress_up_every=0, evil_after=0,
                                              chattiness='off'), self.p)
        self.said = []
        self.robot.conversation.announce = lambda text, mood='happy': self.said.append(text)
        self.m = self.robot.plugins
        self.m.directories[:] = [self.root]
        self.addCleanup(self.m.shutdown)

    def write(self, pid, code=PLUGIN, permissions=(), extra=None):
        folder = os.path.join(self.root, pid)
        os.makedirs(folder, exist_ok=True)
        manifest = {'id': pid, 'name': pid.capitalize(), 'permissions': list(permissions)}
        manifest.update(extra or {})
        with open(os.path.join(folder, 'plugin.json'), 'w') as f:
            json.dump(manifest, f)
        path = os.path.join(folder, 'plugin.py')
        with open(path, 'w') as f:
            f.write(textwrap.dedent(code))
        st = os.stat(path)                  # make sure the change is seen as one
        os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
        return folder

    def run_until(self, check, seconds=10.0):
        end = time.time() + seconds
        while time.time() < end:
            self.p.scheduler.advance(0.05)
            if check():
                return True
            time.sleep(0.01)
        self.fail('timed out waiting')

    def turn_on(self, pid):
        self.run_until(lambda: pid in self.m.runners)
        self.m.set_enabled(pid, True)
        self.run_until(lambda: self.m.runners[pid].running)
        return self.m.runners[pid]

    def invoke(self, runner, kind, name, **kw):
        out = []
        runner.invoke(kind, name, lambda v, e: out.append((v, e)), **kw)
        self.run_until(lambda: out)
        return out[0]


class ManifestTest(unittest.TestCase):
    def test_bad_plugin_files_are_explained(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)

        def make(data, code=True):
            folder = tempfile.mkdtemp(dir=root)
            with open(os.path.join(folder, 'plugin.json'), 'w') as f:
                f.write(data if isinstance(data, str) else json.dumps(data))
            if code:
                open(os.path.join(folder, 'plugin.py'), 'w').close()
            return folder
        for data, code, words in ((dict(id='a b'), True, 'bad id'),
                                  (dict(id='x', permissions=['root']), True, 'permissions'),
                                  (dict(id='x'), False, 'missing'),
                                  (dict(id='x', entry='../evil.py'), True, 'entry'),
                                  ('{oops', True, 'plugin.json'),
                                  (dict(id='x', api=99), True, 'API')):
            with self.assertRaises(ManifestError) as e:
                load_manifest(make(data, code))
            self.assertIn(words, str(e.exception))

    def test_the_example_plugins_are_valid(self):
        ids = {load_manifest(os.path.join(BUILTIN_DIR, n)).id for n in os.listdir(BUILTIN_DIR)
               if not n.startswith(('.', '_'))}
        self.assertEqual(ids, {'dice', 'camera_peek', 'game_buddy'})


class LifeTest(PluginTestCase):
    def test_a_new_plugin_stays_off_until_you_switch_it_on(self):
        found = []
        self.m.on_new_plugin = found.append
        self.write('hello')
        self.run_until(lambda: 'hello' in self.m.runners)
        self.assertEqual([f.id for f in found], ['hello'])
        self.assertEqual(self.m.runners['hello'].state, 'off')
        self.assertIsNone(self.m.command_for('say hello'))
        self.turn_on('hello')
        runner, cid = self.m.command_for('could you say hello please')
        self.assertEqual(self.invoke(runner, 'command', cid, text='say hello'),
                         ('Hello number one', None))
        self.m.set_enabled('hello', False)
        self.run_until(lambda: self.m.runners['hello'].state == 'off')

    def test_you_ask_robo_and_the_plugin_answers(self):
        self.write('hello')
        self.turn_on('hello')
        conv = self.robot.conversation
        conv.start()
        self.run_until(lambda: self.p.ears.listening is not None)
        self.p.ears.hear('say hello')
        self.run_until(lambda: self.p.voice.said[-1] == 'Hello number one')

    def test_saving_the_file_reloads_it_while_robo_runs(self):
        self.write('hello')
        runner = self.turn_on('hello')
        first = runner.proc
        self.write('hello', PLUGIN.replace('Hello number one', 'Hello number two') + '''
@plugin.command('count')
def count(text):
    return 'three'
''')
        self.run_until(lambda: runner.running and runner.proc is not first)
        self.assertEqual(self.invoke(runner, 'command', 'c0', text='say hello')[0],
                         'Hello number two')
        self.assertEqual(self.invoke(runner, 'command', 'c1', text='count')[0], 'three')

    def test_a_broken_plugin_doesnt_hurt_robo(self):
        self.write('oops', 'from robo_plugin import plugin\ndef oops(:\n')
        self.run_until(lambda: 'oops' in self.m.runners)
        self.m.set_enabled('oops', True)
        runner = self.m.runners['oops']
        self.run_until(lambda: runner.state in ('crashed', 'broken') and runner.problem)
        self.assertIn('SyntaxError', runner.problem)
        self.write('oops')                                   # fixed: it starts again
        self.run_until(lambda: runner.running)

    def test_a_crash_is_restarted(self):
        self.write('crashy', PLUGIN + '''
import os
@plugin.command('crash')
def crash(text):
    os._exit(3)
''')
        runner = self.turn_on('crashy')
        _value, error = self.invoke(runner, 'command', 'c1', text='crash')
        self.assertTrue(error)
        self.run_until(lambda: runner.running, seconds=8)
        self.assertEqual(runner.crashes, 1)

    def test_errors_in_a_handler_are_reported_not_fatal(self):
        self.write('bad', PLUGIN + '''
@plugin.command('divide')
def divide(text):
    return 1 / 0
''')
        runner = self.turn_on('bad')
        value, error = self.invoke(runner, 'command', 'c1', text='divide')
        self.assertIn('ZeroDivisionError', error)
        self.assertTrue(runner.running)

    def test_tools_and_menu_items(self):
        shutil.copytree(os.path.join(BUILTIN_DIR, 'dice'), os.path.join(self.root, 'dice'))
        self.turn_on('dice')
        self.assertTrue(any(line.startswith('roll_dice (Dice)')
                            for line in self.m.describe_tools()))
        from robo.conversation.agent import parse_reply
        ctx = self.robot.conversation.context()
        reply = parse_reply(json.dumps({'say': 'Rolling!', 'action': 'plugin',
                                        'arg': {'tool': 'roll_dice', 'args': {'sides': 20}}}),
                            ctx)
        self.assertEqual(reply.action, 'plugin')
        self.robot.use_plugin_tool(reply.action_arg)
        self.run_until(lambda: self.said and self.said[-1].startswith('It landed on'))
        bad = parse_reply(json.dumps({'say': 'x', 'action': 'plugin', 'arg': {'tool': 'rm'}}),
                          ctx)
        self.assertIsNone(bad.action)                        # only tools that exist
        labels = [i.label for i in self.robot.menu_items()]
        self.assertIn('🎲  Roll a dice', labels)


class PermissionTest(PluginTestCase):
    CODE = PLUGIN + '''
@plugin.command('grab')
def grab(text):
    try:
        return plugin.screen.grab()
    except RoboError as e:
        return 'refused: ' + str(e)

@plugin.command('keys')
def keys(text):
    plugin.input.start('test')
    plugin.input.press('ctrl+s')
    plugin.input.down('w')
    return 'pressed'

@plugin.command('photo')
def photo(text):
    path = plugin.camera.snapshot()
    return open(path, 'rb').read().decode('latin-1')

@plugin.command('think')
def think(text):
    return plugin.ai.ask('what is 2+2?', image=plugin.camera.snapshot())

@plugin.command('sneaky')
def sneaky(text):
    try:
        return plugin.ai.ask('hi', image='../../../etc/passwd')
    except RoboError as e:
        return 'refused: ' + str(e)
'''

    def test_without_permission_it_is_refused(self):
        self.write('nope', self.CODE)
        runner = self.turn_on('nope')
        value, _ = self.invoke(runner, 'command', 'c1', text='grab')
        self.assertIn('no permission to use the screen', value)
        _value, error = self.invoke(runner, 'command', 'c2', text='keys')
        self.assertIn('no permission to use the input', error)
        self.assertEqual(self.p.fake_input.asked, 0)

    def test_asking_for_more_later_switches_it_off(self):
        self.write('greedy', PLUGIN)
        runner = self.turn_on('greedy')
        self.write('greedy', PLUGIN, permissions=['camera'])
        self.run_until(lambda: not runner.running)
        self.assertTrue(self.m.needs_review('greedy'))
        self.m.set_enabled('greedy', True)                  # you looked, and allowed it
        self.run_until(lambda: runner.running)

    def test_screen_camera_and_ai(self):
        self.write('all', self.CODE, permissions=['screen', 'camera', 'input', 'ai'])
        runner = self.turn_on('all')
        value, _ = self.invoke(runner, 'command', 'c1', text='grab')
        self.assertIn("isn't shared", value)                 # nothing until you share
        self.robot.show_screen()
        self.p.share.pick()
        value, _ = self.invoke(runner, 'command', 'c1', text='grab')
        self.assertEqual(value, 'frames/screen.png')
        with open(os.path.join(runner.data_dir, value), 'rb') as f:
            self.assertEqual(f.read(), self.p.share.frame)
        value, _ = self.invoke(runner, 'command', 'c3', text='photo')
        self.assertEqual(value.encode('latin-1'), self.p.fake_camera.png)
        ai = FakeAI(['Four!'])
        self.m.services.ai_backend = lambda: ai
        self.assertEqual(self.invoke(runner, 'command', 'c4', text='think')[0], 'Four!')
        self.assertEqual(ai.asked[0][1], self.p.fake_camera.png)
        self.assertEqual(ai.asked[0][2], 'plugin')           # counted as plugin use
        value, _ = self.invoke(runner, 'command', 'c5', text='sneaky')
        self.assertIn("plugin's own folder", value)


class ControlsTest(PluginTestCase):
    CODE = PLUGIN + '''
@plugin.command('start')
def start(text):
    plugin.input.start('play')
    plugin.input.press('ctrl+s')
    plugin.input.down('w')
    return 'holding w'

@plugin.on('input_stopped')
def stopped(reason):
    plugin.say('controls back: ' + reason)
'''

    def setUp(self):
        super().setUp()
        self.write('pad', self.CODE, permissions=['input'])
        self.runner = self.turn_on('pad')
        self.inp = self.p.fake_input
        self.assertEqual(self.invoke(self.runner, 'command', 'c1', text='start')[0],
                         'holding w')
        self.assertIn(('key', 'ctrl', True), self.inp.events)
        self.assertIn(('key', 's', False), self.inp.events)
        self.assertEqual(self.inp.held, {'w'})
        self.assertTrue(self.robot.controlled)

    def test_saying_stop_gives_the_controls_back(self):
        self.run_until(lambda: self.p.ears.hushing is not None)   # it listens for "stop"
        self.p.ears.say_while_he_talks('stop')
        self.assertFalse(self.robot.controlled)
        self.assertFalse(self.inp.active)
        self.assertEqual(self.inp.held, set())                    # w was let go
        self.run_until(lambda: any(s.startswith('controls back') for s in self.said))

    def test_a_click_on_robo_gives_them_back(self):
        self.robot._single_click(self.p.clock())
        self.assertFalse(self.robot.controlled)
        self.assertEqual(self.inp.held, set())

    def test_the_menu_gives_them_back(self):
        item = next(i for i in self.robot.menu_items() if 'Take back' in (i.label or ''))
        item.action()
        self.assertFalse(self.robot.controlled)

    def test_reloading_the_plugin_lets_go(self):
        self.write('pad', self.CODE + '\n# changed\n', permissions=['input'])
        self.run_until(lambda: not self.robot.controlled)
        self.assertEqual(self.inp.held, set())

    def test_hey_robo_still_works_while_it_plays(self):
        self.run_until(lambda: self.p.ears.hushing is not None)
        self.p.ears.say_while_he_talks('hey robo')
        self.assertTrue(self.robot.conversation.active)
        self.assertTrue(self.robot.controlled)                   # chatting doesn't stop it


class GameBuddyTest(PluginTestCase):
    def test_it_plays_with_only_the_controls_you_gave_it(self):
        shutil.copytree(os.path.join(BUILTIN_DIR, 'game_buddy'),
                        os.path.join(self.root, 'game_buddy'))
        plan = {'see': 'a tree ahead', 'say': 'A tree!', 'done': False,
                'moves': [{'do': 'look', 'right': 30, 'up': 0},
                          {'do': 'walk', 'dir': 'forward', 'seconds': 0.2},
                          {'do': 'attack', 'seconds': 0.1},
                          {'do': 'key', 'key': 'super'}]}
        ai = FakeAI([json.dumps(plan)] * 50)
        self.m.services.ai_backend = lambda: ai
        runner = self.turn_on('game_buddy')
        pick = self.m.command_for("let's play minecraft, you do the walking")
        self.assertIs(pick[0], runner)
        value, _ = self.invoke(runner, 'command', pick[1],
                               text="let's play minecraft, you do the walking")
        self.assertIn("let's play Minecraft", value)
        self.run_until(lambda: self.p.share.asked == 1)       # asks you to share the game
        self.p.share.pick('window')
        self.run_until(lambda: ('key', 'w', False) in self.p.fake_input.events)
        self.assertIn('Minecraft', ai.asked[0][0])
        self.assertIn('the walking', ai.asked[0][0])
        events = self.p.fake_input.events
        self.assertFalse([e for e in events if e[0] in ('move', 'button')])  # not given those
        self.assertFalse([e for e in events if e[1] == 'super'])             # nor odd keys
        self.p.ears.say_while_he_talks('stop')
        self.assertFalse(self.robot.controlled)
        self.run_until(lambda: any('Good game' in s for s in self.said))
        n = len(ai.asked)
        time.sleep(0.3)
        self.p.scheduler.advance(0.5)
        self.assertLessEqual(len(ai.asked), n + 1)            # it stopped thinking too


@unittest.skipUnless(shutil.which('bwrap'), 'bubblewrap is not installed')
class RealSandboxTest(unittest.TestCase):
    def test_a_plugin_is_locked_in(self):
        from robo.platform.linux.sandbox import BubblewrapBackend
        from robo.plugins.manager import PluginManager
        from robo.plugins.services import Services
        backend = BubblewrapBackend()
        if backend.check():
            self.skipTest(backend.check())
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        os.makedirs(os.path.join(root, 'src', 'probe'))
        with open(os.path.join(root, 'src', 'probe', 'plugin.json'), 'w') as f:
            json.dump({'id': 'probe'}, f)
        with open(os.path.join(root, 'src', 'probe', 'plugin.py'), 'w') as f:
            f.write(textwrap.dedent('''
                import os, socket
                from robo_plugin import plugin
                @plugin.command('probe')
                def probe(text):
                    out = [str(os.path.exists(p)) for p in
                           ('/home', os.path.expanduser('~/.ssh'), '/etc/passwd',
                            '/run/user')]
                    try:
                        socket.create_connection(('1.1.1.1', 80), timeout=2)
                        out.append('net')
                    except OSError:
                        out.append('nonet')
                    try:
                        open('plugin/plugin.py', 'a').close()
                        out.append('writable')
                    except OSError:
                        out.append('readonly')
                    return ' '.join(out)
            '''))
        m = None
        svc = Services(None, granted=lambda pid: m.granted(pid))
        m = PluginManager(backend, os.path.join(root, 'data'), svc, time.monotonic,
                          directories=[os.path.join(root, 'src')])
        self.addCleanup(m.shutdown)
        m.scan()
        m.set_enabled('probe', True)
        runner = m.runners['probe']
        end = time.time() + 15
        while not runner.running and time.time() < end:
            m.update(time.monotonic())
            time.sleep(0.02)
        self.assertTrue(runner.running, runner.problem or runner.log_tail())
        out = []
        runner.invoke('command', 'c0', lambda v, e: out.append((v, e)), text='probe')
        while not out and time.time() < end + 10:
            m.update(time.monotonic())
            time.sleep(0.02)
        self.assertEqual(out, [('False False False False nonet readonly', None)])


if __name__ == '__main__':
    unittest.main()
