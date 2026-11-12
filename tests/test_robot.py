"""Run with:  python3 -m unittest discover -s tests"""
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from robo.app import build_companion  # noqa: E402
from robo.config import Settings  # noqa: E402
from robo.core.bubble import BUBBLE_KINDS, BubbleQueue  # noqa: E402
from robo.core.characters import CHARACTERS  # noqa: E402
from robo.platform.base import PointerEvent  # noqa: E402
from robo.render.costumes import OUTFITS  # noqa: E402
from robo.events import KINDS, Event, classify  # noqa: E402
from robo.platform.headless import HeadlessPlatform  # noqa: E402
from robo.render.icons import ICONS  # noqa: E402


def make_robot(**settings):
    platform = HeadlessPlatform()
    robot = build_companion(Settings(**settings), platform)
    robot.rng.seed(1)
    return robot, platform


class ClassifyTest(unittest.TestCase):
    def test_keywords(self):
        self.assertEqual(classify('notify-send', 'Battery low', '9% left'), 'battery_low')
        self.assertEqual(classify('Telegram', 'Anna', 'sent you a message'), 'chat')
        self.assertEqual(classify('nm', 'Wi-Fi', 'Disconnected'), 'wifi_off')
        self.assertEqual(classify('Software Updater', 'Updated software is available', ''), 'update')

    def test_category_beats_keywords(self):
        self.assertEqual(classify('x', 'network', '', category='email.arrived'), 'mail')

    def test_fallbacks(self):
        self.assertEqual(classify('x', 'hello', ''), 'bell')
        self.assertEqual(classify('x', 'hello', '', urgent=True), 'warning')

    def test_every_kind_has_an_icon(self):
        self.assertEqual(set(BUBBLE_KINDS), set(ICONS))
        self.assertTrue(set(KINDS) <= set(ICONS))


class BubbleQueueTest(unittest.TestCase):
    def test_duplicates_bump_the_counter(self):
        q = BubbleQueue()
        self.assertEqual(q.push('chat', 0), 'queued')
        q.update(0)
        self.assertEqual(q.push('chat', 1), 'bumped')
        self.assertEqual(q.current.count, 2)

    def test_system_kinds_are_deduplicated(self):
        q = BubbleQueue()
        q.push('battery_low', 0)
        self.assertEqual(q.push('battery_low', 10), 'ignored')
        self.assertEqual(q.push('battery_low', 100), 'merged')

    def test_bubble_closes_and_next_one_shows(self):
        q = BubbleQueue()
        q.push('mail', 0, duration=1)
        q.push('chat', 0, duration=1)
        self.assertEqual(q.update(0).kind, 'mail')
        q.update(1.1)           # starts closing
        q.update(1.5)           # closed
        self.assertIsNone(q.current)
        self.assertEqual(q.update(2.0).kind, 'chat')


class CompanionTest(unittest.TestCase):
    def test_walks_around(self):
        robot, p = make_robot()
        positions = set()
        for _ in range(60):
            p.scheduler.advance(1)
            positions.add(p.window.pos[0])
        self.assertGreater(len(positions), 5)
        b = robot.bounds
        self.assertTrue(all(b.min_x - robot.width <= x <= b.max_x for x in positions))

    def test_event_shows_bubble_and_click_region(self):
        robot, p = make_robot()
        robot.handle_event(Event('mail'))
        p.scheduler.advance(0.5)
        self.assertEqual(robot.bubbles.current.kind, 'mail')
        self.assertEqual(len(p.window.regions), 2)      # robot + bubble
        p.scheduler.advance(7)
        self.assertIsNone(robot.bubbles.current)
        self.assertEqual(len(p.window.regions), 1)

    def test_evil_mode_round_trip(self):
        robot, p = make_robot(evil_after=5)
        p.idle.feed(6)
        p.scheduler.advance(2)
        self.assertTrue(robot.evil.active)
        self.assertEqual(robot.evil.blend, 1.0)
        p.idle.feed(0.2)
        p.scheduler.advance(1)
        self.assertFalse(robot.evil.active)
        self.assertEqual(robot.evil.blend, 0.0)

    def test_evil_mode_respects_inhibit(self):
        robot, p = make_robot(evil_after=5)
        p.idle.inhibited = True
        p.idle.feed(60)
        self.assertFalse(robot.evil.active)

    def test_demo_shows_every_icon(self):
        robot, p = make_robot(dress_up_every=0)       # no costume demands mixed in
        robot.demo()
        seen = set()
        for _ in range(int(len(KINDS) * 3.2 * 10)):
            p.scheduler.advance(0.1)
            if robot.bubbles.current:
                seen.add(robot.bubbles.current.kind)
        self.assertEqual(seen, set(KINDS))

    def test_drag_and_drop(self):
        from robo.platform.base import PointerEvent
        robot, p = make_robot()
        x, y = p.window.pos
        robot.pointer_press(PointerEvent(1, 85, 150, x + 85, y + 150))
        robot.pointer_motion(PointerEvent(0, 85, 150, x + 85, y - 200))
        self.assertEqual(robot.body.state, 'drag')
        robot.pointer_release(PointerEvent(1, 85, 150, x + 85, y - 200))
        self.assertEqual(robot.body.state, 'fall')
        p.scheduler.advance(2)
        self.assertEqual(p.window.pos[1], robot.bounds.ground_y)

    def test_right_click_menu(self):
        from robo.platform.base import PointerEvent
        robot, p = make_robot()
        robot.pointer_press(PointerEvent(3, 85, 150, 0, 0))
        labels = [i.label for i in p.window.menus[-1]]
        self.assertIn('Quit', labels)

    def test_renders_every_pose_without_errors(self):
        robot, p = make_robot(evil_after=5)
        robot.demo()
        for step in range(200):
            if step == 50:
                p.idle.feed(6)
            if step == 150:
                p.idle.feed(0.1)
            p.scheduler.advance(0.1)     # each tick redraws the off-screen window



