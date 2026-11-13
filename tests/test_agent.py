"""The AI brain: AgentBrain and the agent CLIs (faked, so no login or network needed).

Run with:  python3 -m unittest discover -s tests
"""
import json
import os
import random
import stat
import sys
import tempfile
import textwrap
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from robo.agents import AgentAnswer, AgentBackend, AgentError, make_backend  # noqa: E402
from robo.agents.base import AgentCancelled  # noqa: E402
from robo.app import build_companion  # noqa: E402
from robo.config import Settings  # noqa: E402
from robo.conversation import AgentBrain, RuleBrain  # noqa: E402
from robo.conversation.agent import parse_reply, spoken  # noqa: E402
from robo.conversation.brain import Context  # noqa: E402
from robo.platform.headless import HeadlessPlatform  # noqa: E402

CTX = Context(characters=('pirate', 'chef'), travel=('fly',))


class FakeBackend(AgentBackend):
    """Answers instantly from a list; records what it was asked."""
    id = name = 'fake'

    def __init__(self, answers=(), error=None, delay=0.0):
        super().__init__(tempfile.gettempdir())
        self.answers = list(answers)
        self.error = error
        self.delay = delay
        self.asked = []

    def ask(self, prompt, system):
        self.asked.append(prompt)
        time.sleep(self.delay)
        if self._cancelled:
            raise AgentCancelled()
        if self.error:
            raise self.error
        return AgentAnswer(self.answers.pop(0) if self.answers else '{"say": "Beep!"}')

    def cancel(self):
        self._cancelled = True


def brain_with(backend):
    b = AgentBrain(RuleBrain(random.Random(1)), tempfile.gettempdir())
    b.backend, b.agent_id = backend, 'fake'
    return b


def wait_reply(brain, question, ctx=CTX, timeout=5):
    got = []
    brain.ask(question, ctx, got.append)
    t0 = time.time()
    while not got and time.time() - t0 < timeout:
        brain.update(0)
        time.sleep(0.01)
    return got[0] if got else None


class ReplyParsingTest(unittest.TestCase):
    def test_json_answer(self):
        r = parse_reply('{"say": "Ahoy!", "mood": "laugh", "action": "dress_up", "arg": "pirate"}',
                        CTX)
        self.assertEqual((r.text, r.mood, r.action, r.action_arg),
                         ('Ahoy!', 'laugh', 'dress_up', 'pirate'))

    def test_code_fences_and_plain_text(self):
        self.assertEqual(parse_reply('```json\n{"say": "Hi"}\n```', CTX).text, 'Hi')
        r = parse_reply('Just a plain **answer** 🤖', CTX)
        self.assertEqual((r.text, r.action), ('Just a plain answer', None))

    def test_only_safe_known_actions(self):
        for raw in ('{"say": "x", "action": "start_task"}',
                    '{"say": "x", "action": "rm -rf"}',
                    '{"say": "x", "action": "dress_up", "arg": "nobody"}'):
            self.assertIsNone(parse_reply(raw, CTX).action, raw)
        grounded = Context(travel=())
        self.assertIsNone(parse_reply('{"say": "x", "action": "travel"}', grounded).action)
        self.assertTrue(parse_reply('{"say": "Night", "action": "nap"}', CTX).end)
        self.assertEqual(parse_reply('{"say": "x", "mood": "furious"}', CTX).mood, 'happy')

    def test_spoken_text(self):
        self.assertEqual(spoken('# Title\n- one\n- two 😀 see https://x.org'),
                         'Title one two see a link')
        long = 'Sentence number one is here. ' * 60
        self.assertLessEqual(len(spoken(long)), 600)
        self.assertTrue(spoken(long).endswith('.'))


