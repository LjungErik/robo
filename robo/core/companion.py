"""Companion: the whole robot, wired together.

    events/idle ──► Companion ──► Body, Face, EvilMode, BubbleQueue
                        │                 │
          WindowHost ◄──┘   draw() ──► build_pose() ──► robo.render

It never touches the OS directly: it is given a WindowHost (window, mouse,
screen size) and receives Events and idle times from the platform.
"""
import logging
import random
import time

from robo.events import KINDS, Event
from robo.platform.base import MenuItem, PointerEvent, WindowHost
from robo.render.scene import draw_frame
from robo.tasks import TaskEnvironment, TaskManager, TaskRefused, make_task

from . import layout, personality
from .body import Body
from .bubble import BubbleQueue
from . import characters
from .evil import EvilMode
from .effects import Effects
from . import face as F
from .face import LOOK_MOVE, WAVE, Face
from .hacker import HackerMode
from .initiative import LISTENS_AFTER, Initiative, line_for
from .memory import Memory
from .mind import Mind
from .pose import build_pose
from .talk import Conversation
from .travel import Traveller
from .wardrobe import Wardrobe

log = logging.getLogger(__name__)

DRAG_THRESHOLD = 6          # px of movement before a press becomes a drag
DOUBLE_CLICK_SECONDS = 0.35 # a second click within this starts a conversation
SCREEN_CHECK_SECONDS = 5    # how often to re-read the work area / re-raise


