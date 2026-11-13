"""Run with:  python3 -m unittest discover -s tests"""
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from robo.app import build_companion  # noqa: E402
from robo.config import Settings  # noqa: E402
from robo.core.bubble import BubbleQueue, bubble_kinds  # noqa: E402
from robo.core import characters  # noqa: E402
from robo.platform.base import PointerEvent  # noqa: E402
from robo.events import KINDS, Event, classify  # noqa: E402
from robo.platform.headless import HeadlessPlatform  # noqa: E402
from robo.render.icons import ICONS, icon_kinds  # noqa: E402


def make_robot(**settings):
    platform = HeadlessPlatform()
    settings.setdefault('chattiness', 'off')       # tests/test_personality.py covers speaking up
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
        self.assertEqual(set(bubble_kinds()), set(icon_kinds()))
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
    def test_every_character_has_an_outfit_and_a_demand(self):
        for cid in characters.costume_ids():
            c = characters.get(cid)
            self.assertTrue(c.demand, cid)
            self.assertIn(c.demand, icon_kinds(), cid)

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
        for cid in characters.costume_ids():
            character = characters.get(cid)
            robot.wardrobe.current = None
            robot.dress_up(cid)
            p.scheduler.advance(1)
            robot.wardrobe.start_move(p.clock())
            p.scheduler.advance(1)           # every tick renders the frame off-screen
            if character.particles:
                self.assertTrue(robot.effects.particles, cid)

    def test_menu_is_short(self):
        robot, p = make_robot()
        robot.pointer_press(PointerEvent(3, 85, 200, 0, 0))
        labels = [i.label or '' for i in p.window.menus[-1]]
        for gone in ('Dress up', 'Wave hello', 'Show all icons'):
            self.assertFalse(any(gone in l for l in labels), gone)
        self.assertTrue(any('Talk to me' in l for l in labels))

    def test_menu_offers_back_to_normal_while_dressed(self):
        robot, p = make_robot(dress_up_every=0)
        robot.dress_up(characters.costume_ids()[0])
        p.scheduler.advance(1)
        robot.pointer_press(PointerEvent(3, 85, 200, 0, 0))
        labels = [i.label or '' for i in p.window.menus[-1]]
        self.assertTrue(any('Back to normal' in l for l in labels))

    def test_every_setting_is_on_a_tab(self):
        from robo.config import FIELDS, TABS
        on_tabs = {sid for _t, _n, _e, sids in TABS for sid in sids}
        for f in FIELDS:
            self.assertIn(f.section, on_tabs, f.key)


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
                    '"known_characters": %s}' % json.dumps(list(characters.costume_ids())))
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


class BrainTest(unittest.TestCase):
    def setUp(self):
        from robo.conversation import Context, RuleBrain
        self.brain = RuleBrain(random.Random(1))
        self.ctx = Context(battery=(15, False), characters=('pirate', 'chef'))

    def ask(self, text):
        return self.brain.respond(text, self.ctx)

    def test_topics(self):
        self.assertIn('Robo', self.ask("what's your name").text)
        self.assertEqual(self.ask('tell me a joke').action, 'hearts')
        self.assertIn('15 percent', self.ask('how is my battery').text)
        self.assertEqual(self.ask('how is my battery').icon, 'battery_low')
        self.assertTrue(self.ask('goodbye').end)
        self.assertEqual(self.ask('you are so cute').icon, 'heart')
        self.assertEqual(self.ask('you are stupid').mood, 'sad')

    def test_specific_topics_beat_greetings(self):
        self.assertEqual(self.ask('hey what time is it').icon, 'alarm')

    def test_dress_up_by_name_and_random(self):
        r = self.ask('can you dress up as a wizard')
        self.assertEqual((r.action, r.action_arg), ('dress_up', 'wizard'))
        r = self.ask('put on a costume')
        self.assertIn(r.action_arg, ('pirate', 'chef'))      # only allowed characters

    def test_unknown_gets_a_friendly_fallback(self):
        r = self.ask('purple monkey dishwasher')
        self.assertFalse(r.end)
        self.assertEqual(r.mood, 'surprised')


