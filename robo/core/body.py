"""The robot's body: where he is and how he moves.

States
    IDLE   standing around until `state_until`, then asks for a new action
    WALK   walking toward `target_x`
    SLEEP  napping until `state_until`
    DRAG   held by the mouse
    FALL   dropped, falling back to the ground
    FLY    flying through the air toward (target_x, target_y)   } airborne: anywhere
    HOVER  hovering in the air until `state_until`              } on the screen, not
    HANG   hanging from the top of the screen until `state_until` } just the bottom

Body knows nothing about moods or bubbles; update() just reports what
happened ('ready', 'woke', 'landed') so the Companion can react.
"""
import math

WALK_SPEED = 42.0       # design px / s
GRAVITY = 2400.0        # design px / s²
HOP_TIME, HOP_HEIGHT = 0.6, 12.0
SQUASH_TIME, SQUASH_AMOUNT = 0.3, 0.16
STEPS_PER_SECOND = 9.0  # walk cycle speed (radians of leg phase)

IDLE, WALK, SLEEP, DRAG, FALL = 'idle', 'walk', 'sleep', 'drag', 'fall'
FLY, HOVER, HANG = 'fly', 'hover', 'hang'
AIR = (FLY, HOVER, HANG)
SLOW_DOWN = 50.0        # design px from the target where flying starts to brake


