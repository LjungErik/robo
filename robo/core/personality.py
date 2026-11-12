"""What the robot decides to do, and how he reacts to things.

This is the file to edit to change Robo's character: how often he naps,
waves or walks, what he does when dressed up, and how he reacts when a
bubble pops up, you pat him, or he changes clothes.
"""
from . import face as F
from .characters import DEMAND_ICONS

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


# ---------------------------------------------------------------- free time
def next_action(robot, now):
    """Called when the robot has been idle long enough."""
    if robot.evil.active:
        _next_evil_action(robot, now)
    elif robot.wardrobe.current:
        _next_costumed_action(robot, now)
    else:
        _next_good_action(robot, now)


def _next_costumed_action(robot, now):
    body, wardrobe, r = robot.body, robot.wardrobe, robot.rng.random()
    if r < MOVE_CHANCE:
        wardrobe.start_move(now)
        body.rest(now, wardrobe.current.move_seconds + 1, wardrobe.current.move_seconds + 3)
    elif r < MOVE_CHANCE + DEMAND_CHANCE:
        demand(robot, now)
        body.rest(now, 3, 5)
    else:
        body.wander(now, robot.bounds, 60, 380)


def demand(robot, now):
    robot.bubbles.push(robot.wardrobe.current.demand, now, duration=DEMAND_SECONDS, dedup=False)


def _next_good_action(robot, now):
    body, r = robot.body, robot.rng.random()
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


# ---------------------------------------------------------------- reactions
def on_bubble_shown(robot, bubble, now):
    body, face = robot.body, robot.face
    robot.wardrobe.stop_move()
    if body.wake(now):
        face.show(F.SURPRISED, now, 0.5)
    body.stop(now)
    if body.state == 'idle':
        body.state_until += bubble.duration    # stay put while the bubble is up
    if bubble.kind in DEMAND_ICONS:            # his own demand: stamp and insist
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
    if body.wake(now):
        face.show(F.SURPRISED, now, 0.5)
    face.show(F.HAPPY, now, 1.4)
    face.add_hearts(now, (0, 0.25, 0.5))
    body.hop(now)
    if body.state == 'walk':
        body.rest(now, 2, 5)


def on_landed(robot, now):
    robot.face.show(F.SURPRISED, now, 0.4)


def on_woke(robot, now):
    robot.face.show(F.SURPRISED, now, 0.5)


def on_turned_evil(robot, now):
    body = robot.body
    robot.wardrobe.stop_move()             # evil plans first, dancing later
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
            and not robot.evil.active and not robot.bubbles.busy)


def on_dressed(robot, now):
    body, face = robot.body, robot.face
    face.show(F.HAPPY, now, 1.5)
    face.show(F.ARMS_UP, now, 1.0)
    body.hop(now)
    body.rest(now, 3, 5)
    demand(robot, now)                     # first thing he does: make demands


def on_undressed(robot, now):
    robot.face.show(F.HAPPY, now, 1.2)
    robot.face.add_hearts(now, (0.1, 0.35))
    robot.body.hop(now)


def on_costume_clicked(robot, now):
    """Clicking him while dressed up snaps him out of it."""
    robot.face.show(F.SURPRISED, now, 0.5)
    robot.bubbles.discard(DEMAND_ICONS, now)
    robot.wardrobe.undress(now)
    robot.body.stop(now)


def on_settings_applied(robot, now):
    """A little "got it!" hop with a heart."""
    robot.face.show(F.HAPPY, now, 1.2)
    robot.face.add_hearts(now, (0.1,))
    robot.body.hop(now)


def walk_speed(robot):
    speed = robot.settings.walk_speed
    if robot.evil.active:
        return speed * EVIL_SPEED
    if robot.wardrobe.current:
        return speed * robot.wardrobe.current.walk_speed
    return speed