class AgentBrainTest(unittest.TestCase):
    def test_questions_go_to_the_agent(self):
        fake = FakeBackend(['{"say": "Black holes are very hungry.", "mood": "focus"}'])
        r = wait_reply(brain_with(fake), 'what is a black hole')
        self.assertEqual(r.text, 'Black holes are very hungry.')
        self.assertIn('what is a black hole', fake.asked[0])
        self.assertIn('[Robo status:', fake.asked[0])          # he tells it about himself

    def test_commands_stay_local(self):
        fake = FakeBackend()
        brain = brain_with(fake)
        for cmd in ('do a task', 'abort task', 'dress up as a pirate', 'what time is it',
                    'goodbye', 'fly around'):
            self.assertIsNotNone(wait_reply(brain, cmd), cmd)
        self.assertEqual(fake.asked, [])
        wait_reply(brain, 'dress up as a pirate and tell me a story about the sea')
        self.assertEqual(len(fake.asked), 1)                    # longer request: the agent

    def test_no_agent_means_rules_only(self):
        brain = AgentBrain(RuleBrain(random.Random(1)), tempfile.gettempdir())
        brain.configure(Settings())
        self.assertIsNone(brain.backend)
        self.assertEqual(wait_reply(brain, 'explain quantum physics').mood, 'surprised')  # "Beep?"

    def test_problems_are_said_kindly(self):
        fake = FakeBackend(error=AgentError('claude: not logged in', 'Please log me in!'))
        r = wait_reply(brain_with(fake), 'how are volcanoes made')
        self.assertEqual((r.text, r.mood), ('Please log me in!', 'sad'))

    def test_hushing_drops_the_answer(self):
        fake = FakeBackend(['{"say": "too late"}'], delay=0.3)
        brain = brain_with(fake)
        got = []
        brain.ask('tell me a long story', CTX, got.append)
        brain.cancel()
        t0 = time.time()
        while time.time() - t0 < 0.6:
            brain.update(0)
            time.sleep(0.01)
        self.assertEqual(got, [])
        self.assertFalse(brain.thinking)

    def test_answers_arrive_on_the_main_thread_only(self):
        fake = FakeBackend(['{"say": "hi"}'], delay=0.05)
        brain = brain_with(fake)
        got = []
        brain.ask('hello there friend how are you today', CTX, got.append)
        time.sleep(0.2)
        self.assertEqual(got, [])                               # nothing until update()
        brain.update(0)
        self.assertEqual(len(got), 1)

    def test_forgets_after_a_long_break(self):
        fake = FakeBackend()
        brain = brain_with(fake)
        fake.session, fake.history = 'abc', [('a', 'b')]
        brain.conversation_ended(0)
        brain.conversation_started(60)
        self.assertEqual(fake.session, 'abc')
        brain.conversation_ended(100)
        brain.conversation_started(100 + 31 * 60)
        self.assertIsNone(fake.session)


class ConversationTest(unittest.TestCase):
    def test_talking_to_him_with_an_agent(self):
        p = HeadlessPlatform()
        robot = build_companion(Settings(dress_up_every=0, evil_after=0), p)
        fake = FakeBackend(['{"say": "The sky is blue because of sunlight scattering.", '
                            '"action": "wave"}'])
        brain = robot.conversation.brain
        brain.backend, brain.agent_id = fake, 'fake'
        said = []
        orig = robot.conversation._say
        robot.conversation._say = lambda r: (said.append(r), orig(r))
        robot.talk()
        for _ in range(100):
            if p.ears.listening:
                break
            p.scheduler.advance(0.1)
        p.ears.hear('why is the sky blue')
        for _ in range(100):
            if len(said) > 1:
                break
            p.scheduler.advance(0.05)
            time.sleep(0.005)
        self.assertEqual(said[-1].text, 'The sky is blue because of sunlight scattering.')

    def test_settings(self):
        self.assertEqual(Settings(agent='claude').agent, 'claude')
        self.assertEqual(Settings(agent='skynet').agent, 'off')
        s = Settings.from_dict({'agent': 'gemini', 'agent_model': 'gemini-2.5-flash'})
        self.assertEqual((s.agent, s.agent_model), ('gemini', 'gemini-2.5-flash'))


