"""Tiny geometry types shared by the core and the platforms."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    w: float
    h: float

    def contains(self, px, py):
        return self.x <= px < self.x + self.w and self.y <= py < self.y + self.h

    def scaled(self, s):
        return Rect(int(self.x * s), int(self.y * s), int(self.w * s), int(self.h * s))


@dataclass(frozen=True)
class Bounds:
    """Where the robot may walk, in screen pixels.

    min_x/max_x limit the robot's centre; ground_y is the window's top
    edge when the robot stands on the floor.
    """
    min_x: float
    max_x: float
    ground_y: float

    def clamp_x(self, x):
        return min(max(x, self.min_x), self.max_x)

    def contains_x(self, x):
        return self.min_x <= x <= self.max_x
