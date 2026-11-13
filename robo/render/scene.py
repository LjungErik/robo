"""Draws one complete frame: robot, Z's, hearts and the speech bubble."""
import math

import cairo

from robo.core import layout

from .effects import draw_particles, draw_poof
from .icons import draw_icon
from .robot import draw_hearts, draw_robot, draw_zzz
from .shapes import INK, RED, WHITE, circle, paint, speech_path

ICON_SCALE = 1.15


def draw_frame(cr, scale, pose, bubble, now, offset=0.0):
    """cr: cairo context for the whole window; bubble may be None. `offset` (design
    px) moves everything down: the window is a tall column while a web is out."""
    cr.save()
    cr.set_operator(cairo.OPERATOR_SOURCE)
    cr.set_source_rgba(0, 0, 0, 0)
    cr.paint()
    cr.set_operator(cairo.OPERATOR_OVER)
    cr.scale(scale, scale)

    cr.save()
    cr.translate(layout.GROUND_X + pose.jitter, layout.GROUND_Y + offset)
    draw_robot(cr, pose)
    if pose.zzz:
        draw_zzz(cr, pose.t, pose.facing)
    draw_hearts(cr, pose.hearts)
    draw_particles(cr, pose.particles, now)
    draw_poof(cr, pose.poof)
    if pose.seeing:
        draw_seeing_badge(cr, pose)
    cr.restore()

    if bubble is not None:
        cr.save()
        cr.translate(0, layout.bubble_offset(offset))
        draw_bubble(cr, bubble, now)
        cr.restore()
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


def draw_seeing_badge(cr, pose):
    """You're showing him your screen: a pulsing red eye beside his head, so you can
    tell at a glance that he's looking (the red border around the screen says what)."""
    pulse = 0.5 + 0.5 * math.sin(pose.t * 3.2)
    x, y = 40, -118 - pose.lift
    cr.save()
    cr.set_source_rgba(0.93, 0.16, 0.22, 0.22 * pulse)          # soft halo
    circle(cr, x, y, 17 + 5 * pulse)
    cr.fill()
    circle(cr, x, y, 13)
    paint(cr, RED, INK, 2.2)
    cr.new_path()                                               # an eye: almond + pupil
    cr.move_to(x - 8, y)
    cr.curve_to(x - 4, y - 6, x + 4, y - 6, x + 8, y)
    cr.curve_to(x + 4, y + 6, x - 4, y + 6, x - 8, y)
    cr.close_path()
    paint(cr, WHITE, None)
    circle(cr, x, y, 2.6 + 0.6 * pulse)
    paint(cr, INK, None)
    cr.restore()