class Companion:
    def __init__(self, settings, clock=time.monotonic, rng=None):
        self.settings = settings
        self.scale = settings.scale
        self.clock = clock
        self.rng = rng or random.Random()
        self.width, self.height = layout.window_size(self.scale)
        now = clock()
        self.t0 = self.last_tick = now
        self.face = Face(now, self.rng)
        self.evil = EvilMode(settings.effective_evil_after)
        self.bubbles = BubbleQueue()
        self.wardrobe = Wardrobe(settings.effective_dress_up_every, now, self.rng,
                                 allowed=settings.characters)
        self.effects = Effects(self.rng)
        self.travel = Traveller(self.rng)
        self.look = settings.look             # his everyday look (base design or character)
        self.tasks = TaskManager()
        self.task_env = TaskEnvironment()       # no sandbox = no tasks (set by the app)
        self.last_task_problem = None
        self.hacker = HackerMode()
        self.memory = Memory(None, enabled=settings.remember_me)   # the app gives it a file
        self.mind = Mind(self.memory, rng=self.rng)
        self.initiative = Initiative(self.rng)
        self._idle_seconds = 0.0
        self._next_initiative = 0.0
        self._last_grab_line = -1e9
        self.conversation = Conversation(self)
        self.body = None            # created in attach(), once we know the screen
        self.bounds = None
        self.host: WindowHost = None
        self.on_quit = lambda: None
        self.on_open_settings = None      # set by the app if the platform has a settings window
        self._press = None
        self._pending_click = None    # time of a click that may become a double-click
        self._last_pos = None
        self._last_bubble_visible = None
        self._next_screen_check = 0.0

    def hobbies(self):
        costume = self.wardrobe.current.id if self.wardrobe.current else ''
        return characters.REGISTRY.hobbies(self.look, costume)

    def personality(self):
        costume = self.wardrobe.current.id if self.wardrobe.current else ''
        return characters.REGISTRY.personality(self.look, costume)

    @property
    def look_character(self):
        """The Character he looks like when not dressed up (Robo by default)."""
        return characters.get(self.look) or characters.get(characters.DEFAULT_LOOK)

    # ------------------------------------------------------------ setup
    def attach(self, host: WindowHost):
        self.host = host
        now = self.clock()
        self.bounds = layout.walk_bounds(host.workarea(), self.scale)
        x = self.rng.uniform(self.bounds.min_x, self.bounds.max_x)
        self.body = Body(x, self.bounds.ground_y, self.scale, now, self.rng)
        self._next_screen_check = now + SCREEN_CHECK_SECONDS
        self._sync_window()

    def apply_settings(self, settings):
        """Take new settings while running (hot reload)."""
        now = self.clock()
        self.settings = settings
        if settings.scale != self.scale:
            self.scale = settings.scale
            self.width, self.height = layout.window_size(self.scale)
            self.host.resize(self.width, self.height)
            self._last_height = self.height
            self.body.scale = self.scale
            self.bounds = layout.walk_bounds(self.host.workarea(), self.scale)
            self.body.x = self.bounds.clamp_x(self.body.x)
            if self.body.on_ground:
                self.body.y = self.bounds.ground_y
            self._last_pos = self._last_bubble_visible = None   # force move + click regions
        if self.evil.set_after(settings.effective_evil_after, now) == 'good':
            personality.on_turned_good(self, now)
        self.wardrobe.configure(settings.effective_dress_up_every, settings.characters, now)
        self.memory.set_enabled(settings.remember_me)
        if settings.look != self.look:
            self.look = settings.look
            self.travel.check(self)              # e.g. no longer Iron Man: come down
        self.conversation.configure(settings)
        self._sync_window()
        personality.on_settings_applied(self, now)

    # ------------------------------------------------------------ inputs from the platform
    def handle_event(self, event: Event):
        """An EventSource reported something."""
        log.info('[%s] %s: %s', event.source, event.kind, event.detail)
        result = self.bubbles.push(event.kind, self.clock(), duration=self.settings.bubble_seconds)
        if result == 'bumped':
            personality.on_same_bubble_again(self, self.clock())
        elif result == 'ignored':
            log.info('  (duplicate, ignored)')

    def on_idle(self, seconds):
        """The IdleMonitor reports how long the user has been away."""
        now = self.clock()
        self._idle_seconds = seconds
        self.initiative.on_idle(seconds, now, self.memory)
        change = self.evil.on_idle(seconds, now, may_turn_evil=not self.busy_working)
        if change == 'evil':
            log.info('no input for a while... turning EVIL')
            personality.on_turned_evil(self, now)
        elif change == 'good':
            log.info('user is back — good robot again')
            personality.on_turned_good(self, now)

    def demo(self):
        """Queue every icon once, quickly."""
        now = self.clock()
        for kind in KINDS:
            self.bubbles.push(kind, now, duration=2.2, dedup=False, limit=len(KINDS))

    def quit(self):
        self.on_quit()

    # ------------------------------------------------------------ frame update
    def tick(self):
        now = self.clock()
        dt = min(0.1, now - self.last_tick)
        self.last_tick = now

        if now >= self._next_screen_check:
            self._next_screen_check = now + SCREEN_CHECK_SECONDS
            self.bounds = layout.walk_bounds(self.host.workarea(), self.scale)
            self.body.settle(now, self.bounds)
            if self._press is None:
                self.host.keep_on_top()

        self.face.update(now, dt)
        self.evil.update(dt)
        self.mind.update(dt, busy=self.busy_working or self.conversation.active,
                         entertained=self.face.active(F.HOBBY, now),
                         idle_seconds=self._idle_seconds)
        self.memory.update()
        self._follow_pointer(now)
        if now >= self._next_initiative:
            self._next_initiative = now + 1.0
            choice = self.initiative.choose(self, now)
            if choice:
                self.speak_up(*choice)

        happened = self.body.update(now, dt, self.bounds, personality.walk_speed(self))
        if happened == 'ready' and not self.bubbles.busy and not self.conversation.active:
            personality.next_action(self, now)
        elif happened == 'landed':
            personality.on_landed(self, now)
        elif happened == 'arrived':
            personality.on_arrived(self, now)
        elif happened == 'woke':
            personality.on_woke(self, now)

        shown = self.bubbles.update(now)
        if shown:
            personality.on_bubble_shown(self, shown, now)

        self._update_costume(now, dt)
        self._update_travel(now, dt)
        self._update_tasks(now, dt)
        self.conversation.update(now)
        if self._pending_click is not None and now - self._pending_click > DOUBLE_CLICK_SECONDS:
            self._pending_click = None
            self._single_click(now)

        self._sync_window()
        self.host.redraw()

    def _update_costume(self, now, dt):
        if personality.should_dress_up(self, now):
            self.wardrobe.dress_up(now)
        change = self.wardrobe.update(now)
        if change == 'dressed':
            log.info('dressed up as %s', self.wardrobe.current.id)
            personality.on_dressed(self, now)
        elif change == 'undressed':
            log.info('back to plain old Robo')
            personality.on_undressed(self, now)
        character = self.wardrobe.current
        if character and character.particles and self.wardrobe.doing_move(now):
            self.effects.emit(character.particles, now, dt, self.body.facing)
        elif character is None and self.face.active(LOOK_MOVE, now):
            look = self.look_character
            if look is not None and look.particles:
                self.effects.emit(look.particles, now, dt, self.body.facing)
        elif self.face.active(F.HOBBY, now):
            hobby = self.hobbies().get(self.face.hobby)
            if hobby is not None and hobby.particles:
                self.effects.emit(hobby.particles, now, dt, self.body.facing)
        self.effects.update(now)

    def _update_travel(self, now, dt):
        change = self.travel.update(self, now, dt)
        if change:
            log.info('teleport: %s', change)
            personality.on_teleport(self, change, now)
        a = self.travel.ability
        if a is not None and a.particles and (self.body.airborne or self.travel.teleporting(now)):
            self.effects.emit(a.particles, now, dt, self.body.facing)

    # ------------------------------------------------------------ being alive
    def _follow_pointer(self, now):
        """His eyes follow your mouse pointer (when the platform can tell where it is)."""
        if self.body.state in ('sleep', 'drag') or self.evil.active:
            return
        pos = self.host.pointer_position() if self.host is not None else None
        if not pos:
            return
        x, y, _h, offset = self._window_rect()
        face_x = self.body.x
        face_y = y + (layout.GROUND_Y + offset - 85) * self.scale
        self.face.follow(now, pos[0] - face_x, pos[1] - face_y, self.body.facing)

    def speak_up(self, kind, info=None):
        """Say something on his own (see robo.core.initiative)."""
        from robo.conversation import Reply
        now = self.clock()
        log.info('speaking up: %s', kind)
        personality.on_speak_up(self, kind, now)
        talk = self.conversation
        if talk.active or talk.voice is talk.silent_voice:
            return                                 # no voice: the body language says it
        text = line_for(kind, self.personality(), self.memory.name, self.rng, info)
        mood = {'late': 'yawn', 'sleepy': 'yawn', 'bored': 'sad'}.get(kind, 'happy')
        fallback = Reply(text, mood) if text else None
        listen = kind in LISTENS_AFTER and talk.can_hear

        def deliver(reply):
            if talk.active or not reply.text:
                return
            if listen:
                talk.start(opener=reply, quiet=True)   # ...and listens for an answer
            else:
                talk.announce(reply.text, reply.mood)
        brain = talk.brain
        if hasattr(brain, 'compose'):
            brain.compose(kind, info or {}, talk.context(), deliver, fallback)
        elif fallback is not None:
            deliver(fallback)

    def _picked_up(self, now):
        mood = self.mind.grabbed(now)
        if mood == 'giggle':
            self.face.show(F.GIGGLE, now, 60)
        elif mood == 'grumpy':
            self.face.show(F.GRUMPY, now, 60)
        talk = self.conversation
        if mood in ('giggle', 'grumpy') and self.settings.chattiness != 'off' \
                and talk.voice is not talk.silent_voice and not talk.active \
                and now - self._last_grab_line > 45 and self.rng.random() < 0.5:
            kind = 'picked_up_happy' if mood == 'giggle' else 'picked_up_grumpy'
            text = line_for(kind, self.personality(), self.memory.name, self.rng)
            if text:
                self._last_grab_line = now
                talk.announce(text, 'happy' if mood == 'giggle' else 'sad')

    def dress_up(self, character_id=None):
        if not self.busy_working:              # no costumes over the hacker outfit
            self.wardrobe.dress_up(self.clock(), character_id, exclude=(self.look,))

    def characters_reloaded(self):
        """Someone edited a character file: use the new version right away."""
        self.wardrobe.refresh()
        self.travel.check(self)

    # ------------------------------------------------------------ tasks
    @property
    def busy_working(self):
        """Has a task (or is still in his hacker outfit)."""
        return self.tasks.busy or self.hacker.active

    def start_task(self, kind=None, args=None):
        """Give him a task. Returns 'started', 'queued', 'asking' (waiting for you
        to approve its permissions) or 'unavailable' (it can't run safely here)."""
        now = self.clock()
        problem = self.task_env.unavailable_reason()
        if problem:
            log.warning("can't do tasks: %s", problem)
            personality.on_task_refused(self, now)
            return 'unavailable'
        try:
            task = make_task(kind, self.rng, self.task_env, args)
        except TaskRefused as e:
            log.warning("can't do that task: %s", e)
            self.last_task_problem = str(e)
            personality.on_task_refused(self, now)
            self.conversation.announce(f"Sorry, I can't do that task: {e}.", 'sad')
            return 'refused'
        perms = task.permissions
        lines = task.approval_lines() if hasattr(task, 'approval_lines') else \
            (perms.describe() if perms is not None else [])
        approved = bool((args or {}).get('approved'))     # filled in by you in the task form
        if not approved and (getattr(task, 'kind', '') == 'agent'
                             or (perms is not None and perms.needs_approval)):
            log.info('task %s asks for: %s', task.id, lines)

            def answered(ok):
                if ok:
                    self._submit(task)
                else:
                    log.info('task %s: permissions denied', task.id)
                    personality.on_task_refused(self, self.clock())
            self.task_env.approver.ask_permissions(task.title, lines, answered)
            return 'asking'
        return self._submit(task)

    def agent_can_do_tasks(self):
        factory = self.task_env.agent_factory
        if factory is None or self.task_env.unavailable_reason():
            return False
        agent = factory()
        return bool(agent and agent.supports_tasks)

    def ask_for_task(self):
        """Menu: a form for a task (what to do, which files). You chose the files
        yourself there, so it counts as approved."""
        agent = self.task_env.agent_factory() if self.task_env.agent_factory else None
        if agent is None:
            return
        shown = self.task_env.approver.ask_task(
            agent.name, lambda args: self.start_task('agent', args))
        if not shown:
            self.start_task()

    def _submit(self, task):
        now = self.clock()
        result = self.tasks.submit(task, now)
        log.info('task %s: %s (%s)', task.id, task.title, result)
        personality.on_task_given(self, now)
        return result

    def review_changes(self, task):
        """The task changed copies of your files: ask before applying them."""
        changes = getattr(task, 'changes', None)
        if not changes:
            return
        cleanup = getattr(task, 'cleanup', lambda: None)

        def answered(ok):
            if not ok:
                log.info('task %s: changes thrown away', task.id)
                cleanup()
                return
            applied, skipped = changes.apply()
            log.info('task %s: applied %d changes', task.id, len(applied))
            for change, reason in skipped:
                log.warning('  skipped %s: %s', change.original_path, reason)
            cleanup()
        self.task_env.approver.review_changes(task.title, changes.describe(), answered)

    def shutdown(self):
        """The app is closing: stop every task (kills their sandboxes)."""
        self.tasks.abort_all(self.clock())

    def abort_task(self, everything=False):
        """Abandon the current task (or all of them). Returns the aborted tasks."""
        now = self.clock()
        return self.tasks.abort_all(now) if everything else self.tasks.abort(now)

    def _update_tasks(self, now, dt):
        # Talking to him or picking him up interrupts the work; it resumes afterwards.
        self.tasks.set_paused('conversation', self.conversation.active, now)
        self.tasks.set_paused('held', self.body.held, now)
        for event, task in self.tasks.update(now):
            log.info('task %s %s', task.id, event)
            personality.on_task_event(self, event, task, now)
        change = self.hacker.update(now, dt, has_work=self.tasks.busy,
                                    can_sit=self.tasks.working and self.body.on_ground)
        if change == 'dressed':
            log.info('hacker mode on')
            personality.on_hacker_dressed(self, now)
        elif change == 'undressed':
            log.info('hacker mode off')
            personality.on_hacker_undressed(self, now)
        if self.hacker.typing:
            self.effects.emit('binary', now, dt, self.body.facing)

    def _window_rect(self):
        """(x, y, height, offset): where his window goes. Normally it's just around
        him; while a web is out it's a tall column from the top of the screen down
        to the ground, and he's drawn `offset` design px down it."""
        x = int(round(self.body.x - self.width / 2))
        if not self.travel.tall:
            return x, int(round(self.body.y)), self.height, 0.0
        top = int(self.bounds.min_y)
        height = self.height + int(round(self.bounds.ground_y - top))
        return x, top, height, (self.body.y - top) / self.scale

    def _sync_window(self):
        x, y, height, offset = self._window_rect()
        if height != getattr(self, '_last_height', self.height):
            self._last_height = height
            self.host.resize(self.width, height)
        if (x, y) != self._last_pos:
            self._last_pos = (x, y)
            self.host.move(x, y)
        visible = self.bubbles.visible
        key = (visible, round(offset * self.scale))
        if key != self._last_bubble_visible:
            self._last_bubble_visible = key
            self.host.set_click_regions(layout.click_regions(self.scale, visible, offset))

    # ------------------------------------------------------------ WindowListener
    def draw(self, cr):
        now = self.clock()
        offset = self._window_rect()[3]
        draw_frame(cr, self.scale, build_pose(self, now), self.bubbles.current, now, offset)

    def pointer_press(self, ev: PointerEvent):
        if ev.button == 3:
            self.host.show_menu(self.menu_items())
        elif ev.button == 1:
            offset = self._window_rect()[3]
            in_bubble = self.bubbles.visible and layout.BUBBLE_HITBOX.contains(
                ev.x / self.scale, ev.y / self.scale - layout.bubble_offset(offset))
            # grab him where he is (not where a tall web window starts)
            wx, wy = self.body.x - self.width / 2, self.body.y
            self._press = dict(rx=ev.root_x, ry=ev.root_y,
                               ox=ev.root_x - wx, oy=ev.root_y - wy, in_bubble=in_bubble)

    def pointer_motion(self, ev: PointerEvent):
        p = self._press
        if not p:
            return
        if self.body.state != 'drag':
            if abs(ev.root_x - p['rx']) + abs(ev.root_y - p['ry']) < DRAG_THRESHOLD:
                return
            self.body.grab(self.clock())
            self.travel.cut_web(self.clock())         # picked up: the web is gone
            self._picked_up(self.clock())
        self.body.drag_to(ev.root_x - p['ox'] + self.width / 2, ev.root_y - p['oy'])

    def pointer_release(self, ev: PointerEvent):
        if ev.button != 1 or not self._press:
            return
        now = self.clock()
        p, self._press = self._press, None
        if self.body.state == 'drag':
            self.face.clear(F.GIGGLE)
            self.face.clear(F.GRUMPY)
            self.body.drop(now, self.bounds)
            if self.body.state == 'fall':
                self.travel.on_dropped(self, now)
        elif p['in_bubble'] and not self.conversation.active:
            self.bubbles.dismiss(now)
        elif self._pending_click is not None:          # second click: let's talk!
            self._pending_click = None
            self.talk()
        else:
            self._pending_click = now                  # wait: maybe a double-click

    def _single_click(self, now):
        if self.conversation.active:
            self.conversation.stop()                   # shh
        elif (self.wardrobe.current and not self.wardrobe.changing(now)
              and not self.busy_working):
            personality.on_costume_clicked(self, now)
        elif self.bubbles.visible:
            self.bubbles.dismiss(now)
        else:
            personality.on_pat(self, now)

    def talk(self):
        """Start a conversation (or end the current one)."""
        if self.conversation.active:
            self.conversation.stop()
        else:
            self.conversation.start()

    # ------------------------------------------------------------ menu
    def menu_items(self):
        now = self.clock
        items = [MenuItem('👋  Wave hello', lambda: self.face.show(WAVE, now(), 2.5))]
        if self.busy_working:
            items.append(MenuItem('🛑  Abort task', self.abort_task))
        else:
            if self.agent_can_do_tasks():
                items.append(MenuItem('💻  Give me a task…', self.ask_for_task))
            else:
                items.append(MenuItem('💻  Do a task', self.start_task))
            if self.body.state == 'sleep':
                items.append(MenuItem('☀️  Wake up', lambda: self.body.wake(now())))
            else:
                items.append(MenuItem('😴  Take a nap', lambda: personality.nap(self, now(), 60)))
        if self.busy_working:
            pass                                  # no costumes while hacking
        elif self.wardrobe.current:
            items.append(MenuItem('👕  Back to normal',
                                  lambda: personality.on_costume_clicked(self, now())))
        else:
            items.append(MenuItem('🎭  Dress up', self.dress_up))
        if not self.busy_working and self.travel.abilities(self):
            label = {'fly': '🚀  Fly around', 'hang': '🕸️  Swing up',
                     'teleport': '✨  Teleport'}.get(self.travel.abilities(self)[0].kind)
            items.append(MenuItem(label, lambda: self.travel.start_kind(self, '', now())))
        if self.conversation.active:
            items.append(MenuItem('🤐  Stop talking', self.conversation.stop))
        else:
            items.append(MenuItem('🎤  Talk to me', self.talk))
        if self.on_open_settings:
            items.append(MenuItem('⚙️  Settings…', self.on_open_settings))
        items += [MenuItem('🎨  Show all icons', self.demo),
                  MenuItem.separator(),
                  MenuItem('Quit', self.quit)]
        return items
