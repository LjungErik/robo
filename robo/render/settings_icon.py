"""The settings icon: Robo's face with a little gear tucked in the corner.

Used for the settings window (title bar / taskbar) and the "Settings…"
entry in the right-click menu. Toolkit-free: it just draws with cairo.
"""
import math

import cairo

from robo.core.pose import Pose

from .robot import draw_robot
from .shapes import INK, WHITE, circle, hexc, paint

GEAR_COLOR = hexc('#FFD54F')

# the part of the robot's design space that holds his head, ears and antenna
_HEAD_CX, _HEAD_CY, _HEAD_SPAN = 0.0, -92.0, 96.0
_CHIN = -53.0                        # below this is his neck and body


def draw_gear(cr, cx, cy, r, teeth=8, angle=0.0, color=GEAR_COLOR, hole=WHITE, width=2.2):
    """A cartoon gear with an outlined hub hole."""
    cr.save()
    cr.translate(cx, cy)
    cr.rotate(angle)
    cr.new_path()
    step = math.pi / teeth
    for i in range(teeth * 2):
        cr.arc(0, 0, r if i % 2 == 0 else r * 0.78, i * step, (i + 1) * step)
    cr.close_path()
    paint(cr, color, INK, width)
    circle(cr, 0, 0, r * 0.32)
    paint(cr, hole, INK, width * 0.9)
    cr.restore()


def draw_settings_icon(cr, size, skin='', t=0.3):
    """Draw the icon into a `size` x `size` box at the current origin."""
    cr.save()
    k = size / _HEAD_SPAN
    cr.save()
    cr.scale(k, k)
    cr.translate(_HEAD_SPAN / 2 - _HEAD_CX, _HEAD_SPAN / 2 - _HEAD_CY)
    cr.rectangle(-_HEAD_SPAN, _CHIN - 2 * _HEAD_SPAN, 2 * _HEAD_SPAN, 2 * _HEAD_SPAN)
    cr.clip()
    cr.push_group()
    draw_robot(cr, Pose(t=t, skin=skin, mood='happy'))
    cr.pop_group_to_source()
    cr.paint()
    cr.restore()
    r = size * 0.21
    draw_gear(cr, size - r - size * 0.01, size - r - size * 0.01, r, teeth=8,
              angle=t * 0.6, width=max(1.0, size / 28))
    cr.restore()


def settings_icon_surface(size, skin=''):
    """An ARGB cairo surface holding the icon."""
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    cr = cairo.Context(surface)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    draw_settings_icon(cr, size, skin)
    surface.flush()
    return surface
