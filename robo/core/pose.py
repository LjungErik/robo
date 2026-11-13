"""Pose: a snapshot of how the robot should look in one frame.

build_pose() is where state becomes appearance (which eyes, which arm
gesture, antenna light...). The renderer only draws what the Pose says.
"""
import math
from dataclasses import dataclass, field
from typing import List, Optional

from . import face as F
from .body import HANG, SLEEP, WALK
from .hacker import OUTFIT as HACKER


@dataclass
class Pose:
    t: float = 0.0               # seconds since start (drives idle animations)
    facing: int = 1              # +1 right, -1 left
    walking: bool = False
    phase: float = 0.0           # walk cycle
    dangling: bool = False       # held by the mouse / falling
    lift: float = 0.0            # hop height
    squash: float = 0.0          # landing squash
    mood: str = 'normal'         # normal happy surprised sleep evil laugh
    openness: float = 1.0        # eyelids (blink)
    look: float = 0.0            # eye offset
    arms: str = 'rest'           # rest swing wave up scheme
    antenna: str = 'normal'      # normal alert sleep evil
    alert_kind: str = ''         # event kind when antenna == 'alert'
    glow: float = 0.0
    shadow: bool = True
    tilt: float = 0.0
    evil: float = 0.0            # 0 good .. 1 evil
    glitch: float = 0.0
    sweat: bool = False
    zzz: bool = False
    jitter: float = 0.0          # horizontal glitch shake
    hearts: List[float] = field(default_factory=list)   # ages of floating hearts
    costume: str = ''            # outfit id ('' = just Robo)
    skin: str = ''               # his everyday look: a base design or character id ('' = robo)
    airborne: bool = False       # flying / hovering / hanging somewhere up the screen
    travel: str = ''             # '', 'fly', 'hang' or 'teleport' while getting around
    cruising: bool = False       # moving through the air right now (not just hovering)
    poof: Optional[float] = None  # costume-change smoke, 0..1 while it plays
    particles: list = field(default_factory=list)       # robo.core.effects.Particle
    talk: float = 0.0            # mouth opening while speaking (0..1)
    sit: float = 0.0             # 0 standing .. 1 sitting at his laptop (hacker mode)


def _mood(robot, now, looks_evil):
    face, body = robot.face, robot.body
    if looks_evil:
        return 'laugh' if face.active(F.LAUGH, now) else 'evil'
    if body.state == SLEEP:
        return 'sleep'
    if face.active(F.SURPRISED, now) or body.held:
        return 'surprised'
    talk = robot.conversation
    if talk.state == 'speaking' and talk.reply is not None and talk.reply.mood:
        return talk.reply.mood
    if talk.state == 'thinking':
        return 'focus'
    travel = robot.travel.mood(robot, now)
    if travel:
        return travel
    if robot.wardrobe.doing_move(now):
        return robot.wardrobe.current.move.mood
    look_move = _look_move(robot, now)
    if look_move:
        return look_move.mood
    if face.active(F.HAPPY, now):
        return 'happy'
    if robot.hacker.typing:
        return 'focus'
    if robot.bubbles.open:
        return 'happy'
    return 'normal'


def _arms(robot, now, looks_evil):
    face, body = robot.face, robot.body
    if body.held:
        return 'up'
    if looks_evil:
        return 'swing' if body.state == WALK else 'scheme'
    travel = robot.travel.gesture(robot, now)
    if travel:
        return travel
    if robot.wardrobe.doing_move(now):
        return robot.wardrobe.current.move.gesture
    look_move = _look_move(robot, now)
    if look_move:
        return look_move.gesture
    if robot.hacker.typing:
        return 'type'
    if face.active(F.ARMS_UP, now) or face.active(F.HAPPY, now):
        return 'up'
    if face.active(F.WAVE, now):
        return 'wave'
    return 'swing' if body.state == WALK else 'rest'


def _look_move(robot, now):
    """The everyday look's Move while he's showing it off, else None."""
    if robot.wardrobe.current is None and robot.face.active(F.LOOK_MOVE, now):
        look = robot.look_character
        return look.move if look is not None else None
    return None


