"""Travel: getting around the screen without walking.

A character file can give him `travel:` abilities (see robo.design.model.Travel):

    fly       take off, fly to a random spot anywhere on the screen, hover a
              while, maybe fly on to another spot, then land     (Iron Man)
    hang      shoot a web line up to the top of the screen; a web builds where
              it sticks; zip up it, hang and swing, then let go and drop, or
              lower himself down on the thread                   (Spider-Man)
    teleport  wind up (a snap of the fingers), vanish in a puff of smoke and
              reappear somewhere else                            (Thanos)

Traveller decides when (personality asks it), keeps track of the trip and
tells the Pose what to show. The Body does the actual moving.
"""
import math
from dataclasses import dataclass
from typing import Optional

from .body import FALL, FLY, HANG, IDLE, WALK

POOF_SECONDS = 0.7
WEB_LINGERS = 2.5             # seconds the web stays at the top after he lets go
WEB_FADES = 1.0               # ...then it fades away
HAND_Y = 53                   # design px from his feet up to his hand on the line (roughly)


@dataclass
class Web:
    """A web line from his hand up to a spot on the top of the screen."""
    anchor_x: float           # screen px
    anchor_y: float
    shot_at: float            # when he shot it
    shoot: float              # seconds to reach the top
    hit_at: Optional[float] = None      # when it stuck
    zip_at: Optional[float] = None      # when he started zipping up
    hang_at: Optional[float] = None     # when he got there (the swing starts)
    released_at: Optional[float] = None
    lowering: bool = False

    def progress(self, now):
        """0..1: how far the line has flown."""
        k = min(1.0, max(0.0, (now - self.shot_at) / max(0.01, self.shoot)))
        return 1 - (1 - k) ** 2

    def gone(self, now):
        return self.released_at is not None and now - self.released_at > WEB_LINGERS + WEB_FADES

AIR_BLEND_SECONDS = 0.4       # time to rise to / sink from the extra flying height
MIN_TELEPORT = 160            # design px: teleports go somewhere noticeably else


