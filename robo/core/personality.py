"""What the robot decides to do, and how he reacts to things.

This is the file to edit to change Robo's character: how often he naps,
waves or walks, what he does when dressed up, and how he reacts when a
bubble pops up, you pat him, or he changes clothes.
"""
import logging

from . import characters, outfits
from . import face as F

log = logging.getLogger(__name__)

TASK_DONE_ICON = 'task_done'

NAP_CHANCE = 0.10
NAP_COOLDOWN = 240          # seconds between naps
WAVE_CHANCE = 0.12
TURN_CHANCE = 0.10
EVIL_LAUGH_CHANCE = 0.25
EVIL_SCHEME_CHANCE = 0.30
EVIL_SPEED = 0.6            # evil robot sneaks slowly
# dressed up
MOVE_CHANCE = 0.40          # do his signature move
DEMAND_CHANCE = 0.20        # repeat his demand ("still no pyramid?!")
DEMAND_SECONDS = 5.0
SIGNATURE_CHANCE = 0.12     # everyday look is a character: do its move now and then


# ---------------------------------------------------------------- free time
def next_action(robot, now):
    """Called when the robot has been idle long enough."""
    if robot.body.airborne:                 # done hovering / hanging up there
        robot.travel.next(robot, now)
    elif robot.travel.busy(now):            # shooting a web, mid-teleport: wait for it
        robot.body.rest(now, 1, 2)
    elif robot.busy_working:
        robot.body.rest(now, 4, 8)          # stays at his laptop
    elif robot.evil.active:
        _next_evil_action(robot, now)
    elif robot.wardrobe.current:
        _next_costumed_action(robot, now)
    else:
        _next_good_action(robot, now)


def _next_costumed_action(robot, now):
    body, wardrobe = robot.body, robot.wardrobe
    if robot.travel.maybe_start(robot, now):    # fly / swing / teleport somewhere
        return
    r = robot.rng.random()
    if r < MOVE_CHANCE and wardrobe.current.move:
        wardrobe.start_move(now)
        body.rest(now, wardrobe.move_seconds + 1, wardrobe.move_seconds + 3)
    elif r < MOVE_CHANCE + DEMAND_CHANCE:
        demand(robot, now)
        body.rest(now, 3, 5)
    else:
        body.wander(now, robot.bounds, 60, 380)


def demand(robot, now):
    if robot.wardrobe.current.demand:
        robot.bubbles.push(robot.wardrobe.current.demand, now, duration=DEMAND_SECONDS,
                           dedup=False)


def _next_good_action(robot, now):
    body = robot.body
    if robot.travel.maybe_start(robot, now):    # his everyday look may fly too (Iron Man!)
        return
    mind = robot.mind
    if mind.sleepy and robot.settings.naps and now - body.last_sleep > 60 \
            and robot.rng.random() < 0.45:
        body.sleep(now, robot.rng.uniform(40, 90))          # can't keep his eyes open
        return
    if mind.tired and robot.rng.random() < 0.15:
        robot.face.show(F.YAWN, now, 2.5)
        body.rest(now, 3, 5)
        return
    if maybe_design(robot, now, bored=mind.bored):
        return
    if maybe_pastime(robot, now, bored=mind.bored):
        return
    look = robot.look_character
    r = robot.rng.random()
    if look is not None and look.move and r < SIGNATURE_CHANCE:
        _look_move(robot, look, now)             # showing off his look's move now and then
        return
    r = robot.rng.random()
    if r < NAP_CHANCE and robot.settings.naps and now - body.last_sleep > NAP_COOLDOWN:
        body.sleep(now, robot.rng.uniform(25, 60))
    elif r < NAP_CHANCE + WAVE_CHANCE:
        robot.face.show(F.WAVE, now, 2.2)
        body.rest(now, 3, 6)
    elif r < NAP_CHANCE + WAVE_CHANCE + TURN_CHANCE:
        body.turn_around()
        body.rest(now, 2, 5)
    else:
        body.wander(now, robot.bounds, 60, 380)