def _move_lift(robot, now, t):
    """Height off the ground during moves like floating or flying (the
    character file's `move.lift`, eased in and out)."""
    w = robot.wardrobe
    if not w.doing_move(now) or w.current.move.lift is None:
        return 0.0
    ease = min(1.0, (now - w.move_start) / 0.5, (w.move_until - now) / 0.5)
    ease = ease * ease * (3 - 2 * ease)
    return ease * max(0.0, float(w.current.move.lift({'t': t, 'phase': robot.body.phase})))


def _tilt(robot, now, sleeping):
    if sleeping:
        return 0.12 * robot.body.facing
    if robot.conversation.state == 'listening':
        return -0.1                        # head tilted: "I'm listening!"
    travel = robot.travel.tilt(robot)
    if travel is not None:
        return travel                      # leaning into the flight (head forward)
    w = robot.wardrobe
    if w.doing_move(now) and w.current.move.tilt is not None:
        return float(w.current.move.tilt({'t': now - robot.t0}))
    if robot.hacker.typing:
        return 0.05 + math.sin(now * 4) * 0.03   # nodding along to the code
    return 0.0


def build_pose(robot, now):
    body, face, evil, bubbles = robot.body, robot.face, robot.evil, robot.bubbles
    t = now - robot.t0
    evil_blend = evil.visible_blend(now, robot.rng)
    looks_evil = evil_blend > 0.5
    glitching = evil.glitching(now)
    sleeping = body.state == SLEEP and not looks_evil
    mood = _mood(robot, now, looks_evil)

    if bubbles.open:
        antenna, glow = 'alert', 0.5 + 0.5 * math.sin(t * 9)
    elif looks_evil:
        antenna, glow = 'evil', 0.6 + 0.4 * math.sin(t * 5)
    elif robot.hacker.dressed:
        antenna, glow = 'hack', 0.8 if int(t * 7) % 3 else 0.1   # busy disk light
    elif body.state == SLEEP:
        antenna, glow = 'sleep', 0.0
    else:
        antenna, glow = 'normal', 0.25 + 0.2 * math.sin(t * 2)

    character = robot.wardrobe.current
    hacker = robot.hacker
    sit = hacker.sit
    lift = body.hop_lift(now) * (1 - sit) + _move_lift(robot, now, t)
    walker = character or robot.look_character
    if walker and walker.walk_lift is not None and body.state == WALK:   # giddy-up / moon bounce
        lift += max(0.0, float(walker.walk_lift({'phase': body.phase, 't': t})))
    travel = robot.travel
    if travel.air > 0:                                     # room for jet flames + a gentle bob
        lift += travel.lift(t) + travel.air * math.sin(t * 3) * 2
    airborne = body.airborne

    return Pose(
        t=t, facing=body.facing, walking=body.state == WALK, phase=body.phase,
        dangling=body.held or body.state == HANG, lift=lift, squash=body.squash(now),
        mood=mood, openness=face.openness(now),
        look=face.look if mood == 'normal' else 0.0,
        arms=_arms(robot, now, looks_evil),
        antenna=antenna, alert_kind=bubbles.current.kind if bubbles.current else '', glow=glow,
        shadow=not body.held and not airborne, tilt=_tilt(robot, now, sleeping),
        evil=evil_blend, glitch=1.0 if glitching else 0.0,
        sweat=not looks_evil and face.active(F.SWEAT, now),
        zzz=sleeping,
        jitter=robot.rng.uniform(-3, 3) if glitching else 0.0,
        hearts=face.heart_ages(now),
        costume=HACKER if hacker.dressed else (character.id if character else ''),
        skin=robot.look,
        airborne=airborne, travel=travel.kind, cruising=body.cruising,
        poof=_first(robot.wardrobe.poof(now), hacker.poof(now), travel.poof(now)),
        particles=robot.effects.particles,
        talk=robot.conversation.mouth(now),
        sit=sit,
    )


def _first(*values):
    return next((v for v in values if v is not None), None)