def click_robot(robot, p):
    x, y = p.window.pos
    robot.pointer_press(PointerEvent(1, 85, 200, x + 85, y + 200))
    robot.pointer_release(PointerEvent(1, 85, 200, x + 85, y + 200))


class CostumeTest(unittest.TestCase):
    def test_every_character_has_an_outfit(self):
        self.assertEqual(set(CHARACTERS), set(OUTFITS))

    def test_dresses_up_on_his_own_and_makes_a_demand(self):
        robot, p = make_robot(dress_up_every=10, evil_after=0)
        seen = set()
        for _ in range(150):                 # 30 s; he dresses up after 6-14 s
            p.scheduler.advance(0.2)
            if robot.bubbles.current:
                seen.add(robot.bubbles.current.kind)
        c = robot.wardrobe.current
        self.assertIsNotNone(c)
        self.assertIn(c.demand, seen)

    def test_click_takes_the_costume_off(self):
        robot, p = make_robot(dress_up_every=0)
        robot.dress_up('pharaoh')
        p.scheduler.advance(1)
        self.assertEqual(robot.wardrobe.current.id, 'pharaoh')
        click_robot(robot, p)
        p.scheduler.advance(1)
        self.assertIsNone(robot.wardrobe.current)
        self.assertFalse(any(b.kind == 'pyramid' for b in robot.bubbles.pending))

    def test_clicking_the_bubble_keeps_the_costume(self):
        robot, p = make_robot(dress_up_every=0)
        robot.dress_up('viking')
        p.scheduler.advance(1)
        x, y = p.window.pos
        robot.pointer_press(PointerEvent(1, 85, 40, x + 85, y + 40))
        robot.pointer_release(PointerEvent(1, 85, 40, x + 85, y + 40))
        p.scheduler.advance(1)
        self.assertEqual(robot.wardrobe.current.id, 'viking')

    def test_no_dressing_up_while_evil(self):
        robot, p = make_robot(dress_up_every=5, evil_after=5)
        p.idle.feed(6)
        p.scheduler.advance(30)
        self.assertIsNone(robot.wardrobe.current)

    def test_every_signature_move_renders_and_particles_fly(self):
        robot, p = make_robot(dress_up_every=0)
        for cid, character in CHARACTERS.items():
            robot.wardrobe.current = None
            robot.dress_up(cid)
            p.scheduler.advance(1)
            robot.wardrobe.start_move(p.clock())
            p.scheduler.advance(1)           # every tick renders the frame off-screen
            if character.particles:
                self.assertTrue(robot.effects.particles, cid)

    def test_menu_offers_dress_up(self):
        robot, p = make_robot()
        robot.pointer_press(PointerEvent(3, 85, 200, 0, 0))
        labels = [i.label for i in p.window.menus[-1]]
        self.assertTrue(any('Dress up' in l for l in labels))


