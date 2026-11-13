"""The robot's face and gestures: blinking, glancing and short expressions.

Expressions are simple timers: `face.show(HAPPY, now, 1.4)` keeps him
happy for 1.4 s, `face.active(HAPPY, now)` asks whether he still is.
"""
BLINK_TIME = 0.16

# Timed expressions / gestures
SURPRISED = 'surprised'
HAPPY = 'happy'
WAVE = 'wave'
ARMS_UP = 'arms_up'
LAUGH = 'laugh'          # evil laugh
SWEAT = 'sweat'          # "oops, you caught me"
LOOK_MOVE = 'look_move'  # his everyday look's signature move (when that look is a character)
YAWN = 'yawn'            # sleepy
GIGGLE = 'giggle'        # picked up and loving it
GRUMPY = 'grumpy'        # picked up and not in the mood
SAD = 'sad'              # hurt feelings / lonely
HOBBY = 'hobby'          # busy with a pastime (Face.hobby says which)
FOLLOW_SECONDS = 2.5     # after the pointer stops moving he keeps watching it this long

HEART_LIFETIME = 1.5


class Face:
    def __init__(self, now, rng):
        self.rng = rng
        self.next_blink = now + 2
        self.blink_start = -10.0
        self.look = 0.0
        self.look_target = 0.0
        self.next_glance = now + 3
        self.look_y = 0.0
        self.look_y_target = 0.0
        self.hobby = ''
        self._follow_until = -1.0
        self._pointer = None
        self._until = {}
        self._hearts = []

    # ------------------------------------------------------------ timers
    def show(self, expression, now, seconds):
        self._until[expression] = now + seconds

    def clear(self, expression):
        self._until.pop(expression, None)

    def active(self, expression, now):
        return now < self._until.get(expression, 0.0)

    # ------------------------------------------------------------ hearts
    def add_hearts(self, now, delays):
        self._hearts.extend(now + d for d in delays)

    def heart_ages(self, now):
        return [now - h for h in self._hearts]

    # ------------------------------------------------------------ animation
    def update(self, now, dt):
        rng = self.rng
        if now >= self.next_blink:
            self.blink_start = now
            double = rng.random() < 0.2
            self.next_blink = now + (0.35 if double else rng.uniform(2.5, 6))
        if now < self._follow_until:
            pass                                  # watching your mouse pointer
        elif now >= self.next_glance:
            self.look_target = rng.choice((0, 0, -3, 3, -2, 2))
            self.look_y_target = 0.0
            self.next_glance = now + rng.uniform(1.5, 5)
        self.look += (self.look_target - self.look) * min(1.0, dt * 8)
        self.look_y += (self.look_y_target - self.look_y) * min(1.0, dt * 8)
        self._hearts = [h for h in self._hearts if now - h < HEART_LIFETIME]

    def follow(self, now, dx, dy, facing):
        """Your pointer is at (dx, dy) screen px from his face: look at it, if it
        moved and isn't too far away."""
        moved = self._pointer is None or abs(dx - self._pointer[0]) + abs(dy - self._pointer[1]) > 3
        self._pointer = (dx, dy)
        if not moved or abs(dx) > 900 or abs(dy) > 700:
            return
        self._follow_until = now + FOLLOW_SECONDS
        self.look_target = max(-3.2, min(3.2, dx * facing / 60))   # eyes are mirrored too
        self.look_y_target = max(-2.6, min(2.6, dy / 80))

    def openness(self, now):
        """1 = eyes open, 0 = closed (mid-blink)."""
        b = now - self.blink_start
        if 0 <= b < BLINK_TIME:
            return abs(1 - 2 * (b / BLINK_TIME))
        return 1.0
