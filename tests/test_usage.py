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
        self.assertIn("don't know how much of your plan is left", text)
        self.led.hit_limit('Limit reached, resets 6pm')
        self.assertIn('resets 6pm', self.led.spoken())
        self.assertTrue(any('Today: 92.0k in' in l for l in self.led.lines()))


    def test_plan_windows_from_claude(self):
        self.assertEqual(self.led.plan_windows(), [])
        now = 1_000_000.0
        self.led.record_limits({'status': 'allowed', 'rateLimitType': 'five_hour',
                                'unifiedWindows': {
                                    'seven_day': {'utilization': 0.09, 'resetsAt': now + 9e4},
                                    'five_hour': {'utilization': 0.12, 'resetsAt': now + 600},
                                    'seven_day_opus': {'utilization': 0.5},
                                    'seven_day_omelette': {'utilization': 0.3}}})
        ws = self.led.plan_windows()
        self.assertEqual([(w.key, w.used) for w in ws],
                         [('five_hour', 0.12), ('seven_day', 0.09), ('seven_day_opus', 0.5)])
        self.assertEqual(ws[0].label, 'Session (5 hours)')
        self.assertEqual(self.led.window_for_model('claude-opus-5-5').key, 'seven_day_opus')
        self.assertIsNone(self.led.window_for_model('haiku'))
        again = Ledger(self.path, today=self.today, clock=lambda: now + 700)
        self.assertEqual(again.plan_windows()[0].used, 0.0)        # the session has reset
        self.led.record('chat', Usage(10, 10))
        self.assertIn('12 percent of this session and 9 percent of this week',
                      self.led.spoken())
        self.led.record_limits({'unifiedWindows': {}})              # nothing useful: kept
        self.assertEqual(len(self.led.plan_windows()), 3)

    def test_model_names(self):
        from robo.agents.usage import pretty_model
        self.assertEqual(pretty_model('claude-haiku-5-5'), 'Haiku 5.5')
        self.assertEqual(pretty_model('claude-sonnet-4-5-20250929'), 'Sonnet 4.5')
        self.assertEqual(pretty_model('opus'), 'Opus')
        self.assertEqual(pretty_model(''), '')
        self.led.record('chat', Usage(1, 1, model='claude-haiku-5-5'))
        self.assertEqual(Ledger(self.path, today=self.today).last_model, 'claude-haiku-5-5')


class ClaudeStreamTest(unittest.TestCase):
    EVENT = {'type': 'rate_limit_event', 'rate_limit_info': {
        'status': 'allowed', 'unifiedWindows': {
            'five_hour': {'utilization': 0.4, 'resetsAt': 4_000_000_000, 'status': 'allowed'}}}}

    def setUp(self):
        import robo.agents.claude as claude_mod
        self.mod, self.old = claude_mod, claude_mod.LEDGER
        claude_mod.LEDGER = Ledger()

    def tearDown(self):
        self.mod.LEDGER = self.old

    def test_chat_reads_the_plan_usage(self):
        backend = make_backend('claude', tempfile.gettempdir())
        argv = backend.command('hi', 'sys')
        self.assertEqual(argv[argv.index('--output-format') + 1], 'stream-json')
        img_argv, _ = backend.command_with_image('look', 'sys', b'png')
        self.assertEqual(img_argv.count('--verbose'), 1)
        out = '\n'.join(json.dumps(m) for m in ({'type': 'system', 'subtype': 'init'},
                                                 self.EVENT, RESULT))
        answer = backend.parse(out, '', 0)
        self.assertEqual(answer.text, 'Beep!')
        self.assertEqual(self.mod.LEDGER.plan_windows()[0].used, 0.4)

    def test_tasks_read_it_too(self):
        backend = make_backend('claude', tempfile.gettempdir())
        self.assertIsNone(backend.task_event(json.dumps(self.EVENT)))
        self.assertEqual(self.mod.LEDGER.plan_windows()[0].key, 'five_hour')


class UsageCardTest(unittest.TestCase):
    def setUp(self):
        self.led, usage_mod.LEDGER = usage_mod.LEDGER, Ledger()

    def tearDown(self):
        usage_mod.LEDGER = self.led

    def test_what_the_card_says(self):
        from robo.core.usage_card import build_card
        led = usage_mod.LEDGER
        self.assertEqual(build_card(Settings(agent='off'), led).title, 'AI brain: off')
        card = build_card(Settings(agent='claude'), led)
        self.assertEqual((card.title, card.bars), ("Claude · Claude Code's default", []))
        led.record('chat', Usage(1, 1, model='claude-opus-5-5'))
        led.record_limits({'unifiedWindows': {'five_hour': {'utilization': 0.25},
                                              'seven_day': {'utilization': 0.1},
                                              'seven_day_opus': {'utilization': 0.6}}})
        card = build_card(Settings(agent='claude'), led)
        self.assertEqual(card.title, 'Claude · Opus 5.5')
        self.assertEqual([(l, u) for l, u, _ in card.bars],
                         [('Session', 0.25), ('Week (Opus)', 0.6)])
        card = build_card(Settings(agent='claude', agent_model='haiku'), led)
        self.assertEqual(card.title, 'Claude · Haiku')               # what you picked
        self.assertEqual([l for l, _, _ in card.bars], ['Session', 'Week'])
        self.assertIn("doesn't tell", build_card(Settings(agent='gemini'), led).note)

    def test_hovering_shows_it(self):
        from robo.core import usage_card
        from robo.platform.base import PointerEvent
        p = HeadlessPlatform()
        robot = build_companion(Settings(dress_up_every=0, evil_after=0, chattiness='off'), p)
        clock = [100.0]
        robot.clock = lambda: clock[0]
        s = robot.scale
        on_him = PointerEvent(0, 85 * s, 200 * s, 0, 0)
        robot.pointer_motion(on_him)
        robot._update_hover(clock[0])
        self.assertFalse(robot.hover.visible)
        clock[0] += usage_card.HOVER_SECONDS + 0.1
        robot.pointer_motion(on_him)                                 # still resting there
        robot._update_hover(clock[0])
        self.assertTrue(robot.hover.visible)
        p.window.redraw()                                            # draws without trouble
        robot.pointer_leave()
        clock[0] += usage_card.POP_OUT + 0.1
        robot._update_hover(clock[0])
        self.assertFalse(robot.hover.visible)
        robot.pointer_motion(PointerEvent(0, 2 * s, 2 * s, 0, 0))     # beside him: nothing
        clock[0] += 5
        robot._update_hover(clock[0])
        self.assertFalse(robot.hover.visible)


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
