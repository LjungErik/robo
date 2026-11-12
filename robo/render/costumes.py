"""Outfits Robo can dress up in.

An Outfit is a set of optional layer functions that draw_robot() calls at
the right moment (all drawn in the robot's coordinates, +x = the way he faces):

    behind(cr, p)        behind arms and body       capes
    body(cr, p)          on top of the body          collars, ties, overalls
    behind_head(cr, p)   behind the head             headdress flaps
    face(cr, p)          on the face screen          glasses, beards
    head(cr, p)          on top of the head          hats, helmets
    front(cr, p)         in front of everything      toys
    front_hand(cr, angle, p) / back_hand(...)       props, drawn at the hand
                         (cr is in arm coordinates; cr.rotate(-angle) = upright)
    antenna_y            where the antenna sticks out (top of the hat)

To add a costume: write its layers, add an Outfit to OUTFITS, and add a
Character with the same id to robo.core.characters.
"""
import math
from dataclasses import dataclass

import cairo
from typing import Callable, Optional

from .anatomy import HEAD_TOP
from .shapes import (INK, WHITE, circle, ellipse, hexc, outlined_stroke, paint, rrect)

GOLD = hexc('#F5C542')
LAPIS = hexc('#3D6FD9')
SNAKE_RED = hexc('#E2474F')
HAT_BROWN = hexc('#B5733E')
DARK_BROWN = hexc('#7A4A28')
ROPE = hexc('#D9A55B')
BANDANA = hexc('#E5484D')
STEEL = hexc('#C3CCDD')
BRONZE = hexc('#D49A3A')
HORN = hexc('#F4E6C4')
BEARD = hexc('#F29A4A')
WOOD = hexc('#B9824A')
VISOR = (0.36, 0.80, 0.52, 0.85)
VISOR_BAND = hexc('#2F9E5B')
TIE = hexc('#4769D6')
CALC = hexc('#8C93A8')
CALC_SCREEN = hexc('#B6F0A8')
CAP_RED = hexc('#E5484D')
DENIM = hexc('#5B8BE0')
DENIM_DARK = hexc('#4673C4')
TOGA = hexc('#FBF6EA')
ROMAN_PURPLE = hexc('#8B4FD8')
CAPE = hexc('#D93B48')
LEAF = hexc('#6CC56B')


@dataclass(frozen=True)
class Outfit:
    behind: Optional[Callable] = None
    body: Optional[Callable] = None
    behind_head: Optional[Callable] = None
    face: Optional[Callable] = None
    head: Optional[Callable] = None
    front_hand: Optional[Callable] = None
    back_hand: Optional[Callable] = None
    front: Optional[Callable] = None
    antenna_y: float = HEAD_TOP


NO_OUTFIT = Outfit()


def _striped(cr, path, base, stripe, step):
    """Fill `path` with horizontal stripes, then outline it."""
    cr.save()
    path()
    cr.clip()
    path()
    paint(cr, base, None)
    cr.set_source_rgba(*stripe)
    y, i = -160.0, 0
    while y < 20:
        if i % 2:
            cr.rectangle(-80, y, 160, step)
        y += step
        i += 1
    cr.fill()
    cr.restore()
    path()
    paint(cr, None, INK, 2.2)


def _upright(cr, angle):
    cr.rotate(-angle)


# ================================================================ pharaoh
def _nemes_flap(cr, side):
    cr.new_path()
    cr.move_to(side * 30, -100)
    cr.line_to(side * 40, -102)
    cr.line_to(side * 47, -56)
    cr.line_to(side * 33, -56)
    cr.close_path()


def _nemes_top(cr):
    cr.new_path()
    cr.move_to(-41, -92)
    cr.curve_to(-43, -120, -20, -126, 0, -126)
    cr.curve_to(20, -126, 43, -120, 41, -92)
    cr.line_to(34, -94)
    cr.curve_to(30, -104, 18, -107, 0, -107)
    cr.curve_to(-18, -107, -30, -104, -34, -94)
    cr.close_path()


def pharaoh_behind_head(cr, p):
    for side in (-1, 1):
        _striped(cr, lambda s=side: _nemes_flap(cr, s), GOLD, LAPIS, 4.5)


