"""Draws one complete frame: robot, Z's, hearts and the speech bubble."""
import math

import cairo

from robo.core import layout

from .effects import draw_particles, draw_poof
from .icons import draw_icon
from .robot import draw_hearts, draw_robot, draw_zzz
from .shapes import INK, RED, WHITE, circle, paint, speech_path

ICON_SCALE = 1.15


def draw_frame(cr, scale, pose, bubble, now):
    """cr: cairo context for the whole window; bubble may be None."""
    cr.save()
    cr.set_operator(cairo.OPERATOR_SOURCE)
    cr.set_source_rgba(0, 0, 0, 0)
    cr.paint()
    cr.set_operator(cairo.OPERATOR_OVER)
    cr.scale(scale, scale)

    cr.save()
    cr.translate(layout.GROUND_X + pose.jitter, layout.GROUND_Y)
    draw_robot(cr, pose)
    if pose.zzz:
        draw_zzz(cr, pose.t, pose.facing)
    draw_hearts(cr, pose.hearts)
    draw_particles(cr, pose.particles, now)
    draw_poof(cr, pose.poof)
    cr.restore()

    if bubble is not None:
        draw_bubble(cr, bubble, now)
    cr.restore()


def draw_bubble(cr, bubble, now):
    s = bubble.scale(now)
    if s <= 0.01:
        return
    b = layout.BUBBLE
    tip_x, tip_y = layout.GROUND_X, b.y + b.h + layout.BUBBLE_TAIL
    cr.save()
    cr.translate(tip_x, tip_y)          # grow out of the tail tip
    cr.scale(s, s)
    cr.translate(-tip_x, -tip_y)

    def outline():
        speech_path(cr, b.x, b.y, b.w, b.h, layout.BUBBLE_RADIUS, tip_x, 18, layout.BUBBLE_TAIL)

    cr.save()
    cr.translate(0, 3)
    outline()
    cr.set_source_rgba(0.1, 0.12, 0.2, 0.18)   # soft shadow
    cr.fill()
    cr.restore()
    outline()
    paint(cr, WHITE, INK, 2.6)

    age = bubble.age(now)
    k = ICON_SCALE
    cx, cy = b.x + b.w / 2, b.y + b.h / 2
    cr.save()
    cr.translate(cx - 24 * k, cy - 24 * k + math.sin(age * 3) * 1.2)
    cr.scale(k, k)
    draw_icon(cr, bubble.kind, age)
    cr.restore()

    if bubble.count > 1:
        _count_badge(cr, b.x + b.w - 4, b.y + 4, bubble.count)
    cr.restore()


def _count_badge(cr, x, y, count):
    circle(cr, x, y, 10)
    paint(cr, RED, INK, 2)
    label = str(count) if count < 10 else '9+'
    cr.select_font_face('Sans', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    cr.set_font_size(11 if len(label) == 1 else 9)
    ext = cr.text_extents(label)
    cr.move_to(x - ext.width / 2 - ext.x_bearing, y - ext.height / 2 - ext.y_bearing)
    cr.set_source_rgba(*WHITE)
    cr.show_text(label)
