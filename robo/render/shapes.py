"""Colours and small Cairo drawing helpers shared by the robot and the icons."""
import math


def hexc(h, a=1.0):
    h = h.lstrip('#')
    return (int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255, a)


INK = hexc('#3B4060')
WHITE = hexc('#FFFFFF')
RED = hexc('#FF5A64')
GREEN = hexc('#43D17A')
YELLOW = hexc('#FFD23F')
BLUE = hexc('#4DA8FF')
ORANGE = hexc('#FFA94D')
PINK = hexc('#FF7AB6')
PURPLE = hexc('#9B87FF')
GREY = hexc('#B4BACB')
CARD = hexc('#F6C27A')
SKY = hexc('#8FD8FF')
CREAM = hexc('#FFF4DC')

LW = 2.6
TAU = 2 * math.pi


# ---------------------------------------------------------------- helpers
def rrect(cr, x, y, w, h, r):
    r = min(r, w / 2, h / 2)
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
    cr.close_path()


def ellipse(cr, cx, cy, rx, ry):
    cr.save()
    cr.translate(cx, cy)
    cr.scale(rx, ry)
    cr.new_sub_path()
    cr.arc(0, 0, 1, 0, TAU)
    cr.restore()


def circle(cr, cx, cy, r):
    cr.new_sub_path()
    cr.arc(cx, cy, r, 0, TAU)


def paint(cr, fill=None, stroke=INK, lw=LW):
    """Fill and/or stroke the current path."""
    if fill is not None:
        cr.set_source_rgba(*fill)
        if stroke is not None:
            cr.fill_preserve()
        else:
            cr.fill()
    if stroke is not None:
        cr.set_source_rgba(*stroke)
        cr.set_line_width(lw)
        cr.stroke()


def line(cr, pts, color=INK, lw=LW):
    cr.move_to(*pts[0])
    for p in pts[1:]:
        cr.line_to(*p)
    paint(cr, None, color, lw)


def outlined_stroke(cr, path_fn, color, inner=4.5, outer=8.0):
    """Stroke a path twice: thick ink outline, then colour on top."""
    path_fn()
    paint(cr, None, INK, outer)
    path_fn()
    paint(cr, None, color, inner)


def sparkle(cr, x, y, r, color=YELLOW):
    cr.move_to(x, y - r)
    cr.curve_to(x, y, x, y, x + r, y)
    cr.curve_to(x, y, x, y, x, y + r)
    cr.curve_to(x, y, x, y, x - r, y)
    cr.curve_to(x, y, x, y, x, y - r)
    cr.close_path()
    paint(cr, color, None)


def speech_path(cr, x, y, w, h, r, tail_x, tail_w, tail_h):
    """Rounded rectangle with a little tail on its bottom edge, as ONE path."""
    cr.new_path()
    cr.move_to(x + r, y)
    cr.line_to(x + w - r, y)
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.line_to(x + w, y + h - r)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.line_to(tail_x + tail_w / 2, y + h)
    cr.line_to(tail_x, y + h + tail_h)
    cr.line_to(tail_x - tail_w / 2, y + h)
    cr.line_to(x + r, y + h)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.line_to(x, y + r)
    cr.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
    cr.close_path()


def heart_path(cr, cx, cy, s=1.0):
    cr.save()
    cr.translate(cx, cy)
    cr.scale(s, s)
    cr.move_to(0, 14)
    cr.curve_to(-16, 4, -18, -8, -10, -12)
    cr.curve_to(-5, -15, -1, -12, 0, -7)
    cr.curve_to(1, -12, 5, -15, 10, -12)
    cr.curve_to(18, -8, 16, 4, 0, 14)
    cr.close_path()
    cr.restore()