def pharaoh_head(cr, p):
    _striped(cr, lambda: _nemes_top(cr), GOLD, LAPIS, 4.5)

    def band():
        cr.new_path()
        cr.move_to(-34, -95)
        cr.curve_to(-30, -105, -18, -108, 0, -108)
        cr.curve_to(18, -108, 30, -105, 34, -95)
    outlined_stroke(cr, band, GOLD, 3.2, 6)
    ellipse(cr, 0, -111, 3.2, 4.6)          # the little cobra
    paint(cr, SNAKE_RED, INK, 1.8)
    circle(cr, 0, -112, 1.2)
    paint(cr, GOLD, None)


def pharaoh_face(cr, p):
    _striped(cr, lambda: rrect(cr, -4.5, -59, 9, 15, 3.5), GOLD, LAPIS, 3)   # false beard


def pharaoh_body(cr, p):
    def collar():
        cr.new_path()
        cr.arc(0, -54, 21, 0, math.pi)
        cr.arc_negative(0, -54, 11, math.pi, 0)
        cr.close_path()
    collar()
    paint(cr, GOLD)
    for r, col in ((14.5, LAPIS), (18, SNAKE_RED)):
        cr.new_path()
        cr.arc(0, -54, r, 0.12, math.pi - 0.12)
        paint(cr, None, col, 2.2)


def crook(cr, angle, p):
    _upright(cr, angle)

    def path():
        cr.new_path()
        cr.move_to(0, 9)
        cr.line_to(0, -24)
        cr.arc(5, -24, 5, math.pi, 2 * math.pi)
        cr.line_to(10, -21)
    outlined_stroke(cr, path, GOLD, 3.2, 6)
    for y in (-2, -10, -18):
        cr.move_to(-1.6, y)
        cr.line_to(1.6, y)
        paint(cr, None, LAPIS, 2)


# ================================================================ cowboy
def cowboy_head(cr, p):
    cr.move_to(-21, -110)
    cr.curve_to(-23, -126, -19, -138, -10, -138)
    cr.curve_to(-4, -138, -2, -134, 0, -134)
    cr.curve_to(2, -134, 4, -138, 10, -138)
    cr.curve_to(19, -138, 23, -126, 21, -110)
    cr.close_path()
    paint(cr, HAT_BROWN)
    cr.rectangle(-21.5, -119, 43, 5)
    paint(cr, BANDANA, INK, 1.8)
    cr.move_to(-50, -118)
    cr.curve_to(-40, -103, 40, -103, 50, -118)
    cr.curve_to(34, -109, -34, -109, -50, -118)
    cr.close_path()
    paint(cr, HAT_BROWN)


def cowboy_face(cr, p):
    for side in (-1, 1):                    # curly moustache
        cr.move_to(0, -80)
        cr.curve_to(side * 4, -84, side * 10, -84, side * 14, -79)
        cr.curve_to(side * 10, -80.5, side * 5, -78, 0, -77)
        cr.close_path()
        paint(cr, DARK_BROWN, None)


def _star(cr, cx, cy, r):
    cr.new_path()
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.45
        cr.line_to(cx + math.cos(a) * rr, cy + math.sin(a) * rr)
    cr.close_path()


def cowboy_body(cr, p):
    cr.move_to(-17, -53)
    cr.line_to(17, -53)
    cr.line_to(0, -38)
    cr.close_path()
    paint(cr, BANDANA)
    for x, y in ((-7, -50), (5, -49), (0, -44)):
        circle(cr, x, y, 1.3)
        paint(cr, WHITE, None)
    _star(cr, 13, -40, 5.5)
    paint(cr, GOLD, INK, 1.6)


def lasso(cr, angle, p):
    _upright(cr, angle)
    if p.arms == 'lasso':
        a = p.t * 12                        # loop spinning high above the hat
        loop_x, loop_y = -12, -80

        def rope():
            cr.new_path()
            cr.move_to(0, 0)
            cr.curve_to(2, -30, loop_x + 6, -55, loop_x + math.cos(a) * 18,
                        loop_y + math.sin(a) * 5)
        outlined_stroke(cr, rope, ROPE, 2.2, 4.2)

        def loop():
            cr.new_path()
            ellipse(cr, loop_x, loop_y, 18, 5)
        outlined_stroke(cr, loop, ROPE, 2.4, 4.6)
    else:
        for r in (6.5, 4.2):                # coiled rope at his side
            def coil(r=r):
                cr.new_path()
                circle(cr, 0, 6, r)
            outlined_stroke(cr, coil, ROPE, 2.0, 3.8)


