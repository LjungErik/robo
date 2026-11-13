"""Character files: the interpreter, user characters, and getting around the screen.

Run with:  python3 -m unittest discover -s tests
"""
import os
import random
import sys
import tempfile
import textwrap
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import cairo  # noqa: E402

from robo.app import build_companion  # noqa: E402
from robo.config import Settings  # noqa: E402
from robo.conversation import RuleBrain  # noqa: E402
from robo.core import characters  # noqa: E402
from robo.core.pose import Pose, build_pose  # noqa: E402
from robo.design import REGISTRY, ExprError, LoadError, compile_expr  # noqa: E402
from robo.design.loader import load_file  # noqa: E402
from robo.platform.headless import HeadlessPlatform  # noqa: E402
from robo.render.robot import draw_robot  # noqa: E402


def make_robot(**settings):
    platform = HeadlessPlatform()
    settings.setdefault('dress_up_every', 0)
    settings.setdefault('evil_after', 0)
    robot = build_companion(Settings(**settings), platform)
    robot.rng.seed(1)
    return robot, platform


def render(pose):
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 200, 220)
    cr = cairo.Context(surf)
    cr.translate(100, 200)
    draw_robot(cr, pose)
    return bytes(surf.get_data())


class UserCharacters:
    """Temporarily add a folder of character files to the registry."""

    def __init__(self, files):
        self.tmp = tempfile.TemporaryDirectory()
        for name, text in files.items():
            with open(os.path.join(self.tmp.name, name), 'w') as f:
                f.write(textwrap.dedent(text))

    def __enter__(self):
        REGISTRY.add_directory(self.tmp.name)
        REGISTRY.reload()
        return self.tmp.name

    def __exit__(self, *exc):
        REGISTRY.directories.remove(self.tmp.name)
        REGISTRY.reload()
        self.tmp.cleanup()


DUCK = """
    name: Duck
    words: [duck, ducky]
    move: {gesture: flap, mood: happy, seconds: 2}
    gestures:
      flap: {back: "1.4 + sin(t * 20) * 0.4", front: "-1.4 - sin(t * 20) * 0.4"}
    palette:
      beak: "#FFA94D"
    recolor:
      body: "#FFE066"
    layers:
      face:
        - {ellipse: [0, -76, 9, 4], fill: beak}
    demand:
      icon: bread
      color: orange
      draw:
        - {rect: [8, 14, 32, 24], r: 8, fill: "#E0A050"}
"""


class ExpressionTest(unittest.TestCase):
    def test_maths_and_variables(self):
        self.assertAlmostEqual(compile_expr('sin(t) * 2 + 1')({'t': 0}), 1.0)
        self.assertEqual(compile_expr("1 if arms in ('fly', 'up') else 0")({'arms': 'up'}), 1)
        self.assertEqual(compile_expr('pick(4, 10, 20, 30)')({}), 20)
        self.assertEqual(compile_expr(3)({}), 3.0)

    def test_files_cannot_run_code(self):
        for bad in ('__import__("os").system("ls")', 'x.__class__', 'x[0]', 'open("f")',
                    '(lambda: 1)()', '[c for c in "ab"]', 'exec("1")', '2 ** 10'):
            with self.assertRaises(ExprError, msg=bad):
                compile_expr(bad)({'x': 1})

    def test_no_giant_strings(self):
        with self.assertRaises(ExprError):
            compile_expr('mood * 100000000')({'mood': 'happy'})


