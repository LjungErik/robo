r"""Layout of the robot's window, in design units (multiply by scale for pixels).

    +-----------------------------+  0
    |      ( speech bubble )      |
    |             \/              |  ~84
    |            o  antenna       |  (room for hats and helmets)
    |         [ robot ]           |
    |___________/  \______________|  WINDOW_H  (feet FOOT_PAD above)
"""
from .geometry import Bounds, Rect

WINDOW_W, WINDOW_H = 170, 252
FOOT_PAD = 8                              # feet stand this far above the window bottom
GROUND_X, GROUND_Y = WINDOW_W / 2, WINDOW_H - FOOT_PAD

BUBBLE = Rect(39, 6, 92, 68)
BUBBLE_RADIUS = 20
BUBBLE_TAIL = 10                          # tail tip is at (GROUND_X, BUBBLE bottom + tail)

ROBOT_TOP = GROUND_Y - 178                # tip of the tallest hat (wizard) + antenna
ROBOT_HITBOX = Rect(GROUND_X - 48, ROBOT_TOP, 96, WINDOW_H - ROBOT_TOP)
BUBBLE_HITBOX = Rect(BUBBLE.x, BUBBLE.y, BUBBLE.w, BUBBLE.h + BUBBLE_TAIL)

WALK_MARGIN = 40                          # keep the robot's centre this far from screen edges


def window_size(scale):
    return int(round(WINDOW_W * scale)), int(round(WINDOW_H * scale))


def click_regions(scale, bubble_visible):
    """Window-local rectangles (pixels) that should catch the mouse."""
    rects = [ROBOT_HITBOX.scaled(scale)]
    if bubble_visible:
        rects.append(BUBBLE_HITBOX.scaled(scale))
    return rects


def walk_bounds(workarea, scale):
    """Turn the screen's work area into the robot's walking Bounds."""
    margin = WALK_MARGIN * scale
    _, h = window_size(scale)
    return Bounds(min_x=workarea.x + margin,
                  max_x=workarea.x + workarea.w - margin,
                  ground_y=workarea.y + workarea.h - h)