# ================================================================ viking
def viking_head(cr, p):
    for side in (-1, 1):
        cr.move_to(side * 30, -108)
        cr.curve_to(side * 44, -110, side * 50, -120, side * 50, -134)
        cr.curve_to(side * 44, -124, side * 38, -120, side * 30, -116)
        cr.close_path()
        paint(cr, HORN)
    cr.move_to(-38, -98)
    cr.curve_to(-38, -128, 38, -128, 38, -98)
    cr.close_path()
    paint(cr, STEEL)
    cr.new_path()
    cr.arc(-12, -110, 9, math.pi * 1.1, math.pi * 1.45)
    paint(cr, None, (1, 1, 1, 0.7), 2.2)
    rrect(cr, -40, -102, 80, 7, 3)
    paint(cr, BRONZE)
    for x in (-30, -15, 15, 30):
        circle(cr, x, -98.5, 1.3)
        paint(cr, INK, None)
    rrect(cr, -3, -101, 6, 13, 2)          # nose guard
    paint(cr, STEEL)


def viking_face(cr, p):
    cr.move_to(-30, -66)
    cr.curve_to(-30, -50, -16, -38, 0, -36)
    cr.curve_to(16, -38, 30, -50, 30, -66)
    cr.curve_to(22, -60, 14, -66, 8, -63)
    cr.curve_to(4, -61, -4, -61, -8, -63)
    cr.curve_to(-14, -66, -22, -60, -30, -66)
    cr.close_path()
    paint(cr, BEARD)
    for side in (-1, 1):                    # braids
        rrect(cr, side * 8 - 3, -42, 6, 12, 3)
        paint(cr, BEARD)
        cr.rectangle(side * 8 - 3.5, -35, 7, 2.5)
        paint(cr, BRONZE, None)


def axe(cr, angle, p):
    _upright(cr, angle)

    def handle():
        cr.new_path()
        cr.move_to(0, 10)
        cr.line_to(0, -22)
    outlined_stroke(cr, handle, WOOD, 3.2, 5.8)
    cr.move_to(1, -25)
    cr.curve_to(10, -31, 16, -25, 15, -13)
    cr.curve_to(11, -16, 6, -16, 1, -14)
    cr.close_path()
    paint(cr, STEEL)


def shield(cr, angle, p):
    _upright(cr, angle)
    circle(cr, 0, 0, 12.5)
    paint(cr, WOOD)
    for a in (0, math.pi / 2):
        cr.move_to(math.cos(a) * 12, math.sin(a) * 12)
        cr.line_to(-math.cos(a) * 12, -math.sin(a) * 12)
        paint(cr, None, DARK_BROWN, 1.6)
    circle(cr, 0, 0, 10.5)
    paint(cr, None, BRONZE, 2.2)
    circle(cr, 0, 0, 3.8)
    paint(cr, STEEL, INK, 1.8)


# ================================================================ accountant
def accountant_head(cr, p):
    rrect(cr, -37, -110, 74, 6, 3)
    paint(cr, VISOR_BAND)
    cr.move_to(-34, -105)
    cr.line_to(34, -105)
    cr.line_to(43, -96)
    cr.curve_to(20, -92, -20, -92, -43, -96)
    cr.close_path()
    paint(cr, VISOR)


def accountant_face(cr, p):
    lx = p.look
    for ex in (-12, 12):
        circle(cr, ex + lx, -87, 8.5)
        paint(cr, (1, 1, 1, 0.08), INK, 2.2)
        cr.new_path()
        cr.arc(ex + lx, -87, 6, math.pi * 1.15, math.pi * 1.4)
        paint(cr, None, (1, 1, 1, 0.75), 1.5)
    cr.move_to(-3.5 + lx, -88)
    cr.line_to(3.5 + lx, -88)
    paint(cr, None, INK, 2.2)


