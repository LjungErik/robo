"""Personality: memory, moods, speaking up on his own, and his more alive body.

Run with:  python3 -m unittest discover -s tests
"""
import json
import os
import random
import sys
import tempfile
import unittest
from datetime import date, datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from robo.app import build_companion  # noqa: E402
from robo.config import Settings  # noqa: E402
from robo.conversation import RuleBrain  # noqa: E402
from robo.conversation.agent import parse_reply  # noqa: E402
from robo.conversation.brain import Context  # noqa: E402
from robo.core import face as F  # noqa: E402
from robo.core import personality  # noqa: E402
from robo.core.initiative import Initiative, fill, in_quiet_hours, line_for  # noqa: E402
from robo.core.memory import Memory  # noqa: E402
from robo.core.mind import Mind, daylight_energy  # noqa: E402
from robo.core.pose import build_pose  # noqa: E402
from robo.design import REGISTRY  # noqa: E402
from robo.platform.base import PointerEvent  # noqa: E402
from robo.platform.headless import HeadlessPlatform  # noqa: E402


def make_robot(**settings):
    settings.setdefault('dress_up_every', 0)
    settings.setdefault('evil_after', 0)
    p = HeadlessPlatform()
    robot = build_companion(Settings(**settings), p)
    robot.rng.seed(2)
    return robot, p


class MemoryTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, 'memory.json')

    def tearDown(self):
        self.dir.cleanup()

    def test_remembers_across_restarts(self):
        m = Memory(self.path)
        m.remember_name('erik')
        self.assertTrue(m.remember('likes pizza'))
        self.assertFalse(m.remember('Likes pizza'))           # no duplicates
        m.remember_task('sort notes', 'done')
        again = Memory(self.path)
        self.assertEqual(again.name, 'Erik')
        self.assertEqual([f['text'] for f in again.facts], ['likes pizza'])
        self.assertIn('Erik', again.summary())
        self.assertIn('likes pizza', again.describe())

    def test_forgetting(self):
        m = Memory(self.path)
        m.remember_name('Erik')
        m.remember('has a cat called Mo')
        m.remember('likes jazz')
        self.assertEqual(m.forget('cat'), 1)
        self.assertEqual([f['text'] for f in m.facts], ['likes jazz'])
        m.forget('all')
        self.assertEqual((m.name, m.facts), ('', []))
        with open(self.path) as f:
            self.assertEqual(json.load(f)['facts'], [])

    def test_switched_off_keeps_nothing(self):
        m = Memory(self.path, enabled=False)
        self.assertFalse(m.remember('secret'))
        self.assertFalse(m.remember_name('Erik'))
        self.assertFalse(os.path.exists(self.path))
        self.assertIn('switched off', m.describe())

    def test_days_together(self):
        day = [date(2026, 1, 1)]
        m = Memory(self.path, today=lambda: day[0])
        self.assertEqual(m.saw_you(), 'first')
        self.assertIsNone(m.saw_you())                        # same day
        day[0] = date(2026, 1, 2)
        self.assertEqual(m.saw_you(), 'new_day')
        self.assertEqual(m.days_together, 2)


class MindTest(unittest.TestCase):
    def test_sleepy_at_night_awake_in_the_day(self):
        self.assertGreater(daylight_energy(10), 0.9)
        self.assertLess(daylight_energy(2), 0.2)
        self.assertTrue(Mind(hour=lambda: 1.0).sleepy)
        self.assertFalse(Mind(hour=lambda: 11.0).tired)

    def test_how_you_treat_him(self):
        m = Mind(Memory(), hour=lambda: 12.0)
        before = m.happiness
        m.patted()
        self.assertGreater(m.happiness, before)
        m.insulted()
        m.insulted()
        self.assertLess(m.happiness, before)
        bored = Mind(hour=lambda: 12.0)
        bored.update(3000, idle_seconds=5)                    # you're here, ignoring him
        self.assertTrue(bored.bored)
        bored.chatted()
        self.assertFalse(bored.bored)

    def test_picked_up_too_often_makes_him_grumpy(self):
        m = Mind(hour=lambda: 12.0)
        for i in range(5):
            mood = m.grabbed(i)
        self.assertEqual(mood, 'grumpy')

    def test_tired_eyes_and_slow_walk(self):
        night, day = Mind(hour=lambda: 0.5), Mind(hour=lambda: 11.0)
        self.assertLess(night.eyelids(), day.eyelids())
        self.assertLess(night.walk_factor(), day.walk_factor())
        self.assertIn('sleepy', night.feeling())


class FakeRobot:
    """Just enough of a Companion for Initiative.choose()."""

    def __init__(self, **settings):
        self.settings = Settings(**settings)
        self.mind = Mind(hour=lambda: 12.0)
        self.mind.user_here = True
        busy = type('B', (), {'active': False, 'busy': False, 'is_inhibited': lambda s: False})
        self.conversation = busy()
        self.bubbles = busy()
        self.evil = busy()
        self.busy_working = False
        self.body = type('Body', (), {'state': 'idle', 'held': False})()
        self.wardrobe = type('W', (), {'changing': lambda s, now: False})()