class LoaderTest(unittest.TestCase):
    def load(self, text, name='thing.yaml'):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, name)
            with open(path, 'w') as f:
                f.write(textwrap.dedent(text))
            return load_file(path)

    def test_mistakes_are_reported_with_the_file_name(self):
        cases = {
            'colour: red\n': 'unknown key',
            'layers: {hat: [{circle: [0, 0, 1]}]}\n': 'unknown layer',
            'layers: {head: [{blob: [0, 0, 1]}]}\n': 'exactly one of',
            'layers: {head: [{circle: [0, 0]}]}\n': 'list of 3',
            'layers: {head: [{path: "M 0 0 Q 1 1"}]}\n': 'path command',
            'layers: {head: [{circle: [0, 0, "t.x"]}]}\n': 'Attribute',
            'layers: {head: [{circle: [0, 0, 1], fill: "#12"}]}\n': 'bad colour',
            'role: base\n': 'must draw every part',
            'travel: [{kind: dig}]\n': 'kind must be',
        }
        for text, expected in cases.items():
            with self.assertRaises(LoadError, msg=text) as e:
                self.load(text)
            self.assertIn('thing.yaml', str(e.exception))
            self.assertIn(expected, str(e.exception), text)

    def test_json_works_too(self):
        cf = self.load('{"name": "Jason", "layers": {"head": [{"circle": [0, -120, 5]}]}}',
                       'jason.json')
        self.assertEqual((cf.id, cf.character.title), ('jason', 'Jason'))

    def test_every_built_in_file_loads(self):
        self.assertEqual(REGISTRY.errors, {})
        for cid in ('robo', 'hacker', 'ironman', 'spiderman', 'thanos'):
            self.assertIsNotNone(REGISTRY.get(cid), cid)
        self.assertIn('ironman', characters.costume_ids())
        self.assertNotIn('hacker', characters.costume_ids())     # work outfit, never random
        self.assertNotIn('robo', characters.costume_ids())


class UserCharacterTest(unittest.TestCase):
    def test_a_new_file_is_a_new_character(self):
        with UserCharacters({'duck.yaml': DUCK}):
            self.assertIn('duck', characters.costume_ids())
            robot, p = make_robot()
            robot.dress_up('duck')
            p.scheduler.advance(1)
            self.assertEqual(robot.wardrobe.current.id, 'duck')
            self.assertEqual(robot.bubbles.current.kind, 'bread')     # its own demand icon
            robot.wardrobe.start_move(p.clock())
            pose = build_pose(robot, p.clock())
            self.assertEqual(pose.arms, 'flap')
            self.assertNotEqual(render(pose), render(Pose(t=pose.t, arms='flap')))
            reply = RuleBrain(random.Random(1)).respond('dress up as a duck',
                                                       robot.conversation.context())
            self.assertEqual(reply.action, 'dance')          # "I am already the duck!"
            plain, _ = make_robot()
            reply = RuleBrain(random.Random(1)).respond('be a ducky', plain.conversation.context())
            self.assertEqual(reply.action_arg, 'duck')
        self.assertNotIn('duck', characters.costume_ids())

    def test_same_id_replaces_the_built_in_one(self):
        plain = render(Pose(t=0.3))
        with open(REGISTRY.file('robo').character.source) as f:
            robo = f.read()
        green = robo.replace('body:   {good: "#F4F7FB"', 'body:   {good: "#40C040"')
        self.assertNotEqual(green, robo)
        with UserCharacters({'robo.yaml': green}):
            self.assertNotEqual(render(Pose(t=0.3)), plain)
        self.assertEqual(render(Pose(t=0.3)), plain)

    def test_a_broken_drawing_never_crashes_him(self):
        broken = DUCK.replace('[0, -76, 9, 4]', '[0, -76, nine, 4]')
        with UserCharacters({'duck.yaml': broken}):
            with self.assertLogs(level='WARNING') as logs:
                render(Pose(t=0.3, costume='duck'))
            self.assertTrue(any('nine' in m for m in logs.output))

    def test_a_broken_file_is_skipped(self):
        with UserCharacters({'oops.yaml': 'name: [unclosed\n', 'duck.yaml': DUCK}):
            self.assertIn('duck', characters.costume_ids())
            self.assertTrue(any('oops.yaml' in e for e in REGISTRY.errors.values()))

    def test_edits_are_picked_up_while_running(self):
        with UserCharacters({'duck.yaml': DUCK}) as d:
            self.assertFalse(REGISTRY.reload_if_changed())
            path = os.path.join(d, 'duck.yaml')
            with open(path, 'a') as f:
                f.write('walk: {speed: 3}\n')
            os.utime(path, ns=(1, 10 ** 18))
            self.assertTrue(REGISTRY.reload_if_changed())
            self.assertEqual(characters.get('duck').walk_speed, 3.0)