def accountant_body(cr, p):
    cr.move_to(-3, -51)
    cr.line_to(3, -51)
    cr.line_to(4.5, -34)
    cr.line_to(0, -28)
    cr.line_to(-4.5, -34)
    cr.close_path()
    paint(cr, TIE, INK, 1.8)
    rrect(cr, -3.5, -54, 7, 5, 2)
    paint(cr, TIE, INK, 1.8)
    rrect(cr, -19, -44, 8, 7, 1.5)          # pocket protector + pens
    paint(cr, WHITE, INK, 1.6)
    for x, col in ((-17, SNAKE_RED), (-14, TIE)):
        cr.move_to(x, -44)
        cr.line_to(x, -49)
        paint(cr, None, col, 2)


def calculator(cr, angle, p):
    _upright(cr, angle)
    rrect(cr, -6.5, -17, 13, 17, 2.5)
    paint(cr, CALC, INK, 1.8)
    rrect(cr, -4.5, -15, 9, 4, 1)
    paint(cr, CALC_SCREEN, None)
    for row in range(3):
        for col in range(3):
            circle(cr, -3.2 + col * 3.2, -8.5 + row * 2.7, 0.9)
            paint(cr, WHITE, None)


# ================================================================ mechanic
def mechanic_head(cr, p):
    ellipse(cr, -34, -108, 13, 3.8)        # brim, worn backwards
    paint(cr, CAP_RED)
    cr.move_to(-34, -104)
    cr.curve_to(-34, -127, 34, -127, 34, -104)
    cr.close_path()
    paint(cr, CAP_RED)
    circle(cr, 10, -113, 3.6)
    paint(cr, WHITE, INK, 1.5)


def mechanic_face(cr, p):
    ellipse(cr, -19, -70, 5, 2.4)          # oil smudge
    cr.set_source_rgba(0.2, 0.18, 0.16, 0.55)
    cr.fill()
    circle(cr, -13, -67, 1.4)
    cr.fill()


def mechanic_body(cr, p):
    for side in (-1, 1):
        def strap(s=side):
            cr.new_path()
            cr.move_to(s * 11, -49)
            cr.line_to(s * 17, -54)
        outlined_stroke(cr, strap, DENIM, 3, 5.4)
    rrect(cr, -13, -50, 26, 24, 4)
    paint(cr, DENIM)
    rrect(cr, -6, -44, 12, 8, 2)
    paint(cr, DENIM_DARK, INK, 1.6)
    cr.move_to(3, -44)
    cr.line_to(3, -49)
    paint(cr, None, GOLD, 2)
    for x in (-9.5, 9.5):
        circle(cr, x, -47, 1.8)
        paint(cr, GOLD, None)


def wrench(cr, angle, p):
    # Held along the arm, so lifting the arm swings it at his own head. Bonk.
    def handle():
        cr.new_path()
        cr.move_to(0, 2)
        cr.line_to(0, 15)
    outlined_stroke(cr, handle, STEEL, 3.4, 6)
    circle(cr, 0, 18, 4.8)
    paint(cr, STEEL)
    circle(cr, 0, 18.5, 1.9)
    paint(cr, INK, None)


# ================================================================ roman emperor
def roman_behind(cr, p):
    cr.move_to(-19, -52)
    cr.curve_to(-26, -40, -30, -24, -30, -14)
    cr.line_to(30, -14)
    cr.curve_to(30, -24, 26, -40, 19, -52)
    cr.close_path()
    paint(cr, CAPE)


def roman_body(cr, p):
    cr.move_to(-21, -53)
    cr.line_to(-9, -53)
    cr.line_to(22, -30)
    cr.line_to(22, -19)
    cr.line_to(14, -18)
    cr.close_path()
    paint(cr, TOGA)
    cr.move_to(-9, -53)
    cr.line_to(22, -30)
    paint(cr, None, ROMAN_PURPLE, 2.6)
    circle(cr, -15, -50, 2.8)
    paint(cr, GOLD, INK, 1.5)


def roman_head(cr, p):
    for i in range(11):                     # laurel wreath
        a = math.radians(205 + i * 13)
        x, y = math.cos(a) * 35, -80 + math.sin(a) * 35
        cr.save()
        cr.translate(x, y)
        cr.rotate(a + math.pi / 2 + (0.6 if i % 2 else -0.6))
        ellipse(cr, 0, 0, 6, 2.8)
        cr.restore()
        paint(cr, LEAF, INK, 1.5)


