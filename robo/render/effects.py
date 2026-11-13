"""Little flying things (numbers, music notes, sparks) and the costume poof.

Each particle kind comes from a character file (`particles:`): it picks one
of the glyphs drawn here, or brings its own drawing (`draw:`).
"""
import math

import cairo

from robo.design import REGISTRY

from .interpreter import safe_draw
from .shapes import INK, PINK, WHITE, YELLOW, circle, ellipse, heart_path, hexc, paint, sparkle

NUMBER_COLOURS = (hexc('#2F9E5B'), hexc('#3D6FD9'), hexc('#E5484D'))
NOTE = hexc('#FF7AB6')
STAR = hexc('#FFE27A')
MAGIC = (hexc('#B98CFF'), hexc('#FF7AB6'), hexc('#7DF3FF'), hexc('#FFD23F'))
NO_PALETTE = {'_palette': {}, 'evil': 0.0}


def _colour(em, pt, default):
    if em is not None and em.colours:
        c = em.colours[pt.index % len(em.colours)]
        return c(NO_PALETTE) if c else default[pt.index % len(default)]
    return default[pt.index % len(default)]


def draw_particles(cr, particles, now):
    """Particles are in robot coordinates (origin = ground point)."""
    for pt in particles:
        age = now - pt.born
        k = age / pt.life if pt.life > 0 else 1
        if not 0 <= k < 1:
            continue
        x, y = pt.x + pt.vx * age, pt.y + pt.vy * age
        alpha = 1 - k * k
        em = REGISTRY.emitter(pt.kind) if pt.kind else None
        cr.save()
        cr.push_group()
        if em is not None and em.draw is not None:
            env = dict(NO_PALETTE, x=x, y=y, k=k, age=age, i=pt.index, glyph=pt.glyph)
            safe_draw(em.draw, cr, env, f'particles {pt.kind}')
        elif pt.glyph == 'note':
            _note(cr, x, y + math.sin(age * 8) * 2)
        elif pt.glyph == 'spark':
            sparkle(cr, x, y, 4.5 * (1 - k) + 1.5, YELLOW)
        elif pt.glyph == 'star':
            sparkle(cr, x, y, 4 * math.sin(k * math.pi) + 0.5, STAR)
        elif pt.glyph == 'magic':
            sparkle(cr, x, y, 5 * (1 - k) + 1.5, _colour(em, pt, MAGIC))
        elif pt.glyph == 'heart':
            heart_path(cr, x, y, 0.32)
            paint(cr, PINK, INK, 1.4)
        else:
            cr.select_font_face('Sans', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            cr.set_font_size(10 + k * 3)
            col = _colour(em, pt, NUMBER_COLOURS)
            cr.move_to(x, y)
            cr.text_path(pt.glyph)
            paint(cr, col, WHITE, 2.5)
            cr.move_to(x, y)
            cr.text_path(pt.glyph)
            paint(cr, col, None)
        cr.pop_group_to_source()
        cr.paint_with_alpha(alpha)
        cr.restore()


def _note(cr, x, y):
    cr.move_to(x + 2.6, y)
    cr.line_to(x + 2.6, y - 10)
    cr.line_to(x + 7, y - 8)
    paint(cr, None, INK, 1.8)
    ellipse(cr, x, y, 3.2, 2.5)
    paint(cr, NOTE, INK, 1.5)


def draw_poof(cr, progress):
    """A puff of smoke around the robot while he changes clothes (0..1)."""
    if progress is None:
        return
    k = progress
    grow = math.sin(min(1.0, k * 1.6) * math.pi / 2)
    alpha = 1.0 if k < 0.55 else max(0.0, 1 - (k - 0.55) / 0.45)
    cr.save()
    cr.push_group()
    for i in range(9):
        a = i / 9 * 2 * math.pi + k * 1.5
        r = 18 + grow * 26
        cx, cy = math.cos(a) * r * 1.1, -70 + math.sin(a) * r
        circle(cr, cx, cy, 12 + grow * 8 - (i % 3) * 2)
        paint(cr, (0.97, 0.97, 1.0, 1), (0.75, 0.78, 0.88, 1), 2)
    circle(cr, 0, -70, 10 + grow * 30)
    paint(cr, (0.97, 0.97, 1.0, 1), None)
    cr.pop_group_to_source()
    cr.paint_with_alpha(alpha * 0.95)
    cr.restore()
    for i in range(4):
        a = i * math.pi / 2 + 0.6 + k * 2
        r = 30 + k * 40
        sparkle(cr, math.cos(a) * r, -70 + math.sin(a) * r, 6 * (1 - k), YELLOW)
