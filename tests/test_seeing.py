"""Showing Robo your screen: only when you choose to, and always visibly.

The platform's ScreenShare is faked (robo.platform.headless.FakeScreenShare):
pick() is you choosing a screen in the system's picker.
"""
import json
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from robo.agents import make_backend  # noqa: E402
from robo.agents.base import AgentAnswer  # noqa: E402
from robo.app import build_companion  # noqa: E402
from robo.config import Settings  # noqa: E402
from robo.conversation import Context, RuleBrain  # noqa: E402
from robo.conversation.agent import AgentBrain, parse_reply  # noqa: E402
from robo.core import companion as companion_mod  # noqa: E402
from robo.core.pose import build_pose  # noqa: E402
from robo.platform.headless import HeadlessPlatform  # noqa: E402


class FakeBackend:
    """Stands in for Claude: remembers what it was shown."""
    name = 'Claude'
    supports_images = True
    supports_tasks = False
    model = ''

    def __init__(self):
        self.asked = []

    def ask(self, prompt, system, kind='chat', image=None):
        self.asked.append((prompt, image))
        return AgentAnswer(json.dumps({'say': 'I see a spreadsheet!', 'mood': 'happy'}))

    def forget(self):
        pass

    def cancel(self):
        pass


def make_robot(agent='claude'):
    p = HeadlessPlatform()
    robot = build_companion(Settings(agent=agent, dress_up_every=0, evil_after=0,
                                     chattiness='off'), p)
    robot.rng.seed(5)
    said = []
    robot.conversation.announce = lambda text, mood='happy': said.append(text)
    return robot, p, said


def labels(robot):
    return [i.label or '' for i in robot.menu_items()]


class ConsentTest(unittest.TestCase):
    def test_nothing_is_seen_until_you_pick(self):
        robot, p, _said = make_robot()
        self.assertIsNone(robot.look_at_screen())
        self.assertTrue(any('Show Robo my screen' in l for l in labels(robot)))
        robot.show_screen()
        self.assertEqual(p.share.asked, 1)                   # the system picker asks you
        self.assertIsNone(robot.seeing)
        self.assertIsNone(robot.look_at_screen())            # still nothing while it asks
        self.assertTrue(any('Stop showing' in l for l in labels(robot)))
        p.share.pick()
        self.assertEqual(robot.look_at_screen(), p.share.frame)

    def test_cancelling_the_picker_shows_nothing(self):
        robot, p, said = make_robot()
        robot.show_screen()
        p.share.cancel()
        self.assertIsNone(robot.seeing)
        self.assertIsNone(robot.look_at_screen())
        self.assertEqual(said, [])
        self.assertTrue(any('Show Robo my screen' in l for l in labels(robot)))

    def test_talking_never_starts_a_share(self):
        robot, p, _said = make_robot()
        ctx = robot.conversation.context()
        for heard in ('look at my screen', 'can you see this', 'help me with this'):
            reply = RuleBrain(random.Random(1)).respond(heard, ctx)
            self.assertIn('Right-click me', reply.text)
            self.assertIsNone(reply.action)
        r = parse_reply(json.dumps({'say': 'Let me look!', 'action': 'show_screen'}), ctx)
        self.assertIsNone(r.action)                          # the AI has no way to start one
        self.assertEqual(p.share.asked, 0)

    def test_no_sharing_without_a_brain_that_can_see(self):
        robot, p, _said = make_robot(agent='off')
        self.assertFalse(robot.can_see_screen())
        self.assertFalse(any('Show Robo my screen' in l for l in labels(robot)))
        robot.show_screen()
        self.assertEqual(p.share.asked, 0)


class WhileSharingTest(unittest.TestCase):
    def setUp(self):
        self.robot, self.p, self.said = make_robot()
        self.robot.show_screen()
        self.p.share.pick()

    def test_he_shows_that_he_is_looking(self):
        pose = build_pose(self.robot, self.robot.clock())
        self.assertTrue(pose.seeing)
        self.assertEqual(pose.antenna, 'seeing')
        self.assertEqual(self.robot.menu_items()[0].label, '⏹  Stop showing my screen')

    def test_your_question_comes_with_a_fresh_picture(self):
        backend = FakeBackend()
        brain = AgentBrain(RuleBrain(), '/tmp')
        brain.backend = backend
        self.robot.conversation.brain = brain
        answers = []
        ctx = self.robot.conversation.context()
        from dataclasses import replace
        ctx = replace(ctx, screen=self.robot.look_at_screen())
        brain.ask('what is in this cell?', ctx, answers.append)
        import time
        t0 = time.time()
        while not answers and time.time() - t0 < 5:
            brain.update(0)
            time.sleep(0.01)
        prompt, image = backend.asked[0]
        self.assertEqual(image, self.p.share.frame)
        self.assertIn('SHOWING YOU their whole screen', prompt)
        self.assertEqual(answers[0].text, 'I see a spreadsheet!')

    def test_even_short_questions_go_to_the_eyes(self):
        brain = AgentBrain(RuleBrain(), '/tmp')
        brain.backend = FakeBackend()
        ctx = self.robot.conversation.context()
        self.assertFalse(brain._local('what time is it', ctx))   # he looks, then answers
        self.assertFalse(brain._local('can you see this', ctx))
        self.assertTrue(brain._local('stop looking', ctx))

    def test_stopping(self):
        self.robot.stop_showing()
        self.assertIsNone(self.robot.seeing)
        self.assertIsNone(self.robot.look_at_screen())
        self.assertFalse(self.p.share.indicator)
        self.assertIn("can't see your screen any more", self.said[-1])
        self.assertFalse(build_pose(self.robot, self.robot.clock()).seeing)

    def test_saying_stop_looking(self):
        r = RuleBrain(random.Random(1)).respond('stop looking', self.robot.conversation.context())
        self.assertEqual(r.action, 'stop_seeing')
        from robo.core import personality
        personality.on_reply(self.robot, r, self.robot.clock())
        self.assertIsNone(self.robot.seeing)

    def test_it_stops_when_nobody_asks_for_a_while(self):
        self.robot.conversation.stop()
        self.p.scheduler.advance(companion_mod.SHARE_IDLE_SECONDS + 2)
        self.assertIsNone(self.robot.seeing)
        self.assertFalse(self.p.share.indicator)


class ClaudeImageTest(unittest.TestCase):
    def test_the_picture_goes_in_with_every_tool_off(self):
        b = make_backend('claude', '/tmp', 'haiku')
        argv, stdin = b.command_with_image('what is this?', 'SYS', b'\x89PNG')
        self.assertEqual(argv[argv.index('--tools') + 1], '')
        self.assertEqual(argv[argv.index('--input-format') + 1], 'stream-json')
        self.assertEqual(argv[argv.index('--output-format') + 1], 'stream-json')
        self.assertNotIn('what is this?', argv)                    # it's on stdin
        msg = json.loads(stdin)
        kinds = [c['type'] for c in msg['message']['content']]
        self.assertEqual(kinds, ['image', 'text'])

    def test_reads_the_stream_json_result(self):
        b = make_backend('claude', '/tmp')
        out = '\n'.join(json.dumps(x) for x in (
            {'type': 'system', 'subtype': 'init'},
            {'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': 'hm'}]}},
            {'type': 'result', 'subtype': 'success', 'is_error': False, 'result': 'A cat!',
             'session_id': 's9', 'usage': {'input_tokens': 1500, 'output_tokens': 20}}))
        a = b.parse(out, '', 0)
        self.assertEqual((a.text, a.session, a.usage.input), ('A cat!', 's9', 1500))


if __name__ == '__main__':
    unittest.main()