def lyre(cr, angle, p):
    _upright(cr, angle)
    for side in (-1, 1):
        def horn(s=side):
            cr.new_path()
            cr.move_to(s * 6, 0)
            cr.curve_to(s * 10, -6, s * 10, -12, s * 5, -17)
        outlined_stroke(cr, horn, GOLD, 2.6, 4.8)

    def bar():
        cr.new_path()
        cr.move_to(-7, -14)
        cr.line_to(7, -14)
    outlined_stroke(cr, bar, GOLD, 2.4, 4.4)
    for x in (-2.5, 0, 2.5):
        cr.move_to(x, -1)
        cr.line_to(x, -14)
        paint(cr, None, INK, 0.9)
    rrect(cr, -7, -2, 14, 4.5, 2)
    paint(cr, GOLD, INK, 1.8)



# ================================================================ chef
CHEF_WHITE = hexc('#FFFFFF')
PAN = hexc('#4A4F63')
PANCAKE = hexc('#F2C063')
BUTTER = hexc('#FFE98A')


def chef_head(cr, p):
    for x, y, r in ((-16, -131, 11), (16, -131, 11), (0, -138, 13)):   # puffy toque
        circle(cr, x, y, r)
        paint(cr, CHEF_WHITE)
    rrect(cr, -23, -124, 46, 13, 3)
    paint(cr, CHEF_WHITE)
    for x in (-12, 0, 12):
        cr.move_to(x, -122)
        cr.line_to(x, -113)
        paint(cr, None, hexc('#C9D1E3'), 1.6)


def chef_body(cr, p):
    rrect(cr, -22, -53, 44, 35, 11)           # chef's jacket
    paint(cr, CHEF_WHITE)
    for x in (-5.5, 5.5):
        for y in (-41, -33, -25):
            circle(cr, x, y, 1.7)
            paint(cr, hexc('#9AA2B8'), None)
    cr.move_to(-15, -53)
    cr.curve_to(-8, -44, 8, -44, 15, -53)
    cr.close_path()
    paint(cr, BANDANA)
    circle(cr, 0, -47, 3)
    paint(cr, BANDANA)


def frying_pan(cr, angle, p):
    _upright(cr, angle)

    def handle():
        cr.new_path()
        cr.move_to(0, 0)
        cr.line_to(10, -1)
    outlined_stroke(cr, handle, DARK_BROWN, 3.2, 5.8)
    ellipse(cr, 19, -1, 9.5, 3.4)
    paint(cr, PAN)
    h, spin = 0.0, 0.0
    if p.arms == 'flip':                      # up, flip, and... caught!
        k = (p.t % 1.2) / 1.2
        if k < 0.65:
            k /= 0.65
            h, spin = math.sin(k * math.pi) * 28, k * 2 * math.pi
    cr.save()
    cr.translate(19, -4.5 - h)
    cr.scale(1, max(0.25, abs(math.cos(spin))))
    ellipse(cr, 0, 0, 7.5, 2.6)
    cr.restore()
    paint(cr, PANCAKE, INK, 1.6)
    if h < 2:
        rrect(cr, 17.5, -8.5, 3.5, 2.2, 0.8)
        paint(cr, BUTTER, None)


# ================================================================ astronaut
GLASS = (0.78, 0.92, 1.0, 0.28)
SUIT_GREY = hexc('#C3CCDD')


def astronaut_behind(cr, p):
    rrect(cr, -31, -57, 15, 34, 4)            # backpack
    paint(cr, SUIT_GREY)
    circle(cr, -24, -48, 2)
    paint(cr, SNAKE_RED, None)


def astronaut_body(cr, p):
    ellipse(cr, 0, -53, 21, 4.5)              # neck ring
    paint(cr, SUIT_GREY)
    rrect(cr, -10, -46, 20, 13, 3)
    paint(cr, hexc('#E7ECF5'), INK, 1.8)
    for x, col in ((-5, SNAKE_RED), (0, GOLD), (5, LAPIS)):
        circle(cr, x, -39.5, 2)
        paint(cr, col, None)
    rrect(cr, 12, -46, 8, 6, 1)               # mission patch
    paint(cr, LAPIS, INK, 1.4)
    cr.move_to(13, -43)
    cr.line_to(19, -43)
    paint(cr, None, WHITE, 1.4)


