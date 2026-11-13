"""Robo picks his own outfits and learns what he likes (robo.core.outfits)."""
import os
import random
import sys
import tempfile
import unittest
from collections import Counter
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from robo.app import build_companion  # noqa: E402
from robo.config import Settings  # noqa: E402
from robo.conversation import Context, RuleBrain  # noqa: E402
from robo.core import characters, outfits  # noqa: E402
from robo.core.outfits import Taste, calendar_situations, choose, innate_taste  # noqa: E402
from robo.design.model import WEAR_SITUATIONS, Character  # noqa: E402
from robo.events import Event  # noqa: E402
from robo.platform.base import PointerEvent  # noqa: E402
from robo.platform.headless import HeadlessPlatform  # noqa: E402


def make_robot(**settings):
    settings.setdefault('dress_up_every', 0)
    settings.setdefault('evil_after', 0)
    settings.setdefault('chattiness', 'off')
    p = HeadlessPlatform()
    robot = build_companion(Settings(**settings), p)
    robot.rng.seed(3)
    return robot, p


class SituationsTest(unittest.TestCase):
    def test_every_situation_has_words_and_is_allowed_in_files(self):
        self.assertEqual(set(outfits.SITUATIONS), set(WEAR_SITUATIONS))

    def test_built_in_outfits_say_when_they_fit(self):
        for cid in characters.costume_ids():
            self.assertTrue(characters.get(cid).wear, f'{cid} has no wear: list')

    def test_calendar(self):
        night = calendar_situations(datetime(2026, 10, 31, 23, 30))   # Saturday
        self.assertTrue({'night', 'weekend', 'autumn', 'halloween'} <= night)
        lunch = calendar_situations(datetime(2026, 12, 21, 12, 0))    # Monday
        self.assertTrue({'lunch', 'monday', 'winter', 'christmas'} <= lunch)
        self.assertIn('night', calendar_situations(datetime(2026, 6, 3, 2, 0)))
        self.assertNotIn('morning', calendar_situations(datetime(2026, 6, 3, 2, 0)))

    def test_what_you_are_doing_counts(self):
        robot, p = make_robot()
        robot.handle_event(Event('music'))
        self.assertIn('music', outfits.situations(robot, robot.clock()))
        p.scheduler.advance(outfits.RECENT_SECONDS + 1)
        self.assertNotIn('music', outfits.situations(robot, robot.clock()))


class ChooseTest(unittest.TestCase):
    def setUp(self):
        self.taste = Taste()
        self.taste.scores = {'a': 0.0, 'b': 0.0, 'c': 0.0}
        self.chars = [Character('a', wear=('night',)), Character('b', wear=('lunch',)),
                      Character('c')]

    def picks(self, tags, n=600, **kw):
        rng = random.Random(4)
        return Counter(choose(self.chars, tags, self.taste, rng, **kw).id for _ in range(n))

    def test_prefers_what_suits_the_moment(self):
        night = self.picks({'night'})
        self.assertGreater(night['a'], night['b'] * 2)
        self.assertGreater(night['a'], night['c'] * 2)
        self.assertGreater(night['b'], 0)                  # ...but can still surprise you

    def test_prefers_favourites(self):
        self.taste.scores['c'] = 1.0
        picks = self.picks(set())
        self.assertGreater(picks['c'], picks['a'] * 3)

    def test_says_why(self):
        rng = random.Random(1)
        only = [Character('a', wear=('night',))]
        c = choose(only, {'night'}, self.taste, rng)
        self.assertEqual((c.id, c.why, c.because), ('a', 'situation', "it's the middle of the night"))
        self.taste.scores['c'] = 0.9
        c = choose([Character('c')], set(), self.taste, rng)
        self.assertEqual(c.why, 'favourite')
        self.assertEqual(choose([Character('b')], set(), self.taste, rng).because, '')

    def test_exclude_is_strict_and_avoid_is_not(self):
        self.assertNotIn('a', self.picks({'night'}, exclude=('a',)))
        self.assertNotIn('a', self.picks({'night'}, avoid=('a',)))
        only_a = choose([Character('a'), Character('b')], set(), self.taste, random.Random(),
                        exclude=('b',), avoid=('a',))
        self.assertEqual(only_a.id, 'a')                   # nothing else left: wear it again
        self.assertIsNone(choose([Character('b')], set(), self.taste, random.Random(),
                                 exclude=('b',)))


class TasteTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, 'outfits.json')

    def tearDown(self):
        self.dir.cleanup()

    def test_starts_with_a_stable_built_in_taste(self):
        self.assertEqual(innate_taste('pirate'), innate_taste('pirate'))
        self.assertLessEqual(abs(innate_taste('pirate')), outfits.INNATE)
        self.assertEqual(len({round(innate_taste(c), 3) for c in characters.costume_ids()}),
                         len(characters.costume_ids()))

    def test_learns_and_remembers(self):
        t = Taste(self.path)
        start = t.of('pirate')
        t.took_off('pirate', 5, clicked=True)              # you clicked him out of it right away
        self.assertLess(t.of('pirate'), start)
        t.took_off('wizard', 600, clicked=True)            # wore it for ages: fine
        self.assertGreater(t.of('wizard'), innate_taste('wizard'))
        t.wore('pirate')
        again = Taste(self.path)
        self.assertAlmostEqual(again.of('pirate'), t.of('pirate'), places=3)
        self.assertEqual(again.worn['pirate'], 1)

    def test_stays_in_range(self):
        t = Taste()
        for _ in range(20):
            t.nudge('x', 0.5)
        self.assertEqual(t.of('x'), 1.0)
        self.assertEqual(t.favourites(['x', 'y']), ['x'])


class RobotPicksTest(unittest.TestCase):
    def test_dresses_up_on_his_own_with_a_choice(self):
        robot, p = make_robot(dress_up_every=30)
        p.scheduler.advance(120)
        self.assertIsNotNone(robot.wardrobe.current)
        self.assertIsNotNone(robot.wardrobe.choice)
        self.assertEqual(robot.wardrobe.choice.id, robot.wardrobe.current.id)
        self.assertEqual(robot.taste.worn.get(robot.wardrobe.current.id), 1)

    def test_tells_you_why_when_chatty(self):
        robot, p = make_robot(chattiness='often')
        said = []
        robot.speak_up = lambda kind, info=None: said.append((kind, info))
        robot.rng.random = lambda: 0.0                     # always in the mood to say it
        robot.taste.scores = {c: 1.0 for c in characters.costume_ids()}
        robot.dress_up()
        p.scheduler.advance(2)
        self.assertEqual(said[0][0], 'dressed_up')
        self.assertEqual(said[0][1]['outfit'], robot.wardrobe.current.title.lower())
        self.assertTrue(said[0][1]['because'])

    def test_never_his_everyday_look(self):
        robot, p = make_robot(look='pirate')
        for _ in range(10):
            robot.wardrobe.current = None
            robot.dress_up()
            p.scheduler.advance(1)
            self.assertNotEqual(robot.wardrobe.current.id, 'pirate')

    def test_clicking_him_out_of_it_right_away_teaches_him(self):
        robot, p = make_robot()
        robot.dress_up('wizard')
        p.scheduler.advance(2)
        liked = robot.taste.of('wizard')
        robot.pointer_press(PointerEvent(1, 85, 200, 0, 0))
        robot.pointer_release(PointerEvent(1, 85, 200, 0, 0))
        p.scheduler.advance(1)
        self.assertIsNone(robot.wardrobe.current)
        self.assertLess(robot.taste.of('wizard'), liked)

    def test_asking_for_an_outfit_makes_him_like_it(self):
        robot, p = make_robot()
        before = robot.taste.of('viking')
        robot.dress_up('viking')
        self.assertGreater(robot.taste.of('viking'), before)


class ConversationTest(unittest.TestCase):
    def test_you_can_let_him_choose(self):
        brain = RuleBrain(random.Random(1))
        ctx = Context(characters=('pirate', 'wizard'), outfit_choice='wizard',
                      outfit_because="it's evening")
        r = brain.respond('wear whatever you like', ctx)
        self.assertEqual((r.action, r.action_arg), ('dress_up', 'wizard'))
        self.assertIn('evening', r.text)
        r = brain.respond('dress up as a pirate', ctx)     # naming one still wins
        self.assertEqual(r.action_arg, 'pirate')

    def test_the_ai_brain_hears_what_he_would_pick(self):
        from robo.conversation.agent import _status_line
        line = _status_line(Context(outfit_choice='astronaut', outfit_because="it's night",
                                    favourite_outfits=('astronaut', 'chef')))
        self.assertIn('would wear: astronaut', line)
        self.assertIn('favourite outfits: astronaut, chef', line)


if __name__ == '__main__':
    unittest.main()