def fake_cli(folder, name, script):
    """Put a fake `name` program on PATH that runs `script` (Python)."""
    path = os.path.join(folder, name)
    with open(path, 'w') as f:
        f.write(f'#!{sys.executable}\nimport json, os, sys\nargs = sys.argv[1:]\n')
        f.write(textwrap.dedent(script))
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.bin = os.path.join(self.tmp.name, 'bin')
        os.makedirs(self.bin)
        self.work = os.path.join(self.tmp.name, 'agent')
        self.old_path = os.environ['PATH']
        os.environ['PATH'] = self.bin + os.pathsep + self.old_path
        os.environ['ANTHROPIC_API_KEY'] = 'sk-should-not-be-used'

    def tearDown(self):
        os.environ['PATH'] = self.old_path
        os.environ.pop('ANTHROPIC_API_KEY', None)
        self.tmp.cleanup()

    def test_claude_code_uses_its_login_and_no_tools(self):
        fake_cli(self.bin, 'claude', '''
            if args[:2] == ['auth', 'status']:
                print(json.dumps({"loggedIn": True, "subscriptionType": "pro"})); sys.exit()
            print(json.dumps({"type": "result", "subtype": "success", "is_error": False,
                              "session_id": "s-1",
                              "result": json.dumps({"say": "key" if "ANTHROPIC_API_KEY" in os.environ
                                                    else " ".join(args)})}))
        ''')
        claude = make_backend('claude', self.work)
        st = claude.status()
        self.assertTrue(st.ready and st.logged_in)
        self.assertIn('pro', st.detail)
        answer = claude.ask('hello', 'SYSTEM')
        said = json.loads(answer.text)['say']
        self.assertNotEqual(said, 'key')                        # API key never passed on
        self.assertIn('--tools  --restricted', said)            # no tools at all
        self.assertEqual(claude.session, 's-1')
        said = json.loads(claude.ask('again', 'SYSTEM').text)['say']
        self.assertIn('--resume s-1', said)                     # same conversation

    def test_claude_not_logged_in(self):
        fake_cli(self.bin, 'claude', '''
            print(json.dumps({"loggedIn": False})); sys.exit(1)
        ''')
        st = make_backend('claude', self.work).status()
        self.assertFalse(st.ready)
        self.assertIn('log in', st.fix)

    def test_claude_errors_become_friendly(self):
        fake_cli(self.bin, 'claude', '''
            print(json.dumps({"subtype": "success", "is_error": True,
                              "result": "Invalid API key · Please run /login"}))
        ''')
        with self.assertRaises(AgentError) as e:
            make_backend('claude', self.work).ask('hi', 'S')
        self.assertIn('log in', e.exception.spoken)

    def test_codex_reads_the_last_message_file(self):
        fake_cli(self.bin, 'codex', '''
            if args[:2] == ['login', 'status']:
                print("Logged in using ChatGPT"); sys.exit()
            out = args[args.index("--output-last-message") + 1]
            assert "--sandbox" in args and args[args.index("--sandbox") + 1] == "read-only"
            open(out, "w").write(json.dumps({"say": "codex says hi"}))
        ''')
        codex = make_backend('codex', self.work)
        self.assertTrue(codex.status().logged_in)
        self.assertEqual(json.loads(codex.ask('hi', 'S').text)['say'], 'codex says hi')
        self.assertEqual(os.listdir(self.work), [])             # temp answer file cleaned up
        codex.ask('and again', 'S')
        self.assertEqual(len(codex.history), 2)                 # it remembers for the CLI

    def test_gemini_json_and_errors(self):
        fake_cli(self.bin, 'gemini', '''
            if "boom" in args[1]:
                print(json.dumps({"error": {"type": "AuthError", "message": "login"}})); sys.exit(1)
            print(json.dumps({"response": "gemini says hi", "stats": {}}))
        ''')
        gemini = make_backend('gemini', self.work)
        self.assertEqual(gemini.ask('hi', 'S').text, 'gemini says hi')
        with self.assertRaises(AgentError) as e:
            gemini.ask('boom', 'S')
        self.assertIn('log in', e.exception.spoken)

    def test_missing_cli(self):
        os.environ['PATH'] = self.bin
        for agent in ('claude', 'codex', 'gemini'):
            backend = make_backend(agent, self.work)
            self.assertFalse(backend.status().installed)
            self.assertTrue(backend.status().fix)
            with self.assertRaises(AgentError):
                backend.ask('hi', 'S')

    def test_cancel_kills_a_slow_cli(self):
        fake_cli(self.bin, 'gemini', '''
            import time; time.sleep(30)
        ''')
        gemini = make_backend('gemini', self.work)
        import threading
        result = []

        def run():
            try:
                gemini.ask('hi', 'S')
            except BaseException as e:      # noqa: BLE001
                result.append(e)
        t = threading.Thread(target=run)
        t0 = time.time()
        t.start()
        time.sleep(0.5)
        gemini.cancel()
        t.join(5)
        self.assertLess(time.time() - t0, 5)
        self.assertIsInstance(result[0], AgentCancelled)


if __name__ == '__main__':
    unittest.main()