def _next_evil_action(robot, now):
    body, r = robot.body, robot.rng.random()
    if r < EVIL_LAUGH_CHANCE:
        robot.face.show(F.LAUGH, now, 1.6)
        body.hop(now)
        body.rest(now, 2.5, 4)
    elif r < EVIL_LAUGH_CHANCE + EVIL_SCHEME_CHANCE:
        body.rest(now, 3, 7)             # standing still while evil = rubbing hands
    else:
        body.wander(now, robot.bounds, 80, 420)


def _look_move(robot, look, now):
    """The everyday look's signature move: shown with the face timers (arms and mood)."""
    robot.face.show(F.LOOK_MOVE, now, look.move.seconds)
    robot.body.rest(now, look.move.seconds + 1, look.move.seconds + 3)


# ---------------------------------------------------------------- his own initiative
def on_speak_up(robot, kind, now):
    """Body language when he says something on his own (see robo.core.initiative)."""
    face, body = robot.face, robot.body
    body.stop(now, 4, 7)
    if kind in ('first_meeting', 'morning', 'welcome_back'):
        face.show(F.WAVE, now, 2.2)
        face.show(F.HAPPY, now, 1.5)
        face.add_hearts(now, (0.3, 0.6))
        body.hop(now)
    elif kind in ('late', 'sleepy'):
        face.show(F.YAWN, now, 2.5)
    elif kind == 'break':
        face.show(F.YAWN, now, 1.5)             # a big stretch, to set an example
    elif kind == 'bored':
        face.show(F.SAD, now, 2.0)
    else:
        face.show(F.HAPPY, now, 1.0)


DESIGN_CHANCE = 0.05            # per free moment, once a design is due (more when bored)


def maybe_design(robot, now, bored=False):
    """Designing himself a new outfit, on his own (Settings: Characters). True if he did."""
    from .initiative import in_quiet_hours
    if robot.rng.random() > (DESIGN_CHANCE * 3 if bored else DESIGN_CHANCE):
        return False
    if not robot.mind.user_here or robot.wardrobe.current or \
            in_quiet_hours(robot.settings.quiet_hours, robot.initiative.now_dt().hour) or \
            not robot.design_due():
        return False
    log.info('feels like designing a new outfit')
    robot.face.show(F.SURPRISED, now, 0.6)            # an idea!
    robot.face.show(F.ARMS_UP, now, 1.0)
    robot.design_outfit(own=True)
    if robot.settings.chattiness != 'off':
        robot.conversation.announce("Ooh, I've got an idea for a new outfit! "
                                    'Give me a few minutes at my laptop.', 'happy')
    return True


def maybe_pastime(robot, now, bored=False):
    """Read, juggle, hum...: what he does when nothing is going on. True if he did."""
    hobbies = robot.hobbies()
    if not hobbies or robot.rng.random() > (0.45 if bored else 0.12):
        return False
    name = robot.rng.choice(sorted(hobbies))
    move = hobbies[name]
    robot.face.hobby = name
    robot.face.show(F.HOBBY, now, move.seconds)
    robot.body.rest(now, move.seconds + 1, move.seconds + 3)
    robot.mind.nudge(boredom=-0.25)
    return True


def nap(robot, now, seconds):
    """Menu: take a nap (comes down first if he's up in the air)."""
    if robot.body.airborne:
        robot.travel.land(robot)
    else:
        robot.body.sleep(now, seconds)


# ---------------------------------------------------------------- reactions
def on_bubble_shown(robot, bubble, now):
    body, face = robot.body, robot.face
    robot.wardrobe.stop_move()
    if body.wake(now):
        face.show(F.SURPRISED, now, 0.5)
    body.stop(now)
    if body.state == 'idle':
        body.state_until += bubble.duration    # stay put while the bubble is up
    if bubble.kind in characters.demand_icons():   # his own demand: stamp and insist
        face.show(F.ARMS_UP, now, 1.6)
        body.hop(now)
        return
    face.show(F.SURPRISED, now, 0.45)
    face.show(F.ARMS_UP, now, 1.0)
    body.hop(now)


def on_same_bubble_again(robot, now):
    robot.body.hop(now)