class Traveller:
    def __init__(self, rng):
        self.rng = rng
        self.ability = None          # the Travel being used right now
        self.hops_left = 0
        self.air = 0.0               # 0..1, eases the extra height in and out
        self.dropped = False         # let go of the thread on purpose (no "oops" face)
        self._windup_until = None    # teleport: gesture until this time, then poof
        self._swap_at = None
        self._target_x = None
        self.poof_start = -10.0
        self.web = None              # Web while one is out (his window is a tall column then)

    # ------------------------------------------------------------ queries
    @property
    def kind(self):
        return self.ability.kind if self.ability else ''

    @property
    def tall(self):
        """A web is out: his window reaches up to the top of the screen."""
        return self.web is not None

    def web_pose(self, robot, now):
        """What the drawing needs to know about the web (see Pose), or None."""
        w = self.web
        if w is None:
            return None
        body, s = robot.body, robot.scale
        from . import layout
        ground_y = body.y + layout.GROUND_Y * s          # his feet on the screen
        swing = 0.0
        if w.hang_at is not None and body.state == HANG:
            age = now - w.hang_at
            amp = self.ability.swing if self.ability else 0.0
            swing = amp * math.sin(age * 2.2) * math.exp(-age / 3.5) + 0.02 * math.sin(age * 1.3)
        return dict(
            web=w.progress(now),
            web_hit=now - w.hit_at if w.hit_at is not None else -1.0,
            web_gone=now - w.released_at if w.released_at is not None else -1.0,
            anchor=((w.anchor_x - body.x) / s, (w.anchor_y - ground_y) / s),
            swing=swing)

    def teleporting(self, now):
        return self._windup_until is not None or self._swap_at is not None \
            or now - self.poof_start < POOF_SECONDS

    def busy(self, now):
        """In the middle of something (web out, teleporting): don't wander off."""
        return (self.web is not None and self.web.released_at is None) or self.teleporting(now)

    def winding_up(self, now):
        return self._windup_until is not None and now < self._windup_until

    def poof(self, now):
        k = (now - self.poof_start) / POOF_SECONDS
        return k if 0 <= k < 1 else None

    @staticmethod
    def abilities(robot):
        """What the way he looks right now lets him do (costume first, then his look)."""
        costume = robot.wardrobe.current
        if costume is not None and costume.travel:
            return costume.travel
        look = robot.look_character
        return look.travel if look is not None else ()

    def can(self, robot, kind):
        return any(a.kind == kind for a in self.abilities(robot))

    def gesture(self, robot, now):
        """Arm gesture to show, or None."""
        a, body = self.ability, robot.body
        if a is None:
            return None
        if a.kind == 'teleport':
            return (a.gesture or None) if self.winding_up(now) else None
        if a.kind == 'hang' and self.web is not None:
            w = self.web
            if w.released_at is not None:
                return None
            if w.lowering:
                return a.climb_gesture or a.hover_gesture or 'up'
            if body.state == HANG:
                return a.hover_gesture or 'up'
            return a.gesture or 'up'                    # shooting and zipping up
        if body.cruising:
            return a.gesture or ('up' if a.kind == 'hang' else 'fly')
        if body.airborne:
            return a.hover_gesture or ('up' if a.kind == 'hang' else 'hover')
        return None

    def mood(self, robot, now):
        a = self.ability
        if a is None or not a.mood:
            return None
        if robot.body.airborne or self.winding_up(now):
            return a.mood
        return None

    def tilt(self, robot):
        a = self.ability
        if a is not None and robot.body.cruising and a.kind == 'fly':
            return a.tilt
        return None

    def lift(self, t):
        a = self.ability
        height = a.height if a is not None else 0.0
        return self.air * height

    # ------------------------------------------------------------ decisions
    def maybe_start(self, robot, now):
        """Called when he picks something to do. Returns True if he set off."""
        body = robot.body
        if not body.on_ground or body.state not in (IDLE, WALK) or self.busy(now) \
                or self.web is not None:
            return False
        for a in self.abilities(robot):
            if self.rng.random() < a.chance:
                self.start(robot, a, now)
                return True
        return False

    def start(self, robot, ability, now):
        body, bounds = robot.body, robot.bounds
        self.ability = ability
        self.dropped = False
        if ability.kind == 'fly':
            self.hops_left = self.rng.randint(*ability.hops) - 1
            self._fly_somewhere(robot)
        elif ability.kind == 'hang':                 # step 1: shoot the web up
            body.rest(now, 30, 30)                   # stand still while it flies
            self.web = Web(anchor_x=bounds.clamp_x(body.x) + body.facing * ability.anchor_dx
                           * robot.scale, anchor_y=bounds.min_y, shot_at=now,
                           shoot=ability.shoot)
        elif ability.kind == 'teleport':
            body.rest(now, ability.windup + POOF_SECONDS + 1.5, ability.windup + POOF_SECONDS + 3)
            self._windup_until = now + ability.windup
            self._target_x = self._far_x(robot)

    def start_kind(self, robot, kind, now):
        """Asked to ("fly around!"). Returns True if he can."""
        a = next((a for a in self.abilities(robot) if a.kind == kind or not kind), None)
        if a is None or self.busy(now) or self.web is not None:
            return False
        if robot.body.airborne:
            if a.kind == 'fly' and self.kind == 'fly':
                self._fly_somewhere(robot)
                return True
            return False
        if not robot.body.on_ground:
            return False
        robot.body.wake(now)
        self.start(robot, a, now)
        return True

    def next(self, robot, now):
        """He's done hovering / hanging: fly on, or come down."""
        if self.kind == 'fly' and self.hops_left > 0 and self._free(robot):
            self.hops_left -= 1
            self._fly_somewhere(robot)
        else:
            self.land(robot)

    def land(self, robot):
        body, a, now = robot.body, self.ability, robot.clock()
        w = self.web
        if w is not None and w.released_at is None:
            end = a.end if a is not None else 'drop'
            if end == 'either':
                end = self.rng.choice(('drop', 'lower'))
            if body.state == HANG and end == 'lower' and self._free(robot):
                w.lowering = True                    # down the silk, like a real spider
                self.dropped = True                  # (a planned landing)
                body.fly_to(body.x, robot.bounds.ground_y, a.lower_speed, robot.bounds,
                            kind='hang', landing=True)
                return
            w.released_at = now                      # let go
            if body.state == HANG:
                self.dropped = True
                body.state, body.vy = FALL, 0.0
            elif body.state == FLY:                  # still zipping up: let go mid-way
                body.state, body.vy = FALL, 0.0
            elif body.state == IDLE:
                body.rest(now, 1, 2)
            return
        if body.state == HANG:
            self.dropped = True
        body.land(robot.bounds, a.speed if a else 140.0)

    def cut_web(self, now):
        """Picked up with the mouse: the web is gone at once."""
        self.web = None

    def check(self, robot):
        """His look changed: if he can't do this kind of travel any more, come down."""
        if robot.body.airborne and not self.can(robot, self.kind or 'fly'):
            self.land(robot)

    def on_dropped(self, robot, now):
        """Let go of with the mouse up in the air: a flyer just hovers there."""
        a = next((a for a in self.abilities(robot) if a.kind == 'fly'), None)
        body = robot.body
        if a is None or body.y >= robot.bounds.ground_y - 1:
            return False
        self.ability = a
        self.hops_left = 0
        body.hover(now, *a.stay)
        return True

    def _free(self, robot):
        return not (robot.busy_working or robot.evil.active)

    def _fly_somewhere(self, robot):
        body, bounds, a = robot.body, robot.bounds, self.ability
        top = bounds.min_y
        span = bounds.ground_y - top
        x = self.rng.uniform(bounds.min_x, bounds.max_x)
        y = self.rng.uniform(top, top + span * 0.8)
        body.fly_to(x, y, a.speed, bounds, kind='fly', stay=a.stay)

    def _far_x(self, robot):
        b, x = robot.bounds, robot.body.x
        far = MIN_TELEPORT * robot.scale
        for _ in range(8):
            nx = self.rng.uniform(b.min_x, b.max_x)
            if abs(nx - x) >= far:
                return nx
        return b.min_x if x - b.min_x > b.max_x - x else b.max_x

    # ------------------------------------------------------------ per frame
    def update(self, robot, now, dt):
        """Returns 'vanished' / 'appeared' around a teleport, else None."""
        body = robot.body
        target = 1.0 if body.airborne and self.kind == 'fly' else 0.0
        step = dt / AIR_BLEND_SECONDS
        self.air = min(target, self.air + step) if target > self.air else max(target, self.air - step)

        if self._windup_until is not None and now >= self._windup_until:
            self._windup_until = None
            if body.held:                       # picked up mid-snap: never mind
                self._done_teleport()
                return None
            self.poof_start = now
            self._swap_at = now + POOF_SECONDS / 2
            return 'vanished'
        if self._swap_at is not None and now >= self._swap_at:
            self._swap_at = None
            if not body.held:
                body.teleport(self._target_x, robot.bounds)
            self._done_teleport()
            return 'appeared'
        if self.web is not None:
            self._update_web(robot, now)
        if self.ability is not None and self.kind != 'teleport' and not body.airborne \
                and not body.held and self.air <= 0 and self.web is None:
            self.ability = None                 # trip over
        return None

    def _update_web(self, robot, now):
        w, body, a, b = self.web, robot.body, self.ability, robot.bounds
        if body.state == 'drag' or a is None:
            self.web = None
            return
        if w.hit_at is None and now - w.shot_at >= w.shoot:
            w.hit_at = now                          # step 2: it sticks, the web spreads out
        if w.hit_at is not None and w.zip_at is None and w.released_at is None \
                and now - w.hit_at >= a.pause:
            w.zip_at = now                          # step 3: zip up the line
            s = robot.scale
            from . import layout
            # his hand ends up `rope` below the web; body.y is his (normal) window's top
            y = w.anchor_y + (a.rope + HAND_Y - layout.GROUND_Y) * s
            body.fly_to(body.x, y, a.speed, b, kind='hang', stay=a.stay,
                        above_top=(layout.GROUND_Y - 140) * s)
        if body.state == HANG and w.hang_at is None:
            w.hang_at = now                         # step 4: hang there and swing
        if w.lowering and body.on_ground and w.released_at is None:
            w.released_at = now                     # down safely: let go of the line
            w.lowering = False
        if w.released_at is None and body.on_ground and w.zip_at is not None \
                and body.state != FLY:
            w.released_at = now
        if w.gone(now):
            self.web = None

    def _done_teleport(self):
        self._target_x = None
        self.ability = None