def astronaut_head(cr, p):
    circle(cr, 0, -84, 45)                    # glass bubble helmet
    paint(cr, GLASS, INK, 2.4)
    cr.new_path()
    cr.arc(0, -84, 38, math.pi * 1.12, math.pi * 1.42)
    paint(cr, None, (1, 1, 1, 0.85), 3.2)
    circle(cr, 27, -112, 2.2)
    paint(cr, (1, 1, 1, 0.85), None)


# ================================================================ wizard
WIZARD_PURPLE = hexc('#7B5CD6')
BEARD_WHITE = hexc('#F7F7FA')


def wizard_head(cr, p):
    cr.move_to(-27, -112)
    cr.curve_to(-20, -128, -8, -146, 2, -160)
    cr.curve_to(8, -140, 20, -126, 27, -112)
    cr.close_path()
    paint(cr, WIZARD_PURPLE)
    ellipse(cr, 0, -111, 44, 7)
    paint(cr, WIZARD_PURPLE)
    cr.move_to(-26, -116)
    cr.curve_to(-10, -120, 10, -120, 26, -116)
    paint(cr, None, GOLD, 3)
    _star(cr, -5, -132, 4.5)
    paint(cr, GOLD, INK, 1.3)
    _star(cr, 8, -124, 3)
    paint(cr, GOLD, None)
    circle(cr, -3, -146, 1.6)
    paint(cr, GOLD, None)


def wizard_face(cr, p):
    cr.move_to(-27, -66)
    cr.curve_to(-28, -46, -12, -26, 0, -20)
    cr.curve_to(12, -26, 28, -46, 27, -66)
    cr.curve_to(18, -61, 9, -65, 0, -63)
    cr.curve_to(-9, -65, -18, -61, -27, -66)
    cr.close_path()
    paint(cr, BEARD_WHITE)
    for side in (-1, 1):                      # fluffy moustache
        cr.move_to(0, -80)
        cr.curve_to(side * 5, -84, side * 11, -83, side * 14, -78)
        cr.curve_to(side * 10, -79, side * 5, -77, 0, -77)
        cr.close_path()
        paint(cr, BEARD_WHITE, INK, 1.4)


def wizard_body(cr, p):
    rrect(cr, -22, -53, 44, 35, 11)           # robe
    paint(cr, WIZARD_PURPLE)
    _star(cr, -12, -26, 3.5)
    paint(cr, GOLD, None)


def wand(cr, angle, p):
    _upright(cr, angle)

    def stick():
        cr.new_path()
        cr.move_to(0, 4)
        cr.line_to(0, -19)
    outlined_stroke(cr, stick, DARK_BROWN, 2.6, 5)
    tw = 1 + 0.15 * math.sin(p.t * 9)
    _star(cr, 0, -23, 5.5 * tw)
    paint(cr, GOLD, INK, 1.6)


# ================================================================ pirate
PIRATE_BLACK = hexc('#2D2F3E')
PARROT = hexc('#4CCB6E')
PARROT_DARK = hexc('#2F9E5B')


def pirate_head(cr, p):
    cr.move_to(-46, -116)                     # tricorn
    cr.curve_to(-34, -107, 34, -107, 46, -116)
    cr.curve_to(40, -121, 34, -141, 0, -141)
    cr.curve_to(-34, -141, -40, -121, -46, -116)
    cr.close_path()
    paint(cr, PIRATE_BLACK)
    cr.move_to(-43, -115)
    cr.curve_to(-32, -108.5, 32, -108.5, 43, -115)
    paint(cr, None, GOLD, 2)
    for a, b in (((-7, -121), (7, -115)), ((7, -121), (-7, -115))):   # crossbones
        cr.move_to(*a)
        cr.line_to(*b)
        paint(cr, None, WHITE, 2.4)
    circle(cr, 0, -127, 5.5)                  # skull
    paint(cr, WHITE, None)
    for x in (-2, 2):
        circle(cr, x, -127.5, 1.3)
        paint(cr, PIRATE_BLACK, None)
    _parrot(cr, p)