def on_pat(robot, now):
    body, face = robot.body, robot.face
    robot.mind.patted()
    face.clear(F.SAD)
    if body.wake(now):
        face.show(F.SURPRISED, now, 0.5)
    face.show(F.HAPPY, now, 1.4)
    face.add_hearts(now, (0, 0.25, 0.5))
    body.hop(now)
    if body.state == 'walk':
        body.rest(now, 2, 5)


def on_landed(robot, now):
    travel = robot.travel
    if travel.ability is not None and (travel.kind == 'fly' or travel.dropped):
        robot.face.show(F.HAPPY, now, 0.8)     # a planned landing: ta-da!
        travel.dropped = False
        return
    robot.face.show(F.SURPRISED, now, 0.4)


def on_arrived(robot, now):
    """Got to his spot in the air (he hovers / hangs there now)."""
    robot.face.show(F.HAPPY, now, 0.8)


def on_teleport(robot, change, now):
    if change == 'appeared':
        robot.face.show(F.HAPPY, now, 1.0)
        robot.body.hop(now)


def on_woke(robot, now):
    robot.mind.napped(now - robot.body.last_sleep)
    robot.face.show(F.SURPRISED, now, 0.5)
    robot.face.show(F.YAWN, now, 2.0)


def on_turned_evil(robot, now):
    body = robot.body
    robot.wardrobe.stop_move()             # evil plans first, dancing later
    if body.airborne:                      # evil plans are made on the ground
        robot.travel.land(robot)
    body.wake(now)
    if body.state == 'idle':
        body.state_until = now + 3
    robot.face.show(F.LAUGH, now, 2.4)    # mwahaha right after transforming


def on_turned_good(robot, now):
    body, face = robot.body, robot.face
    face.clear(F.LAUGH)
    face.show(F.SWEAT, now, 2.6)          # caught in the act...
    face.show(F.SURPRISED, now, 0.9)
    face.show(F.ARMS_UP, now, 0.9)
    face.show(F.HAPPY, now, 2.6)          # ...but happy you're back
    face.add_hearts(now, (1.0, 1.25))
    body.hop(now, delay=0.5)
    if body.on_ground:
        body.rest(now, 4, 8)


def should_dress_up(robot, now):
    """Dress up on his own only when he's free: awake, good, nothing to say."""
    return (robot.wardrobe.due(now) and robot.body.on_ground and robot.body.state != 'sleep'
            and not robot.evil.active and not robot.bubbles.busy and not robot.busy_working)


def on_dressed(robot, now):
    body, face = robot.body, robot.face
    robot.taste.wore(robot.wardrobe.current.id)
    robot.travel.check(robot)
    face.show(F.HAPPY, now, 1.5)
    face.show(F.ARMS_UP, now, 1.0)
    body.hop(now)
    body.rest(now, 3, 5)
    demand(robot, now)                     # first thing he does: make demands
    _say_why_this_outfit(robot, now)


SAY_WHY_CHANCE = {'off': 0.0, 'rarely': 0.25, 'sometimes': 0.5, 'often': 0.8}


def _say_why_this_outfit(robot, now):
    """He picked it himself: now and then he tells you why ("it's winter!")."""
    from .initiative import in_quiet_hours
    choice = robot.wardrobe.choice
    if choice is not None and choice.why == 'new':          # he just made it: show it off
        robot.face.add_hearts(now, (0.3, 0.6, 0.9))
        robot.conversation.announce(choice.announce or
                                    f'Ta-da! I designed this myself. I call it the '
                                    f'{robot.wardrobe.current.title}!', 'happy')
        return
    if choice is None or not choice.because or robot.conversation.active:
        return
    s = robot.settings
    if in_quiet_hours(s.quiet_hours, robot.initiative.now_dt().hour) or \
            robot.evil.is_inhibited() or robot.rng.random() >= SAY_WHY_CHANCE.get(s.chattiness, 0):
        return
    robot.initiative.last_spoke = now
    robot.speak_up('dressed_up', {'outfit': robot.wardrobe.current.title.lower(),
                                  'because': choice.because})


def on_undressed(robot, now):
    robot.travel.check(robot)
    robot.face.show(F.HAPPY, now, 1.2)
    robot.face.add_hearts(now, (0.1, 0.35))
    robot.body.hop(now)