class LookTest(unittest.TestCase):
    def test_look_setting(self):
        self.assertEqual(Settings(look='thanos').look, 'thanos')
        self.assertEqual(Settings(look='nobody').look, 'robo')
        self.assertEqual(Settings.from_dict({'look': 'ironman'}).look, 'ironman')
        self.assertEqual(Settings(look='ironman').to_dict()['look'], 'ironman')

    def test_he_looks_like_his_look_and_never_dresses_up_as_it(self):
        robot, p = make_robot(look='spiderman')
        self.assertEqual(build_pose(robot, p.clock()).skin, 'spiderman')
        robot.wardrobe.allowed = ('spiderman', 'chef')
        for _ in range(5):
            robot.wardrobe.current = None
            robot.dress_up()
            p.scheduler.advance(1)
            self.assertEqual(robot.wardrobe.current.id, 'chef')

    def test_new_characters_are_switched_on_for_old_settings_files(self):
        s = Settings.from_dict({'characters': ['pharaoh'],
                                'known_characters': ['pharaoh', 'cowboy']})
        for cid in ('ironman', 'spiderman', 'thanos'):
            self.assertIn(cid, s.characters)
        self.assertNotIn('cowboy', s.characters)


def run(p, seconds, step=0.1, each=None):
    for _ in range(int(seconds / step)):
        p.scheduler.advance(step)
        if each:
            each()


