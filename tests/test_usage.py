"""How many AI tokens Robo used (robo/agents/usage.py)."""
import json
import os
import random
import sys
import tempfile
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from robo.agents import make_backend  # noqa: E402
from robo.agents.base import AgentError  # noqa: E402
from robo.agents import usage as usage_mod  # noqa: E402
from robo.agents.usage import Ledger, Usage, from_claude  # noqa: E402
from robo.app import build_companion  # noqa: E402
from robo.config import Settings  # noqa: E402
from robo.conversation import Context, RuleBrain  # noqa: E402
from robo.conversation.agent import AgentBrain  # noqa: E402
from robo.platform.headless import HeadlessPlatform  # noqa: E402

# what `claude -p --output-format json` prints (trimmed)
RESULT = {'type': 'result', 'subtype': 'success', 'is_error': False, 'result': 'Beep!',
          'session_id': 's1', 'total_cost_usd': 0.0188,
          'usage': {'input_tokens': 4, 'cache_creation_input_tokens': 747,
                    'cache_read_input_tokens': 5035, 'output_tokens': 75},
          'modelUsage': {'claude-opus-5-5': {'costUSD': 0.0188}}}


class Today:
    def __init__(self):
        self.d = date(2026, 11, 13)

    def __call__(self):
        return self.d


class FromClaudeTest(unittest.TestCase):
    def test_reads_the_result(self):
        u = from_claude(RESULT)
        self.assertEqual((u.input, u.output, u.cache_read), (4 + 747 + 5035, 75, 5035))
        self.assertEqual(u.model, 'claude-opus-5-5')
        self.assertAlmostEqual(u.cost, 0.0188)

    def test_nothing_to_read(self):
        self.assertIsNone(from_claude({'type': 'result'}))
        self.assertIsNone(from_claude('nope'))
        self.assertIsNone(from_claude({'usage': {'input_tokens': 'lots'}}))

    def test_chat_answers_are_counted(self):
        led = usage_mod.LEDGER
        before = led.day()['chat']['calls']
        backend = make_backend('claude', tempfile.gettempdir())
        answer = backend.parse(json.dumps(RESULT), '', 0)
        self.assertEqual(answer.usage.output, 75)
        self.assertEqual(led.day()['chat']['calls'], before)     # parse alone records nothing

    def test_a_limit_is_remembered(self):
        led, usage_mod.LEDGER = usage_mod.LEDGER, Ledger()
        import robo.agents.claude as claude_mod
        old = claude_mod.LEDGER
        claude_mod.LEDGER = usage_mod.LEDGER
        try:
            backend = make_backend('claude', tempfile.gettempdir())
            bad = {**RESULT, 'is_error': True, 'subtype': 'error',
                   'result': 'Claude AI usage limit reached, resets 6pm'}
            with self.assertRaises(AgentError) as e:
                backend.parse(json.dumps(bad), '', 1)
            self.assertIn('used up', e.exception.spoken)
            self.assertEqual(e.exception.usage.output, 75)       # it still counts
            self.assertIn('resets 6pm', usage_mod.LEDGER.recent_limit()['message'])
            ev = backend.task_event(json.dumps(bad))
            self.assertEqual(ev['usage'].output, 75)
        finally:
            claude_mod.LEDGER = old
            usage_mod.LEDGER = led


class LedgerTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, 'usage.json')
        self.today = Today()
        self.led = Ledger(self.path, today=self.today, clock=lambda: 1_000_000.0)

    def tearDown(self):
        self.dir.cleanup()

    def test_adds_up_by_day_and_kind(self):
        self.led.record('chat', Usage(1000, 100, cost=0.01, model='m'))
        self.led.record('chat', Usage(2000, 200, cost=0.02, model='m'))
        self.led.record('design', Usage(50_000, 5000, cost=0.5, model='m'))
        self.led.record('chat', None)                            # nothing reported: no-op
        day = self.led.day()
        self.assertEqual(day['chat']['calls'], 2)
        self.assertEqual(day['all']['input'], 53_000)
        self.assertEqual(self.led.tokens_today(), 58_300)
        self.today.d += timedelta(days=1)
        self.assertEqual(self.led.tokens_today(), 0)
        self.assertEqual(self.led.week()['all']['calls'], 3)

    def test_kept_across_restarts_and_trimmed(self):
        self.led.record('task', Usage(10, 5, cost=0.001))
        again = Ledger(self.path, today=self.today)
        self.assertEqual(again.day()['task']['output'], 5)
        self.today.d += timedelta(days=usage_mod.KEEP_DAYS + 5)
        again.record('chat', Usage(1, 1))
        self.assertEqual(len(again.days), 1)

    def test_says_it_out_loud(self):
        self.assertIn("haven't used any", self.led.spoken())
        self.led.record('chat', Usage(12_000, 400, cost=0.31))
        self.led.record('design', Usage(80_000, 9000, cost=1.2))
        text = self.led.spoken()
        self.assertIn('about 101 thousand tokens', text)
        self.assertIn('1 chat and 1 outfit design', text)
        self.assertIn('1.51 dollars', text)
        self.assertIn("doesn't tell me how much of your plan is left", text)
        self.led.hit_limit('Limit reached, resets 6pm')
        self.assertIn('resets 6pm', self.led.spoken())
        self.assertTrue(any('Today: 92.0k in' in l for l in self.led.lines()))


class RobotTest(unittest.TestCase):
    def setUp(self):
        self.led, usage_mod.LEDGER = usage_mod.LEDGER, Ledger()
        import robo.core.talk as talk_mod
        self.talk_mod, self.old_talk = talk_mod, talk_mod.LEDGER
        talk_mod.LEDGER = usage_mod.LEDGER

    def tearDown(self):
        usage_mod.LEDGER = self.led
        self.talk_mod.LEDGER = self.old_talk

    def test_asking_about_tokens_costs_none(self):
        usage_mod.LEDGER.record('chat', Usage(3000, 300, cost=0.05))
        robot = build_companion(Settings(dress_up_every=0, evil_after=0, chattiness='off'),
                                HeadlessPlatform())
        ctx = robot.conversation.context()
        self.assertIn('3 thousand tokens', ctx.usage_text)
        reply = RuleBrain(random.Random(1)).respond('how many tokens have you used', ctx)
        self.assertIn('3 thousand tokens', reply.text)
        brain = AgentBrain(RuleBrain(), tempfile.gettempdir())
        self.assertTrue(brain._local('how many tokens have you used today', ctx))

    def test_the_budget_stops_his_own_ideas(self):
        robot = build_companion(Settings(dress_up_every=0, evil_after=0, daily_budget='25000'),
                                HeadlessPlatform())
        self.assertTrue(robot.within_budget())
        usage_mod.LEDGER.record('chat', Usage(30_000, 10))
        self.assertFalse(robot.within_budget())
        robot.apply_settings(robot.settings.with_changes(daily_budget='off'))
        self.assertTrue(robot.within_budget())
        self.assertEqual(Settings(daily_budget='lots').daily_budget, 'off')


class ModelTest(unittest.TestCase):
    def test_settings_keep_both_models(self):
        s = Settings.from_dict({'agent': 'claude', 'agent_model': 'sonnet',
                                'task_model': ' opus '})
        self.assertEqual((s.agent_model, s.task_model), ('sonnet', 'opus'))
        self.assertEqual(Settings.from_dict(s.to_dict()).task_model, 'opus')

    def test_chats_and_tasks_use_their_own_model(self):
        from robo.app import RoboApp
        p = HeadlessPlatform()
        app = RoboApp(Settings(agent='claude', agent_model='haiku', task_model='opus',
                               dress_up_every=0, evil_after=0), p)
        self.assertEqual(app.brain.backend.model, 'haiku')
        self.assertIn('haiku', app.brain.backend.command('hi', 'sys'))
        task_agent = app._task_agent()
        self.assertEqual(task_agent.model, 'opus')
        argv = task_agent.task_command('do it', 'sys', '/tmp/mcp.json', 5)
        self.assertEqual(argv[argv.index('--model') + 1], 'opus')
        app.apply(app.settings.with_changes(agent_model='sonnet'), save=False)
        self.assertEqual(app.brain.backend.model, 'sonnet')

    def test_every_brain_offers_its_default(self):
        from robo.agents import BACKENDS
        for cls in BACKENDS.values():
            self.assertEqual(cls.MODELS[0][0], '')


if __name__ == '__main__':
    unittest.main()