def on_costume_clicked(robot, now):
    """Clicking him while dressed up snaps him out of it."""
    robot.face.show(F.SURPRISED, now, 0.5)
    _took_off(robot, now)
    robot.bubbles.discard(characters.demand_icons(), now)
    robot.wardrobe.undress(now)
    robot.body.stop(now)


def _took_off(robot, now):
    """You ended his costume: if that was right away, he takes the hint."""
    wardrobe = robot.wardrobe
    if wardrobe.current is not None and not wardrobe.changing(now):
        robot.taste.took_off(wardrobe.current.id, now - wardrobe.dressed_at, clicked=True)


def _outfit_feedback(robot, amount):
    if robot.wardrobe.current is not None:
        robot.taste.nudge(robot.wardrobe.current.id, amount)


# ---------------------------------------------------------------- seeing your screen
def on_seeing(robot, now):
    """You picked something to show him: he's all eyes, and asks how he can help."""
    from robo.conversation import Reply
    robot.face.show(F.SURPRISED, now, 0.5)
    robot.face.show(F.ARMS_UP, now, 0.8)
    robot.body.wake(now)
    robot.body.stop(now, 4, 6)
    what = 'your screen' if robot.seeing.kind == 'monitor' else 'that window'
    opener = Reply(f'I can see {what} now! What do you need help with?', 'happy')
    talk = robot.conversation
    if talk.can_hear:
        talk.start(opener=opener)
    else:
        talk.announce(opener.text + ' Double-click me to ask.', 'happy')


def on_not_seeing(robot, now, was_seeing):
    if not was_seeing:
        return                                  # you closed the picker: nothing to say
    robot.face.show(F.HAPPY, now, 1.0)
    robot.conversation.announce("Okay, I can't see your screen any more.", 'happy')


def on_settings_applied(robot, now):
    """A little "got it!" hop with a heart."""
    robot.face.show(F.HAPPY, now, 1.2)
    robot.face.add_hearts(now, (0.1,))
    robot.body.hop(now)


# ---------------------------------------------------------------- conversations
def on_conversation_started(robot, now):
    body = robot.body
    robot.mind.chatted()
    robot.memory.chatted()
    robot.initiative.talked(now)
    _outfit_feedback(robot, outfits.CHATTED)
    robot.face.clear(F.HOBBY)
    if body.wake(now):
        robot.face.show(F.SURPRISED, now, 0.5)
    body.stop(now)
    robot.wardrobe.stop_move()
    body.hop(now)


EMOTES = ('wave', 'cheer', 'hearts', 'laugh', 'dance')


def emote(robot, action, now):
    """A quick show of feelings (a Reply's action, or a plugin's plugin.emote)."""
    face, body, wardrobe = robot.face, robot.body, robot.wardrobe
    if action == 'wave':
        face.show(F.WAVE, now, 2.2)
    elif action == 'cheer':
        face.show(F.ARMS_UP, now, 1.4)
        body.hop(now)
    elif action == 'hearts':
        face.add_hearts(now, (0.2, 0.5, 0.8))
    elif action == 'laugh':
        face.show(F.LAUGH, now, 2.0)
        body.hop(now)
    elif action == 'dance':
        if wardrobe.current and wardrobe.current.move:
            wardrobe.start_move(now)
        elif not wardrobe.current and robot.look_character and robot.look_character.move:
            _look_move(robot, robot.look_character, now)
        else:
            face.show(F.ARMS_UP, now, 3.0)   # happy dance with his arms in the air
            body.hop(now)
            face.add_hearts(now, (0.5, 1.5))


