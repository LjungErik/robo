"""Pictures for Robo's popups: Robo himself, with a badge saying what it's about.

    'lock'    asking permission (a padlock, shackle open, with a little key)
    'review'  checking his changes (a magnifying glass)
    'done'    finished (a green tick and sparkles)

Toolkit-free like settings_icon.py: it just draws with cairo.
"""
import math

import cairo

from robo.core.pose import Pose

from .robot import draw_robot
from .shapes import GREEN, INK, WHITE, YELLOW, circle, hexc, paint, rrect

# the robot's whole body in design space (ground point at 0, 0)
_TOP, _BOTTOM, _HALF_WIDTH = -128.0, 8.0, 68.0

LOCK_BODY = hexc('#FFC93C')
LOCK_DARK = hexc('#E0A100')
GLASS = hexc('#BFE9FF', 0.85)
SPARKLE = hexc('#FFD23F')

POSES = {
    '': dict(mood='happy', arms='wave'),
    'lock': dict(mood='surprised', arms='wave', antenna='alert'),
    'review': dict(mood='normal', arms='rest', look=0.6),
    'done': dict(mood='happy', arms='up'),
}


def draw_lock(cr, cx, cy, s):
    """A padlock with its shackle popped open and a key beside it. `s` = its height."""
    w, h = s * 0.78, s * 0.55
    x, y = cx - w / 2, cy - h / 2 + s * 0.15
    lw = max(1.2, s / 18)
    # the shackle, lifted up on the right: "may I open this?"
    cr.new_path()
    r = w * 0.3
    cr.move_to(cx - r, y + 1)
    cr.line_to(cx - r, y - r * 0.6)
    cr.arc(cx, y - r * 0.6, r, math.pi, 2 * math.pi)
    cr.line_to(cx + r, y - r * 0.6 + r * 0.25)
    paint(cr, None, INK, lw * 2.4)
    cr.move_to(cx - r, y + 1)
    cr.line_to(cx - r, y - r * 0.6)
    cr.arc(cx, y - r * 0.6, r, math.pi, 2 * math.pi)
    cr.line_to(cx + r, y - r * 0.6 + r * 0.25)
    paint(cr, None, hexc('#C9CED9'), lw * 1.1)
    # the body
    rrect(cr, x, y, w, h, s * 0.09)
    paint(cr, LOCK_BODY, INK, lw)
    rrect(cr, x + w * 0.08, y + h * 0.62, w * 0.84, h * 0.22, s * 0.04)
    paint(cr, LOCK_DARK, None)
    # keyhole, with a cheeky face around it
    circle(cr, cx, y + h * 0.42, s * 0.07)
    paint(cr, INK, None)
    cr.move_to(cx - s * 0.03, y + h * 0.45)
    cr.line_to(cx + s * 0.03, y + h * 0.45)
    cr.line_to(cx + s * 0.045, y + h * 0.72)
    cr.line_to(cx - s * 0.045, y + h * 0.72)
    cr.close_path()
    paint(cr, INK, None)
    for ex in (-1, 1):
        circle(cr, cx + ex * w * 0.3, y + h * 0.33, s * 0.035)
        paint(cr, INK, None)
    # a little key dangling off the side
    kx, ky = x + w + s * 0.02, y + h * 0.7
    cr.save()
    cr.translate(kx, ky)
    cr.rotate(0.5)
    circle(cr, 0, 0, s * 0.11)
    paint(cr, YELLOW, INK, lw * 0.8)
    circle(cr, 0, 0, s * 0.04)
    paint(cr, WHITE, INK, lw * 0.6)
    cr.move_to(s * 0.11, 0)
    cr.line_to(s * 0.36, 0)
    cr.move_to(s * 0.27, 0)
    cr.line_to(s * 0.27, s * 0.08)
    cr.move_to(s * 0.33, 0)
    cr.line_to(s * 0.33, s * 0.06)
    paint(cr, None, INK, lw * 1.1)
    cr.restore()


def draw_magnifier(cr, cx, cy, s):
    lw = max(1.2, s / 16)
    r = s * 0.3
    gx, gy = cx - s * 0.08, cy - s * 0.08
    cr.move_to(gx + r * 0.7, gy + r * 0.7)
    cr.line_to(cx + s * 0.42, cy + s * 0.42)
    paint(cr, None, INK, lw * 3.2)
    cr.move_to(gx + r * 0.75, gy + r * 0.75)
    cr.line_to(cx + s * 0.4, cy + s * 0.4)
    paint(cr, None, hexc('#8D6E63'), lw * 1.8)
    circle(cr, gx, gy, r)
    paint(cr, GLASS, INK, lw * 1.3)
    cr.new_path()
    cr.arc(gx, gy, r * 0.65, math.pi * 1.1, math.pi * 1.45)
    paint(cr, None, WHITE, lw)


def draw_tick(cr, cx, cy, s):
    lw = max(1.2, s / 16)
    circle(cr, cx, cy, s * 0.42)
    paint(cr, GREEN, INK, lw)
    cr.move_to(cx - s * 0.2, cy + s * 0.01)
    cr.line_to(cx - s * 0.05, cy + s * 0.16)
    cr.line_to(cx + s * 0.22, cy - s * 0.14)
    paint(cr, None, WHITE, lw * 2.2)
    for (dx, dy, k) in ((-0.55, -0.45, 0.16), (0.5, -0.5, 0.12), (0.55, 0.35, 0.09)):
        draw_sparkle(cr, cx + dx * s, cy + dy * s, s * k)


def draw_sparkle(cr, cx, cy, r):
    cr.new_path()
    for i in range(8):
        a = i * math.pi / 4
        rr = r if i % 2 == 0 else r * 0.35
        cr.line_to(cx + rr * math.sin(a), cy - rr * math.cos(a))
    cr.close_path()
    paint(cr, SPARKLE, INK, max(0.8, r / 5))


BADGES = {'lock': draw_lock, 'review': draw_magnifier, 'done': draw_tick}


def draw_popup_art(cr, size, badge='', skin='', t=0.4):
    """Robo (whole body) with `badge` in the lower right, in a `size` x `size` box."""
    cr.save()
    k = size * 0.86 / (_BOTTOM - _TOP)
    cr.save()
    cr.translate(size * 0.42, size * 0.07 - _TOP * k)
    cr.scale(k, k)
    cr.push_group()
    draw_robot(cr, Pose(t=t, skin=skin, shadow=False, **POSES.get(badge, {})))
    cr.pop_group_to_source()
    cr.paint()
    cr.restore()
    fn = BADGES.get(badge)
    if fn:
        s = size * 0.42
        fn(cr, size - s * 0.78, size - s * 0.64, s)
    cr.restore()


def popup_art_surface(size, badge='', skin=''):
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    cr = cairo.Context(surface)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    draw_popup_art(cr, size, badge, skin)
    surface.flush()
    return surface