class TravelTest(unittest.TestCase):
    def test_iron_man_flies_all_over_the_screen_and_lands(self):
        robot, p = make_robot(look='ironman')
        heights, flames = set(), []
        b = robot.bounds

        def watch():
            heights.add(round(robot.body.y))
            self.assertTrue(b.min_y <= robot.body.y <= b.ground_y)
            self.assertTrue(b.min_x <= robot.body.x <= b.max_x)
            if robot.body.airborne:
                pose = build_pose(robot, p.clock())
                flames.append(pose.airborne and not pose.shadow)
        run(p, 240, each=watch)
        span = b.ground_y - b.min_y
        self.assertLess(min(heights), b.ground_y - span * 0.3)    # really up there
        self.assertIn(round(b.ground_y), heights)                  # and back on the ground
        self.assertTrue(flames and all(flames))

    def web_trip(self, end):
        """Spider-Man shoots a web, zips up it, hangs, then comes down by `end`."""
        import dataclasses
        robot, p = make_robot(look='spiderman')
        run(p, 1)
        a = dataclasses.replace(robot.travel.abilities(robot)[0], end=end)
        start_y = robot.body.y
        robot.travel.start(robot, a, p.clock())
        seen = []

        def watch():
            pose = build_pose(robot, p.clock())
            seen.append((robot.body.state, pose.web, pose.web_hit, p.window.height,
                         p.window.pos[1]))
        run(p, 0.2, each=watch)
        self.assertEqual(robot.body.state, 'idle')            # 1. still on the ground, shooting
        self.assertTrue(0 < seen[-1][1] < 1)                  # the line is on its way up
        self.assertEqual(p.window.pos[1], robot.bounds.min_y)  # window: a column to the top
        self.assertGreater(p.window.height, 800)
        run(p, 3, each=watch)
        self.assertEqual(robot.body.state, 'hang')            # 3./4. zipped up, hanging
        self.assertTrue(any(s[2] >= 0 for s in seen))         # 2. the web stuck up there
        pose = build_pose(robot, p.clock())
        self.assertEqual(pose.web, 1.0)
        self.assertTrue(pose.dangling)
        self.assertAlmostEqual(-pose.anchor[1], a.rope + 53, delta=3)   # hanging on the rope
        self.assertLess(robot.body.y, start_y - 500)
        robot.travel.maybe_start = lambda *a: False           # (no second trip in this test)
        robot.travel.land(robot)                              # 5. come down
        run(p, 15)
        self.assertTrue(robot.body.on_ground)
        self.assertIsNone(robot.travel.web)                   # the web faded away
        self.assertEqual(p.window.height, robot.height)       # normal window again
        self.assertEqual(p.window.pos[1], round(robot.bounds.ground_y))
        return robot, p

    def test_spider_man_web_and_drop(self):
        self.web_trip('drop')

    def test_spider_man_lowers_himself_down_the_thread(self):
        self.web_trip('lower')

    def test_spider_man_on_his_own(self):
        robot, p = make_robot(look='spiderman')
        seen = set()
        run(p, 300, each=lambda: seen.add(robot.body.state))
        self.assertIn('hang', seen)

    def test_grabbing_him_cuts_the_web(self):
        from robo.platform.base import PointerEvent
        robot, p = make_robot(look='spiderman')
        robot.travel.start_kind(robot, 'hang', p.clock())
        run(p, 3)
        self.assertEqual(robot.body.state, 'hang')
        hx = robot.body.x
        hy = robot.body.y + 200 * robot.scale          # his belly, in screen pixels
        x, y = p.window.pos
        robot.pointer_press(PointerEvent(1, hx - x, hy - y, hx, hy))
        robot.pointer_motion(PointerEvent(1, hx - x, hy - y, hx + 30, hy + 40))
        self.assertIsNone(robot.travel.web)
        self.assertAlmostEqual(robot.body.y, hy + 40 - 200 * robot.scale, delta=2)
        robot.pointer_release(PointerEvent(1, 0, 0, hx + 30, hy + 40))
        run(p, 3)
        self.assertTrue(robot.body.on_ground)

    def test_thanos_snaps_and_teleports(self):
        robot, p = make_robot(look='thanos')
        jumps, poofs = [], []
        last = [robot.body.x]

        def watch():
            if abs(robot.body.x - last[0]) > 100:
                jumps.append(robot.body.x)
            last[0] = robot.body.x
            poofs.append(build_pose(robot, p.clock()).poof is not None)
        run(p, 240, each=watch)
        self.assertTrue(jumps)
        self.assertTrue(any(poofs))
        self.assertEqual(robot.body.y, robot.bounds.ground_y)

    def take_off(self, robot, p):
        robot.travel.start_kind(robot, 'fly', p.clock())
        run(p, 1)
        self.assertTrue(robot.body.airborne)

    def test_comes_down_when_he_cant_fly_any_more(self):
        robot, p = make_robot(dress_up_every=0)
        robot.dress_up('ironman')
        run(p, 1)
        self.take_off(robot, p)
        from robo.core import personality
        personality.on_costume_clicked(robot, p.clock())      # back to plain Robo
        run(p, 15)
        self.assertFalse(robot.body.airborne)
        self.assertEqual(robot.body.y, robot.bounds.ground_y)

    def test_lands_to_work_on_a_task(self):
        robot, p = make_robot(look='ironman')
        self.take_off(robot, p)
        robot.start_task()
        run(p, 15)
        self.assertTrue(robot.body.on_ground)
        self.assertTrue(robot.hacker.typing)

    def test_lands_when_he_turns_evil(self):
        robot, p = make_robot(look='ironman', evil_after=5)
        self.take_off(robot, p)
        p.idle.feed(6)
        run(p, 15)
        self.assertTrue(robot.evil.active)
        self.assertTrue(robot.body.on_ground)

    def test_let_go_in_the_air_a_flyer_hovers(self):
        from robo.platform.base import PointerEvent
        robot, p = make_robot(look='ironman')
        x, y = p.window.pos
        robot.pointer_press(PointerEvent(1, 85, 200, x + 85, y + 200))
        robot.pointer_motion(PointerEvent(1, 85, 200, x + 85, y - 300))
        robot.pointer_release(PointerEvent(1, 85, 200, x + 85, y - 300))
        run(p, 0.5)
        self.assertEqual(robot.body.state, 'hover')
        robot, p = make_robot(look='robo')
        x, y = p.window.pos
        robot.pointer_press(PointerEvent(1, 85, 200, x + 85, y + 200))
        robot.pointer_motion(PointerEvent(1, 85, 200, x + 85, y - 300))
        robot.pointer_release(PointerEvent(1, 85, 200, x + 85, y - 300))
        run(p, 0.1)
        self.assertEqual(robot.body.state, 'fall')

    def test_ask_him_to_fly(self):
        robot, p = make_robot(look='ironman')
        brain = RuleBrain(random.Random(1))
        reply = brain.respond('can you fly around', robot.conversation.context())
        self.assertEqual((reply.action, reply.action_arg), ('travel', 'fly'))
        plain, _ = make_robot()
        self.assertIsNone(brain.respond('fly!', plain.conversation.context()).action)
        reply = brain.respond('turn into iron man', plain.conversation.context())
        self.assertEqual(reply.action_arg, 'ironman')

    def test_menu_offers_flying(self):
        robot, p = make_robot(look='ironman')
        from robo.platform.base import PointerEvent
        robot.pointer_press(PointerEvent(3, 85, 200, 0, 0))
        item = next(i for i in p.window.menus[-1] if i.label and 'Fly' in i.label)
        item.action()
        run(p, 1)
        self.assertTrue(robot.body.airborne)


if __name__ == '__main__':
    unittest.main()