class ConversationTest(unittest.TestCase):
    def setUp(self):
        self.robot, self.p = make_robot(dress_up_every=0, evil_after=0)

    def run_until_listening(self, max_seconds=20):
        for _ in range(int(max_seconds * 10)):
            if self.p.ears.listening:
                return
            self.p.scheduler.advance(0.1)
        self.fail('never started listening')

    def test_double_click_starts_a_chat_and_he_answers(self):
        x, y = self.p.window.pos
        for _ in range(2):
            self.robot.pointer_press(PointerEvent(1, 85, 200, x + 85, y + 200))
            self.robot.pointer_release(PointerEvent(1, 85, 200, x + 85, y + 200))
        self.assertTrue(self.robot.conversation.active)
        self.assertEqual(len(self.p.voice.said), 1)                 # greeting
        self.run_until_listening()
        self.assertEqual(self.robot.bubbles.current and self.robot.bubbles.current.kind or
                         self.robot.bubbles.pending[0].kind, 'mic')
        self.p.ears.hear('tell me a joke')
        self.assertEqual(self.robot.conversation.state, 'speaking')
        self.assertTrue(any(j in self.p.voice.said[-1] for j in ('robot', 'chips', 'virus',
                                                                  'drive', 'batteries')))
        self.run_until_listening()                                  # listens again
        self.p.ears.hear('goodbye')
        self.p.scheduler.advance(5)
        self.assertFalse(self.robot.conversation.active)
        self.assertIsNone(self.p.ears.listening)

    def test_mouth_moves_while_he_speaks(self):
        self.robot.talk()
        self.p.scheduler.advance(0.2)
        from robo.core.pose import build_pose
        mouth = [build_pose(self.robot, self.p.clock()).talk
                 for _ in range(10) if not self.p.scheduler.advance(0.05)]
        self.assertGreater(max(mouth), 0.5)

    def test_asking_for_a_costume_dresses_him_up(self):
        self.robot.talk()
        self.run_until_listening()
        self.p.ears.hear('dress up as a pirate please')
        self.p.scheduler.advance(1)
        self.assertEqual(self.robot.wardrobe.current.id, 'pirate')

    def test_silence_ends_the_conversation_politely(self):
        self.robot.talk()
        self.run_until_listening()
        self.p.ears.stay_silent()
        self.assertEqual(self.robot.conversation.state, 'speaking')   # farewell
        self.p.scheduler.advance(10)
        self.assertFalse(self.robot.conversation.active)

    def test_single_click_hushes_him(self):
        self.robot.talk()
        click_robot(self.robot, self.p)
        self.p.scheduler.advance(0.5)
        self.assertFalse(self.robot.conversation.active)

    def test_wake_word_starts_a_chat_when_enabled(self):
        self.robot.conversation.configure(Settings(wake_word=True))
        self.p.ears.say_wake_word()
        self.assertTrue(self.robot.conversation.active)

    def test_without_ears_he_explains(self):
        self.robot.conversation.ears = None
        self.robot.talk()
        self.assertIn('hear', self.p.voice.said[-1])
        self.p.scheduler.advance(10)
        self.assertFalse(self.robot.conversation.active)

    def test_voice_off_uses_silent_voice(self):
        self.robot.conversation.configure(Settings(voice=False))
        self.robot.talk()
        self.assertEqual(self.p.voice.said, [])
        self.assertTrue(self.robot.conversation.active)


def _speech_helper_ready():
    from robo.platform.linux.listen import data_dir, find_model
    return (os.path.exists(os.path.join(data_dir(), 'venv', 'bin', 'python'))
            and find_model() is not None)


@unittest.skipUnless(sys.platform.startswith('linux') and _speech_helper_ready(),
                     "Robo's speech recognition is not installed")