def _parrot(cr, p):
    dancing = p.arms == 'jig'
    bob = math.sin(p.t * 10) * 1.6 if dancing else math.sin(p.t * 2) * 0.5
    cr.save()
    cr.translate(-41, -56)                    # sitting on his back shoulder
    for x in (-2, 2):                         # feet
        cr.move_to(x, 0)
        cr.line_to(x, -3)
        paint(cr, None, ORANGE_FEET, 1.6)
    cr.move_to(-1, -4)                        # tail
    cr.line_to(-5, 6)
    cr.line_to(1, 5)
    cr.close_path()
    paint(cr, SNAKE_RED, INK, 1.4)
    ellipse(cr, 0, -10, 7, 9.5)
    paint(cr, PARROT)
    cr.save()                                 # wing (flaps while dancing)
    cr.translate(-3, -14)
    cr.rotate(-0.2 + (math.sin(p.t * 22) * 0.6 if dancing else 0))
    ellipse(cr, 0, 5, 3.6, 7)
    cr.restore()
    paint(cr, PARROT_DARK, INK, 1.4)
    circle(cr, 1, -22 + bob, 6.2)
    paint(cr, PARROT)
    cr.move_to(6, -24 + bob)                  # beak
    cr.curve_to(10, -23 + bob, 10, -19 + bob, 7, -18 + bob)
    cr.line_to(5.5, -21 + bob)
    cr.close_path()
    paint(cr, GOLD, INK, 1.4)
    circle(cr, 2.5, -23.5 + bob, 1.9)
    paint(cr, WHITE, None)
    circle(cr, 3, -23.5 + bob, 1)
    paint(cr, INK, None)
    cr.restore()


ORANGE_FEET = hexc('#F29A4A')


def pirate_face(cr, p):
    cr.move_to(-37, -99)
    cr.line_to(19, -91)
    paint(cr, None, PIRATE_BLACK, 2.2)
    ellipse(cr, 12 + p.look, -87, 7.5, 7)
    paint(cr, PIRATE_BLACK, INK, 1.2)


def pirate_body(cr, p):
    def shirt():
        rrect(cr, -22, -53, 44, 35, 11)
    _striped(cr, shirt, WHITE, BANDANA, 5)
    rrect(cr, -22, -26, 44, 5, 2)             # sash
    paint(cr, hexc('#A8323A'), INK, 1.6)


# ================================================================ superhero
HERO_BLUE = hexc('#2E4BB5')


def hero_behind(cr, p):
    flying = p.arms == 'fly' or p.lift > 8
    trail = -16 if flying else 0
    wave = math.sin(p.t * (9 if flying else 2.5)) * (4 if flying else 1.5)
    cr.move_to(-19, -52)
    cr.curve_to(-28, -38, -34 + trail * 0.5, -22 + wave, -32 + trail, -6 + wave)
    cr.curve_to(-14 + trail, -2 - wave, 10 + trail * 0.5, -4 + wave, 28 + trail * 0.3, -8)
    cr.curve_to(28, -24, 26, -40, 19, -52)
    cr.close_path()
    paint(cr, BANDANA)


def hero_body(cr, p):
    rrect(cr, -22, -26, 44, 5, 2)             # belt
    paint(cr, GOLD, INK, 1.6)
    circle(cr, 0, -39, 8.5)                   # emblem
    paint(cr, GOLD)
    cr.move_to(1.5, -45.5)
    cr.line_to(-3.5, -38.5)
    cr.line_to(0, -38.5)
    cr.line_to(-1.5, -32.5)
    cr.line_to(3.5, -40)
    cr.line_to(0, -40)
    cr.close_path()
    paint(cr, BANDANA, None)


def hero_face(cr, p):
    lx = p.look
    cr.save()
    cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
    rrect(cr, -27 + lx, -95, 54, 16, 8)       # mask with eye holes
    for ex in (-12, 12):
        ellipse(cr, ex + lx, -87, 7, 6.2)
    paint(cr, HERO_BLUE, INK, 1.6)
    cr.restore()


# ================================================================ kitty
KITTY = hexc('#FFB25B')
KITTY_DARK = hexc('#E08A2E')
KITTY_PINK = hexc('#FF9CC2')
YARN = hexc('#FF7AB6')