def on_reply(robot, reply, now):
    """Do what the brain's Reply asks for, as he starts saying it."""
    face, body, wardrobe = robot.face, robot.body, robot.wardrobe
    body.stop(now, 30, 40)                 # stand still while chatting
    action = reply.action
    if reply.feeling == 'praised':
        robot.mind.complimented()
        _outfit_feedback(robot, outfits.PRAISED)
    elif reply.feeling == 'hurt':
        robot.mind.insulted()
        _outfit_feedback(robot, outfits.HURT)
    if reply.user_name:
        robot.memory.remember_name(reply.user_name)
    for fact in reply.remember:
        robot.memory.remember(fact)
    if action == 'forget':
        robot.memory.forget(reply.action_arg or 'all')
    if action in EMOTES:
        emote(robot, action, now)
    elif action == 'dress_up':
        robot.dress_up(reply.action_arg or None)   # no name: his own pick (not while hacking)
    elif action == 'undress' and not robot.busy_working:
        _took_off(robot, now)
        robot.bubbles.discard(characters.demand_icons(), now)
        wardrobe.undress(now)
    elif action == 'travel' and not robot.busy_working:
        robot.travel.start_kind(robot, reply.action_arg or '', now)
    elif action == 'start_task':
        robot.start_task(reply.action_arg)
    elif action == 'agent_task' and reply.action_arg:
        import json
        robot.start_task('agent', json.loads(reply.action_arg))   # asks you first
    elif action == 'abort_task':
        robot.abort_task(everything=reply.action_arg == 'all')
    elif action == 'stop_seeing':
        robot.stop_showing()
    elif action == 'design_outfit':
        robot.design_outfit(reply.action_arg or '')
    elif action == 'plugin' and reply.action_arg:
        robot.use_plugin_tool(reply.action_arg)


def on_conversation_ended(robot, last_reply, now):
    if last_reply is not None and last_reply.action == 'nap':
        robot.body.sleep(now, robot.rng.uniform(40, 70))
    else:
        robot.body.rest(now, 3, 6)


# ---------------------------------------------------------------- tasks
def on_task_given(robot, now):
    """You asked him to do something: no evil plans or costumes while working."""
    if robot.evil.calm_down(now) == 'good':
        on_turned_good(robot, now)
    robot.body.wake(now)
    robot.wardrobe.stop_move()
    robot.bubbles.discard(characters.demand_icons(), now)
    if robot.body.airborne:                # he works sitting down, at his laptop
        robot.travel.land(robot)
    robot.face.show(F.HAPPY, now, 1.2)


def on_task_event(robot, event, task, now):
    face = robot.face
    if event == 'finished':
        robot.bubbles.push(TASK_DONE_ICON, now, duration=5.0, dedup=False)
        face.show(F.ARMS_UP, now, 1.6)
        face.show(F.HAPPY, now, 2.0)
        face.add_hearts(now, (0.2, 0.5))
        robot.review_changes(task)
        robot.mind.task_done()
        if task.kind == 'agent':                 # tell you what he did
            robot.memory.remember_task(task.title, task.result)
            robot.conversation.announce(task.result or 'All done!', 'happy')
        elif task.kind == 'design':              # he'll show it off once he's changed
            robot.designed(task)
    elif event == 'failed':
        robot.bubbles.push('warning', now, duration=5.0, dedup=False)
        face.show(F.SWEAT, now, 2.5)
        face.show(F.SURPRISED, now, 0.6)
        if task.kind == 'agent':
            robot.conversation.announce(f"Sorry, I couldn't finish that task. {task.error}.",
                                        'sad')
        elif task.kind == 'design':
            robot.conversation.announce("Hmm, my new outfit didn't come out right. "
                                        "I'll try again another time!", 'sad')
    elif event == 'aborted':
        face.show(F.SURPRISED, now, 0.5)


def on_task_refused(robot, now):
    """He can't (or may not) do the task: no sandbox, or you said no."""
    robot.bubbles.push('warning', now, duration=4.0, dedup=False)
    robot.face.show(F.SWEAT, now, 2.0)


def on_hacker_dressed(robot, now):
    robot.wardrobe.clear(now)              # the hacker outfit replaces any costume
    robot.face.show(F.HAPPY, now, 1.0)
    robot.body.hop(now)


def on_hacker_undressed(robot, now):
    robot.face.show(F.HAPPY, now, 1.2)
    robot.body.hop(now)
    if robot.body.on_ground:
        robot.body.rest(now, 3, 6)


def walk_speed(robot):
    speed = robot.settings.walk_speed
    if robot.evil.active:
        return speed * EVIL_SPEED
    walker = robot.wardrobe.current or robot.look_character
    return speed * (walker.walk_speed if walker else 1.0) * robot.mind.walk_factor()