class SpeechRecognitionTest(unittest.TestCase):
    """Runs the real Vosk helper on a WAV file made with espeak-ng."""

    def test_helper_understands_a_sentence(self):
        import json
        import subprocess
        import tempfile
        from robo import audio
        from robo.platform.linux.listen import WORKER, data_dir, find_model
        from robo.platform.linux.voice import Espeak
        e = Espeak()
        samples = e.synth('tell me a joke', voice='en-us', wpm=150, pitch=45)
        with tempfile.TemporaryDirectory() as tmp:
            wav = os.path.join(tmp, 'q.wav')
            audio.write_wav(wav, samples, e.rate)
            python = os.path.join(data_dir(), 'venv', 'bin', 'python')
            proc = subprocess.Popen([python, '-I', WORKER, '--model', find_model(),
                                     '--input', wav], stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
            proc.stdin.write('listen 4\n')
            proc.stdin.flush()
            events = []
            for line in proc.stdout:                 # wait for the answer, then quit
                events.append(json.loads(line))
                if events[-1]['event'] in ('heard', 'silence', 'error'):
                    break
            proc.stdin.write('quit\n')
            proc.stdin.close()
            proc.wait(timeout=10)
        heard = [ev['text'] for ev in events if ev['event'] == 'heard']
        self.assertTrue(heard, events)
        self.assertIn('joke', heard[0])


class VoiceStyleTest(unittest.TestCase):
    def test_nice_robo_uses_the_soft_voice_and_evil_robo_the_robot_voice(self):
        robot, p = make_robot(dress_up_every=0, evil_after=5)
        robot.talk()
        self.assertEqual(p.voice.styles[-1], 'normal')
        robot.conversation.stop()
        p.idle.feed(6)                                   # nobody touched the computer...
        p.scheduler.advance(1)
        robot.conversation.on_wake_word()                # ..."hey robo" while he's evil
        self.assertEqual(p.voice.styles[-1], 'evil')

    def test_evil_lines_use_the_evil_voice(self):
        robot, p = make_robot(dress_up_every=0, evil_after=0)
        robot.talk()
        for _ in range(100):
            if p.ears.listening:
                break
            p.scheduler.advance(0.1)
        p.ears.hear('are you evil')
        self.assertEqual(p.voice.styles[-1], 'evil')

    def test_soft_voice_pitch_lift_keeps_the_length(self):
        import array
        from robo import audio
        from robo.platform.linux.voice import nice_pitch_factor
        self.assertAlmostEqual(nice_pitch_factor(0), 0.88)
        self.assertGreater(nice_pitch_factor(75), 1.0)
        samples = array.array('h', [1000] * 22050)
        factor = nice_pitch_factor(75)
        out = audio.resample(samples, factor)
        self.assertAlmostEqual(len(out), 22050 / factor, delta=2)
        soft = audio.soften(samples, 22050, volume=0.5)
        self.assertEqual(soft[0], 0)                     # faded in: no click
        self.assertEqual(max(soft), 500)


class TaskManagerTest(unittest.TestCase):
    def setUp(self):
        from robo.tasks import TimerTask, TaskManager
        self.Task = TimerTask
        self.m = TaskManager()

    def test_runs_one_and_queues_the_rest(self):
        a, b = self.Task(10), self.Task(10)
        self.assertEqual(self.m.submit(a, 0), 'started')
        self.assertEqual(self.m.submit(b, 0), 'queued')
        self.m.update(0)
        self.assertEqual(self.m.update(10.5), [('finished', a), ('started', b)])
        self.m.update(21)
        self.assertFalse(self.m.busy)

    def test_pause_does_not_count_as_work(self):
        a = self.Task(10)
        self.m.submit(a, 0)
        self.m.set_paused('conversation', True, 4)
        self.m.set_paused('held', True, 5)
        self.m.set_paused('conversation', False, 50)
        self.assertFalse(self.m.working)                 # still held
        self.m.set_paused('held', False, 100)
        self.assertAlmostEqual(a.progress(103), 0.7)
        self.m.update(105)
        self.assertEqual(a.state, 'running')
        self.m.update(106.5)
        self.assertEqual(a.state, 'done')

    def test_abort_current_starts_the_next_and_abort_all_clears(self):
        a, b, c = self.Task(10), self.Task(10), self.Task(10)
        for t in (a, b, c):
            self.m.submit(t, 0)
        self.assertEqual(self.m.abort(1), [a])
        self.assertEqual(self.m.current, b)
        self.m.abort_all(2)
        self.assertFalse(self.m.busy)
        self.assertEqual({a.state, b.state, c.state}, {'aborted'})

    def test_parallel_slots(self):
        from robo.tasks import TaskManager
        m = TaskManager(max_parallel=2)
        a, b = self.Task(10), self.Task(10)
        m.submit(a, 0)
        self.assertEqual(m.submit(b, 0), 'started')
        self.assertEqual(len(m.running), 2)


class TaskBrainTest(unittest.TestCase):
    def setUp(self):
        from robo.conversation import Context, RuleBrain
        self.brain = RuleBrain(random.Random(1))
        self.idle = Context()
        self.busy = Context(task='a top secret task', task_progress=0.42)

    def test_task_phrases(self):
        r = self.brain.respond('can you do a task for me', self.idle)
        self.assertEqual(r.action, 'start_task')
        self.assertTrue(r.end)
        self.assertEqual(self.brain.respond('abort task', self.busy).action, 'abort_task')
        self.assertEqual(self.brain.respond('stop the task', self.busy).action, 'abort_task')
        self.assertIsNone(self.brain.respond('abort task', self.idle).action)
        self.assertIn('42 percent', self.brain.respond("how's the task going", self.busy).text)

    def test_no_costumes_while_working(self):
        self.assertIsNone(self.brain.respond('dress up as a pirate', self.busy).action)


class HackerTaskTest(unittest.TestCase):
    def setUp(self):
        self.robot, self.p = make_robot(dress_up_every=10, evil_after=5)

    def chat(self, said):
        self.robot.talk()
        for _ in range(200):
            if self.p.ears.listening:
                break
            self.p.scheduler.advance(0.1)
        self.p.ears.hear(said)

    def test_do_a_task_hacks_then_finishes(self):
        self.chat('do a task')
        self.assertTrue(self.robot.tasks.busy)
        self.p.scheduler.advance(8)                      # says "on it", conversation ends
        self.assertFalse(self.robot.conversation.active)
        self.assertTrue(self.robot.hacker.typing)
        from robo.core.pose import build_pose
        pose = build_pose(self.robot, self.p.clock())
        self.assertEqual((pose.costume, pose.arms), ('hacker', 'type'))
        for i in range(70):                              # 2+ min, user away the whole time
            if not self.robot.tasks.busy:
                break
            self.assertFalse(self.robot.evil.active)
            self.assertIsNone(self.robot.wardrobe.current)
            self.p.idle.feed(30 + i * 2)
            self.p.scheduler.advance(2)
        self.assertFalse(self.robot.tasks.busy)
        self.assertEqual(self.robot.bubbles.current.kind, 'task_done')
        self.p.scheduler.advance(1)
        self.assertFalse(self.robot.hacker.dressed)

    def test_talking_pauses_the_task_and_it_resumes_after(self):
        self.robot.start_task()
        self.p.scheduler.advance(10)
        task = self.robot.tasks.current
        done = task.worked_seconds(self.p.clock())
        self.robot.talk()                                # interrupt
        self.p.scheduler.advance(1)
        self.assertFalse(self.robot.hacker.typing)
        self.assertTrue(self.robot.hacker.dressed)       # still the hacker, just standing
        self.p.scheduler.advance(5)
        self.assertAlmostEqual(task.worked_seconds(self.p.clock()), done, delta=0.1)
        self.robot.conversation.stop()
        self.p.scheduler.advance(5)
        self.assertGreater(task.worked_seconds(self.p.clock()), done + 4)
        self.assertTrue(self.robot.hacker.typing)

    def test_abort_task_by_voice(self):
        self.robot.start_task()
        self.p.scheduler.advance(10)
        self.chat('abort task')
        self.p.scheduler.advance(2)
        self.assertFalse(self.robot.tasks.busy)
        self.assertFalse(self.robot.hacker.dressed)

    def test_asking_again_queues_a_second_task(self):
        self.robot.start_task()
        self.assertEqual(self.robot.start_task(), 'queued')
        self.assertEqual(len(self.robot.tasks.queued), 1)

    def test_menu_offers_task_and_abort(self):
        def labels():
            self.robot.pointer_press(PointerEvent(3, 85, 200, 0, 0))
            return [i.label or '' for i in self.p.window.menus[-1]]
        self.assertTrue(any('Do a task' in l for l in labels()))
        self.robot.start_task()
        self.p.scheduler.advance(1)
        ls = labels()
        self.assertTrue(any('Abort task' in l for l in ls))
        self.assertFalse(any('Dress up' in l for l in ls))


class TaskSafetyTest(unittest.TestCase):
    def setUp(self):
        self.robot, self.p = make_robot(dress_up_every=0, evil_after=0)

    def test_no_sandbox_means_no_tasks(self):
        self.p.fake_sandbox.problem = 'bubblewrap is not installed'
        self.assertEqual(self.robot.start_task(), 'unavailable')
        self.assertFalse(self.robot.tasks.busy)
        from robo.conversation import RuleBrain
        reply = RuleBrain(random.Random(1)).respond('do a task',
                                                    self.robot.conversation.context())
        self.assertIsNone(reply.action)
        self.assertIn('bubblewrap', reply.text)

    def test_default_environment_refuses(self):
        from robo.core.companion import Companion
        self.assertIsNotNone(Companion(Settings()).task_env.unavailable_reason())

    def _register(self, permissions):
        from robo.tasks import SandboxedTask, catalog
        catalog.TASK_KINDS['needy'] = lambda rng, env, args: SandboxedTask(
            'placeholder', 'needy task', env, args={'seconds': 2}, permissions=permissions)
        self.addCleanup(catalog.TASK_KINDS.pop, 'needy')

    def test_permissions_are_asked_first(self):
        from robo.sandbox import Permissions
        self._register(Permissions(hosts=('example.com',)))
        self.p.fake_approver.answer = False
        self.assertEqual(self.robot.start_task('needy'), 'asking')
        self.assertEqual(self.p.fake_approver.asked[-1][0], 'permissions')
        self.assertIn('Download from: example.com', self.p.fake_approver.asked[-1][2])
        self.assertFalse(self.robot.tasks.busy)                 # you said no
        self.p.fake_approver.answer = True
        self.robot.start_task('needy')
        self.assertTrue(self.robot.tasks.busy)

    def test_failed_task_shows_a_warning(self):
        from robo.tasks import SandboxedTask
        task = SandboxedTask('nonsense', 'broken', self.robot.task_env)
        self.robot._submit(task)
        self.p.scheduler.advance(1)
        self.assertEqual(task.state, 'failed')
        self.assertFalse(self.robot.tasks.busy)
        kinds = [b.kind for b in self.robot.bubbles.pending] + \
            [self.robot.bubbles.current.kind if self.robot.bubbles.current else None]
        self.assertIn('warning', kinds)

    def test_quitting_stops_tasks(self):
        self.robot.start_task()
        self.p.scheduler.advance(1)
        proc = self.p.fake_sandbox.launched[-1][1]
        self.robot.shutdown()
        self.assertTrue(proc.killed)
        self.assertFalse(self.robot.tasks.busy)
