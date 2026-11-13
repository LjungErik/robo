"""Travel: getting around the screen without walking.

A character file can give him `travel:` abilities (see robo.design.model.Travel):

    fly       take off, fly to a random spot anywhere on the screen, hover a
              while, maybe fly on to another spot, then land     (Iron Man)
    hang      zip up a thread to the top of the screen, hang there, let go
              and drop back down                                 (Spider-Man)
    teleport  wind up (a snap of the fingers), vanish in a puff of smoke and
              reappear somewhere else                            (Thanos)

Traveller decides when (personality asks it), keeps track of the trip and
tells the Pose what to show. The Body does the actual moving.
"""
from .body import HANG, IDLE, WALK

POOF_SECONDS = 0.7
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

    # ------------------------------------------------------------ queries
    @property
    def kind(self):
        return self.ability.kind if self.ability else ''

    def teleporting(self, now):
        return self._windup_until is not None or self._swap_at is not None \
            or now - self.poof_start < POOF_SECONDS

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
        if not body.on_ground or body.state not in (IDLE, WALK) or self.teleporting(now):
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
        elif ability.kind == 'hang':
            body.fly_to(body.x, bounds.min_y, ability.speed, bounds, kind='hang',
                        stay=ability.stay)
        elif ability.kind == 'teleport':
            body.rest(now, ability.windup + POOF_SECONDS + 1.5, ability.windup + POOF_SECONDS + 3)
            self._windup_until = now + ability.windup
            self._target_x = self._far_x(robot)

    def start_kind(self, robot, kind, now):
        """Asked to ("fly around!"). Returns True if he can."""
        a = next((a for a in self.abilities(robot) if a.kind == kind or not kind), None)
        if a is None or self.teleporting(now):
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
        body = robot.body
        if body.state == HANG:
            self.dropped = True
        body.land(robot.bounds, self.ability.speed if self.ability else 140.0)

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
        if self.ability is not None and self.kind != 'teleport' and not body.airborne \
                and not body.held and self.air <= 0:
            self.ability = None                 # trip over
        return None

    def _done_teleport(self):
        self._target_x = None
        self.ability = None