class InitiativeTest(unittest.TestCase):
    def make(self, hour=12):
        return Initiative(random.Random(1), now_dt=lambda: datetime(2026, 3, 3, hour, 0))

    def test_first_meeting_then_welcome_back(self):
        ini, robot, m = self.make(hour=14), FakeRobot(), Memory()
        ini.on_idle(1, 0, m)
        self.assertEqual(ini.choose(robot, 0)[0], 'first_meeting')
        ini.on_idle(1500, 100, m)                         # gone for 25 minutes...
        ini.on_idle(1, 1600, m)                           # ...and back
        kind, info = ini.choose(robot, 1600)
        self.assertEqual((kind, info['minutes']), ('welcome_back', 25))

    def test_good_morning(self):
        ini, robot, m = self.make(hour=8), FakeRobot(), Memory()
        m.first_met, m.last_seen = '2026-03-01', '2026-03-02'   # met before, not today
        ini.on_idle(1, 0, m)
        self.assertEqual(ini.choose(robot, 0)[0], 'morning')

    def test_break_reminder_after_a_long_stretch(self):
        ini, robot, m = self.make(), FakeRobot(break_after=45 * 60), Memory()
        m.first_met = m.last_seen = date.today().isoformat()
        ini.on_idle(1, 0, m)
        self.assertIsNone(ini.choose(robot, 60))
        t = 0
        while t < 46 * 60:                                # you keep working
            t += 30
            ini.on_idle(2, t, m)
        self.assertEqual(ini.choose(robot, t)[0], 'break')
        self.assertNotEqual((ini.choose(robot, t + 3600) or ('',))[0], 'break')  # once

    def test_polite(self):
        m = Memory()
        for settings, setup in (({'chattiness': 'off'}, None),
                                ({'quiet_hours': '9-17'}, None),
                                ({}, lambda r: setattr(r.conversation, 'active', True)),
                                ({}, lambda r: setattr(r.evil, 'is_inhibited', lambda: True))):
            ini, robot = self.make(hour=12), FakeRobot(**settings)
            if setup:
                setup(robot)
            ini.on_idle(1, 0, m)
            self.assertIsNone(ini.choose(robot, 0), settings)

    def test_quiet_hours(self):
        self.assertTrue(in_quiet_hours('22-8', 23))
        self.assertTrue(in_quiet_hours('22-8', 3))
        self.assertFalse(in_quiet_hours('22-8', 12))
        self.assertFalse(in_quiet_hours('off', 3))

    def test_lines_use_your_name(self):
        self.assertEqual(fill('Good morning{, name}!', 'Erik'), 'Good morning, Erik!')
        self.assertEqual(fill('Good morning{, name}!', ''), 'Good morning!')
        p = REGISTRY.personality('robo', 'pirate')
        self.assertIn('Ahoy', line_for('morning', p, 'Erik', random.Random(1)))
        self.assertTrue(line_for('question', p, '', random.Random(1)))   # falls back to Robo's


class SpeakingUpTest(unittest.TestCase):
    def test_he_greets_you_and_listens(self):
        robot, p = make_robot()
        robot.speak_up('first_meeting')
        self.assertTrue(robot.conversation.active)
        self.assertIn('Robo', p.voice.said[-1])
        for _ in range(100):
            p.scheduler.advance(0.1)
            if p.ears.listening:
                break
        p.ears.stay_silent()                                # you don't answer...
        p.scheduler.advance(2)
        self.assertFalse(robot.conversation.active)         # ...and that's fine:
        self.assertEqual(len(p.voice.said), 1)              # no "goodbye" after it

    def test_announcements_dont_listen(self):
        robot, p = make_robot()
        robot.speak_up('break', {'minutes': 95})
        self.assertIn('95', ' '.join(p.voice.said) + robot.conversation.reply.text)

    def test_voice_off_means_body_language_only(self):
        robot, p = make_robot(voice=False)
        robot.speak_up('welcome_back', {'minutes': 20})
        self.assertEqual(p.voice.said, [])
        self.assertTrue(robot.face.active(F.WAVE, p.clock()))

    def test_on_his_own_through_the_day(self):
        robot, p = make_robot(chattiness='often')
        p.idle.feed(1)
        p.scheduler.advance(3)
        self.assertTrue(p.voice.said)                       # said hello on his own