class Body:
    def __init__(self, x, y, scale, now, rng):
        self.rng = rng
        self.scale = scale
        self.x = x                 # robot centre, screen px
        self.y = y                 # window top, screen px
        self.vy = 0.0
        self.facing = rng.choice((-1, 1))
        self.state = IDLE
        self.state_until = now + rng.uniform(3, 6)
        self.target_x = x
        self.target_y = y
        self.air_speed = 0.0       # design px / s while flying
        self.air_kind = ''         # what he flies to: 'fly' (hover there) or 'hang'
        self.air_stay = (3.0, 6.0)
        self.landing = False       # this flight ends on the ground
        self.phase = 0.0           # walk cycle
        self.hop_start = -10.0
        self.squash_start = -10.0
        self.last_sleep = now

    # ------------------------------------------------------------ queries
    @property
    def held(self):
        """Being dragged or falling (legs dangling)."""
        return self.state in (DRAG, FALL)

    @property
    def on_ground(self):
        return self.state in (IDLE, WALK, SLEEP)

    @property
    def airborne(self):
        """Flying, hovering or hanging somewhere up the screen."""
        return self.state in AIR

    @property
    def cruising(self):
        return self.state == FLY

    def hop_lift(self, now):
        a = now - self.hop_start
        if not 0 <= a <= HOP_TIME:
            return 0.0
        p = a / HOP_TIME
        return abs(math.sin(p * 2 * math.pi)) * HOP_HEIGHT * (1 - p * 0.4)

    def squash(self, now):
        a = now - self.squash_start
        if not 0 <= a < SQUASH_TIME:
            return 0.0
        k = a / SQUASH_TIME
        return SQUASH_AMOUNT * math.sin(k * math.pi) * (1 - k)

    # ------------------------------------------------------------ actions
    def rest(self, now, lo=4.0, hi=14.0):
        """Stay put for a while (in the air too: he keeps hovering / hanging)."""
        if self.state == FLY:
            return
        if self.state not in (HOVER, HANG):
            self.state = IDLE
        self.state_until = now + self.rng.uniform(lo, hi)

    def walk_to(self, x, bounds):
        self.target_x = bounds.clamp_x(x)
        if abs(self.target_x - self.x) > 2:
            self.state = WALK
            self.facing = 1 if self.target_x > self.x else -1
            return True
        return False

    def wander(self, now, bounds, lo, hi):
        """Walk a random distance in a random direction (turning at edges)."""
        dist = self.rng.uniform(lo, hi) * self.scale
        d = self.rng.choice((-1, 1))
        if not bounds.contains_x(self.x + d * dist):
            d = -d
        if not self.walk_to(self.x + d * dist, bounds):
            self.rest(now, 2, 5)

    def turn_around(self):
        self.facing = -self.facing

    def sleep(self, now, seconds):
        self.state = SLEEP
        self.state_until = now + seconds
        self.last_sleep = now

    def wake(self, now):
        """Returns True if he was asleep."""
        if self.state == SLEEP:
            self.rest(now, 3, 6)
            return True
        return False

    def stop(self, now, lo=2, hi=5):
        """Stand still (used when something needs his attention)."""
        if self.state in (WALK, IDLE, HOVER, HANG):
            self.rest(now, lo, hi)

    # ------------------------------------------------------------ in the air
    def fly_to(self, x, y, speed, bounds, kind='fly', stay=(3.0, 6.0), landing=False):
        """Fly (in a straight line) to a point anywhere on the screen."""
        self.target_x = bounds.clamp_x(x)
        self.target_y = bounds.clamp_y(y)
        self.air_speed, self.air_kind, self.air_stay = speed, kind, stay
        self.landing = landing
        self.state = FLY
        if abs(self.target_x - self.x) > 2:
            self.facing = 1 if self.target_x > self.x else -1

    def land(self, bounds, speed=140.0):
        """Come back down: fly to the ground, or let go of the thread."""
        if self.state == HANG:
            self.state, self.vy = FALL, 0.0
        elif self.airborne:
            self.fly_to(self.x, bounds.ground_y, self.air_speed or speed, bounds, landing=True)

    def hover(self, now, lo, hi, kind='fly'):
        """Stay in the air right where he is."""
        self.state = HANG if kind == 'hang' else HOVER
        self.air_kind = kind
        self.state_until = now + self.rng.uniform(lo, hi)

    def teleport(self, x, bounds):
        """Vanish here, appear there (on the ground)."""
        self.x, self.y = bounds.clamp_x(x), bounds.ground_y
        self.target_x = self.x

    def hop(self, now, delay=0.0):
        if self.on_ground:
            self.hop_start = now + delay

    # ------------------------------------------------------------ dragging
    def grab(self, now):
        self.wake(now)
        self.state = DRAG

    def drag_to(self, x, y):
        self.x, self.y = x, y

    def drop(self, now, bounds):
        if self.y < bounds.ground_y - 1:
            self.state = FALL
            self.vy = 0.0
        else:
            self.y = bounds.ground_y
            self.rest(now, 2, 5)
            self.walk_to(self.x, bounds)

    # ------------------------------------------------------------ simulation
    def update(self, now, dt, bounds, speed_factor=1.0):
        """Advance one frame. Returns 'ready', 'woke', 'landed' or None."""
        if self.state == WALK:
            step = WALK_SPEED * self.scale * dt * speed_factor
            diff = self.target_x - self.x
            if abs(diff) <= step:
                self.x = self.target_x
                self.rest(now)
            else:
                self.facing = 1 if diff > 0 else -1
                self.x += self.facing * step
                self.phase += dt * STEPS_PER_SECOND
        elif self.state == IDLE or self.state in (HOVER, HANG):
            if now >= self.state_until:
                return 'ready'
        elif self.state == FLY:
            return self._fly(now, dt, bounds)
        elif self.state == SLEEP:
            if now >= self.state_until:
                self.wake(now)
                return 'woke'
        elif self.state == FALL:
            self.vy += GRAVITY * self.scale * dt
            self.y += self.vy * dt
            if self.y >= bounds.ground_y:
                self.y = bounds.ground_y
                self.vy = 0.0
                self.squash_start = now
                self.rest(now, 2, 5)
                if not bounds.contains_x(self.x):
                    self.walk_to(self.x, bounds)
                return 'landed'
        return None

    def _fly(self, now, dt, bounds):
        dx, dy = self.target_x - self.x, self.target_y - self.y
        dist = math.hypot(dx, dy)
        brake = max(0.3, min(1.0, dist / (SLOW_DOWN * self.scale)))
        step = self.air_speed * self.scale * dt * brake
        if dist > step:
            self.x += dx / dist * step
            self.y += dy / dist * step
            if abs(dx) > 1:
                self.facing = 1 if dx > 0 else -1
            return None
        self.x, self.y = self.target_x, self.target_y
        if self.landing or self.y >= bounds.ground_y - 0.5:
            self.y = bounds.ground_y
            self.squash_start = now
            self.landing = False
            self.air_kind = ''
            self.state = IDLE
            self.rest(now, 2, 5)
            return 'landed'
        self.hover(now, *self.air_stay, kind=self.air_kind)
        return 'arrived'

    def settle(self, now, bounds):
        """Called when the screen layout may have changed."""
        if self.airborne:
            self.x = bounds.clamp_x(self.x)
            self.y = bounds.clamp_y(self.y)
            if self.state == HANG:
                self.y = bounds.min_y          # still hanging from the top edge
        if self.on_ground:
            self.y = bounds.ground_y
            if not bounds.contains_x(self.x) and self.state != WALK:
                self.walk_to(self.x, bounds)
