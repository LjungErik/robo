"""Evil mode: after a while without user input the robot turns evil.

EvilMode only decides *when* to switch and how far the look has blended;
what the robot does about it lives in robo.core.personality.
"""
TO_EVIL_SECONDS = 0.8        # colour fade durations
TO_GOOD_SECONDS = 0.45
GLITCH_TO_EVIL = 0.9         # flicker durations
GLITCH_TO_GOOD = 0.5
GLITCH_FLICKER = 0.35        # chance per frame to show the "other" look while glitching


class EvilMode:
    def __init__(self, after_seconds, is_inhibited=lambda: False):
        self.after = after_seconds
        self.is_inhibited = is_inhibited   # e.g. a video player keeps the screen awake
        self.active = False
        self.blend = 0.0                   # 0 = good look, 1 = evil look
        self.glitch_until = 0.0
        self.last_idle = 0.0

    @property
    def enabled(self):
        return self.after > 0

    def on_idle(self, seconds, now, may_turn_evil=True):
        """Feed the user's idle time. Returns 'evil', 'good' or None.
        may_turn_evil=False keeps him good for now (e.g. he's working on a task)."""
        if not self.enabled:
            return None
        change = None
        if not self.active:
            if seconds >= self.after and may_turn_evil and not self.is_inhibited():
                self.active = True
                self.glitch_until = now + GLITCH_TO_EVIL
                change = 'evil'
        elif seconds < self.last_idle or seconds < 1.0:   # idle timer reset: user is back
            self.active = False
            self.glitch_until = now + GLITCH_TO_GOOD
            change = 'good'
        self.last_idle = seconds
        return change

    def calm_down(self, now):
        """Turn good right away. Returns 'good' if he was evil."""
        if not self.active:
            return None
        self.active = False
        self.glitch_until = now + GLITCH_TO_GOOD
        return 'good'

    def set_after(self, after_seconds, now):
        """Change the delay live. Returns 'good' if this switched evil mode off."""
        self.after = after_seconds
        if not self.enabled and self.active:
            self.active = False
            self.glitch_until = now + GLITCH_TO_GOOD
            return 'good'
        return None

    def update(self, dt):
        if self.active:
            self.blend = min(1.0, self.blend + dt / TO_EVIL_SECONDS)
        else:
            self.blend = max(0.0, self.blend - dt / TO_GOOD_SECONDS)

    def glitching(self, now):
        return now < self.glitch_until

    def visible_blend(self, now, rng):
        """The blend to draw this frame, flickering while glitching."""
        if self.glitching(now) and rng.random() < GLITCH_FLICKER:
            return 1.0 - self.blend
        return self.blend