class TalkTest(unittest.TestCase):
    def ctx(self, **kw):
        return Context(**kw)

    def test_rule_brain_remembers(self):
        b = RuleBrain(random.Random(1))
        r = b.respond('my name is erik', self.ctx())
        self.assertEqual(r.user_name, 'Erik')
        self.assertIn('Erik', b.greeting(self.ctx(user_name='Erik')).text)
        self.assertIn('Erik', b.respond("what's my name", self.ctx(user_name='Erik')).text)
        r = b.respond('remember that i have a cat called mo', self.ctx())
        self.assertEqual(r.remember, ('they have a cat called mo',))
        self.assertEqual(b.respond('forget everything', self.ctx()).action, 'forget')
        self.assertIn('pizza', b.respond('what do you remember about me',
                                         self.ctx(memory_text='I remember pizza')).text)

    def test_honest_about_feelings(self):
        b = RuleBrain(random.Random(1))
        self.assertEqual(b.respond('how are you', self.ctx(feeling='very sleepy')).mood, 'sleep')
        self.assertEqual(b.respond('you are so cute', self.ctx()).feeling, 'praised')
        self.assertEqual(b.respond('you are stupid', self.ctx()).feeling, 'hurt')

    def test_claude_can_remember_things(self):
        r = parse_reply(json.dumps({'say': 'Cool!', 'remember': ['likes jazz'], 'name': 'Erik',
                                    'feeling': 'praised'}), self.ctx())
        self.assertEqual((r.remember, r.user_name, r.feeling), (('likes jazz',), 'Erik', 'praised'))
        off = parse_reply(json.dumps({'say': 'x', 'remember': ['y']}), self.ctx(remembers=False))
        self.assertEqual(off.remember, ())

    def test_what_he_learns_ends_up_in_memory(self):
        robot, p = make_robot()
        robot.talk()
        for _ in range(100):
            if p.ears.listening:
                break
            p.scheduler.advance(0.1)
        p.ears.hear('my name is erik')
        self.assertEqual(robot.memory.name, 'Erik')
        ctx = robot.conversation.context()
        self.assertEqual(ctx.user_name, 'Erik')
        self.assertIn('curious', ctx.personality)          # who he is, for the AI brain


class BodyTest(unittest.TestCase):
    def test_eyes_follow_the_pointer(self):
        robot, p = make_robot()
        p.scheduler.advance(0.5)
        x, y = p.window.pos
        p.window.pointer = (x - 600, y)                     # far left, up high
        p.scheduler.advance(0.5)
        pose = build_pose(robot, p.clock())
        self.assertLess(pose.look * robot.body.facing, -1)
        self.assertLess(pose.look_y, -1)

    def test_pastimes(self):
        robot, p = make_robot()
        robot.rng.random = lambda: 0.0                      # always in the mood
        self.assertTrue(personality.maybe_pastime(robot, p.clock(), bored=True))
        pose = build_pose(robot, p.clock())
        self.assertEqual(pose.hobby, robot.face.hobby)
        self.assertEqual(pose.arms, robot.hobbies()[pose.hobby].gesture)

    def test_picked_up_reaction(self):
        robot, p = make_robot()
        robot.mind.happiness = 0.95
        x, y = p.window.pos
        robot.pointer_press(PointerEvent(1, 85, 200, x + 85, y + 200))
        robot.pointer_motion(PointerEvent(1, 85, 200, x + 85, y + 120))
        self.assertEqual(build_pose(robot, p.clock()).mood, 'happy')       # wheee
        robot.pointer_release(PointerEvent(1, 85, 200, x + 85, y + 120))
        robot.mind.energy = 0.1                                            # now sleepy
        for _ in range(2):
            robot.pointer_press(PointerEvent(1, 85, 200, x + 85, y + 200))
            robot.pointer_motion(PointerEvent(1, 85, 200, x + 85, y + 120))
        self.assertEqual(build_pose(robot, p.clock()).mood, 'sad')         # put me down!

    def test_yawns_and_droopy_eyes_when_tired(self):
        robot, p = make_robot()
        robot.mind.energy = 0.2
        pose = build_pose(robot, p.clock())
        self.assertLess(pose.openness, 1.0)
        robot.face.show(F.YAWN, p.clock(), 2)
        pose = build_pose(robot, p.clock())
        self.assertEqual((pose.mood, pose.arms), ('yawn', 'stretch'))


class SettingsTest(unittest.TestCase):
    def test_new_settings(self):
        s = Settings.from_dict({'chattiness': 'often', 'quiet_hours': '22-8',
                                'remember_me': False})
        self.assertEqual((s.chattiness, s.quiet_hours, s.remember_me), ('often', '22-8', False))
        self.assertEqual(Settings(chattiness='nonstop').chattiness, 'sometimes')

    def test_every_character_has_a_personality(self):
        for cid in REGISTRY.looks():
            p = REGISTRY.personality(cid if cid == 'robo' else 'robo', '' if cid == 'robo' else cid)
            self.assertTrue(p.get('traits') and p.get('speech'), cid)
            self.assertTrue(p['lines'].get('morning'), cid)


if __name__ == '__main__':
    unittest.main()