def kitty_behind(cr, p):
    swish = math.sin(p.t * 3) * 6

    def tail():
        cr.new_path()
        cr.move_to(-18, -26)
        cr.curve_to(-34, -26, -40, -40 + swish * 0.3, -34 + swish, -56)
    outlined_stroke(cr, tail, KITTY, 6, 9.5)
    circle(cr, -34 + swish, -56, 3.6)
    paint(cr, KITTY_DARK, None)


def kitty_body(cr, p):
    rrect(cr, -22, -53, 44, 35, 11)           # onesie
    paint(cr, KITTY)
    ellipse(cr, 0, -34, 11, 10)
    paint(cr, hexc('#FFF1DE'), None)
    for x in (-12, 12):
        cr.move_to(x - 3, -50)
        cr.line_to(x + 3, -47)
        paint(cr, None, KITTY_DARK, 2)


def kitty_head(cr, p):
    for side in (-1, 1):
        cr.move_to(side * 31, -103)
        cr.line_to(side * 25, -126)
        cr.line_to(side * 11, -110)
        cr.close_path()
        paint(cr, KITTY)
        cr.move_to(side * 27, -108)
        cr.line_to(side * 24.5, -120)
        cr.line_to(side * 16, -111)
        cr.close_path()
        paint(cr, KITTY_PINK, None)


def kitty_face(cr, p):
    lx = p.look * 0.6
    for side in (-1, 1):
        for dy in (-3.5, 0, 3.5):
            cr.move_to(side * 19 + lx, -77 + dy * 0.4)
            cr.line_to(side * 27 + lx, -77 + dy)
            paint(cr, None, (1, 1, 1, 0.75), 1.2)
    cr.move_to(-2.2 + lx, -81)
    cr.line_to(2.2 + lx, -81)
    cr.line_to(lx, -78.8)
    cr.close_path()
    paint(cr, KITTY_PINK, None)


def kitty_front(cr, p):
    if p.arms != 'paw':
        return
    hop = abs(math.sin(p.t * 9)) * 4
    cx, cy = 33, -9 - hop
    circle(cr, cx, cy, 7)
    paint(cr, YARN)
    cr.save()
    cr.translate(cx, cy)
    cr.rotate(p.t * 4)
    for a in (-0.6, 0, 0.6):
        cr.new_path()
        cr.arc(0, 0, 5.5, a + 0.6, a + 2.4)
        paint(cr, None, hexc('#D94F92'), 1.2)
    cr.restore()
    cr.move_to(cx - 6, cy + 3)
    cr.curve_to(cx - 14, cy + 9, cx - 20, cy + 6, cx - 26, cy + 9 + hop)
    paint(cr, None, YARN, 1.6)


# ================================================================ registry
OUTFITS = {
    'pharaoh': Outfit(body=pharaoh_body, behind_head=pharaoh_behind_head, face=pharaoh_face,
                      head=pharaoh_head, front_hand=crook, antenna_y=-124),
    'cowboy': Outfit(body=cowboy_body, face=cowboy_face, head=cowboy_head,
                     front_hand=lasso, antenna_y=-135),
    'viking': Outfit(face=viking_face, head=viking_head, front_hand=axe, back_hand=shield,
                     antenna_y=-122),
    'accountant': Outfit(body=accountant_body, face=accountant_face, head=accountant_head,
                         front_hand=calculator),
    'mechanic': Outfit(body=mechanic_body, face=mechanic_face, head=mechanic_head,
                       front_hand=wrench, antenna_y=-121),
    'roman': Outfit(behind=roman_behind, body=roman_body, head=roman_head, front_hand=lyre),
    'chef': Outfit(body=chef_body, head=chef_head, front_hand=frying_pan, antenna_y=-150),
    'astronaut': Outfit(behind=astronaut_behind, body=astronaut_body, head=astronaut_head,
                        antenna_y=-128),
    'wizard': Outfit(body=wizard_body, face=wizard_face, head=wizard_head, front_hand=wand,
                     antenna_y=-158),
    'pirate': Outfit(body=pirate_body, face=pirate_face, head=pirate_head, antenna_y=-140),
    'superhero': Outfit(behind=hero_behind, body=hero_body, face=hero_face),
    'kitty': Outfit(behind=kitty_behind, body=kitty_body, face=kitty_face, head=kitty_head,
                    front=kitty_front),
}