if __name__ == '__main__':
    random.seed(0)
    unittest.main()


class SettingsTest(unittest.TestCase):
    def setUp(self):
        import tempfile
        from robo.settings_store import SettingsStore
        self.tmp = tempfile.TemporaryDirectory()
        self.store = SettingsStore(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def make_app(self, settings=None):
        from robo.app import RoboApp
        p = HeadlessPlatform(config_dir=self.tmp.name)
        app = RoboApp(settings or Settings(dress_up_every=0), p, self.store)
        return app, p

    def test_round_trip_through_the_file(self):
        s = Settings(scale=1.7, evil_mode=False, characters=('viking', 'roman'))
        self.store.save(s)
        self.assertEqual(self.store.load(), s)

    def test_messy_file_falls_back_gracefully(self):
        import json
        import os
        with open(os.path.join(self.tmp.name, 'settings.json'), 'w') as f:
            f.write('{"scale": "huge", "walk_speed": 99, "nonsense": 1, '
                    '"characters": ["roman", "elvis"], '
                    '"known_characters": %s}' % json.dumps(list(CHARACTERS)))
        s = self.store.load()
        self.assertEqual(s.scale, 1.0)               # bad value ignored
        self.assertEqual(s.walk_speed, 3.0)          # clamped
        self.assertEqual(s.characters, ('roman',))   # unknown character dropped

    def test_zero_means_off_like_the_command_line(self):
        s = Settings(evil_after=0, dress_up_every=0)
        self.assertFalse(s.evil_mode)
        self.assertFalse(s.dress_up)

    def test_command_line_overrides_only_given_flags(self):
        from robo.app import parse_args
        overrides, _ = parse_args(['--scale', '2', '--evil-after', '0'])
        self.assertEqual(overrides, {'scale': 2.0, 'evil_after': 0.0, 'evil_mode': False})

    def test_menu_opens_settings_and_apply_updates_the_robot_live(self):
        app, p = self.make_app()
        robot = app.robot
        robot.pointer_press(PointerEvent(3, 85, 200, 0, 0))
        item = next(i for i in p.window.menus[-1] if i.label and 'Settings' in i.label)
        item.action()
        current, on_apply = p.settings_opened[-1]
        on_apply(current.with_changes(scale=2.0, walk_speed=2.5, dress_up=True,
                                      dress_up_every=15, characters=('cowboy',)))
        p.scheduler.advance(0.1)
        self.assertEqual((p.window.width, p.window.height), (robot.width, robot.height))
        self.assertEqual(robot.width, round(170 * 2.0))
        self.assertEqual(self.store.load().scale, 2.0)            # saved
        p.scheduler.advance(40)                                    # dresses up, only as cowboy
        self.assertEqual(robot.wardrobe.current.id, 'cowboy')

    def test_switching_evil_mode_off_turns_him_good_immediately(self):
        app, p = self.make_app(Settings(evil_after=5, dress_up_every=0))
        p.idle.feed(6)
        p.scheduler.advance(1)
        self.assertTrue(app.robot.evil.active)
        app.apply(app.settings.with_changes(evil_mode=False))
        self.assertFalse(app.robot.evil.active)
        p.idle.feed(600)
        self.assertFalse(app.robot.evil.active)

    def test_hand_edited_file_is_hot_reloaded(self):
        import json, os, time as _t
        app, p = self.make_app()
        path = os.path.join(self.tmp.name, 'settings.json')
        _t.sleep(0.01)
        with open(path, 'w') as f:
            json.dump({'scale': 1.5, 'naps': False}, f)
        p.scheduler.advance(3)                                     # file is checked every 2 s
        self.assertEqual(app.robot.scale, 1.5)
        self.assertFalse(app.settings.naps)


class NewCharacterMigrationTest(unittest.TestCase):
    def test_old_settings_file_gets_new_characters_switched_on(self):
        old_file = {'characters': ['pharaoh', 'viking']}      # saved before the new ones existed
        s = Settings.from_dict(old_file)
        self.assertIn('viking', s.characters)
        self.assertNotIn('cowboy', s.characters)               # still off, as the user chose
        for new in ('chef', 'astronaut', 'wizard', 'pirate', 'superhero', 'kitty'):
            self.assertIn(new, s.characters)

    def test_characters_switched_off_later_stay_off(self):
        s = Settings(characters=('chef',))
        again = Settings.from_dict(s.to_dict())
        self.assertEqual(again.characters, ('chef',))
