"""Draws the little robot from a Pose (see robo.core.pose).

Coordinates: origin is the point on the ground between the robot's feet,
y grows downward (so the robot lives at negative y). Total height ~ 130.

The pose key `evil` (0..1) blends the friendly palette into the evil one;
evil facial features (angry eyes, fangs, horns) appear past 0.5.
`pose.costume` dresses him up; outfits live in costumes.py and are drawn
in layers between the body parts (see the OUTFIT LAYER comments).
"""
import math
import random

import cairo

from .anatomy import ANTENNA_TOP, HEAD_TOP  # noqa: F401  (re-exported)
from .costumes import NO_OUTFIT, OUTFITS
from .icons import ICONS
from .shapes import GREY, INK, PINK, circle, ellipse, heart_path, hexc, paint, rrect

BODY = hexc('#F4F7FB')
SHADE = hexc('#DCE4F0')
MINT = hexc('#8EE3CF')
SCREEN = hexc('#26334F')
EYE = hexc('#7DF3FF')
CHEEK = (1.0, 0.55, 0.68, 0.6)
CORAL = hexc('#FF8A80')
BUTTER = hexc('#FFD54F')

# evil palette
BODY_E = hexc('#5C6178')
SHADE_E = hexc('#40455A')
RED_E = hexc('#E8344B')
SCREEN_E = hexc('#2C0C16')
EYE_E = hexc('#FF3B4E')
SWEAT = hexc('#9FDcFF')

def lerp(a, b, k):
    return tuple(x + (y - x) * k for x, y in zip(a, b))


def smooth(k):
    k = max(0.0, min(1.0, k))
    return k * k * (3 - 2 * k)


def _arm(cr, px, py, angle, shade, hand, prop=None, p=None):
    """Arm hanging from (px, py), rotated by angle. `prop(cr, angle, p)` is
    drawn at the hand, so whatever he holds moves with the arm."""
    cr.save()
    cr.translate(px, py)
    cr.rotate(angle)
    rrect(cr, -4, -2, 8, 19, 4)
    paint(cr, shade)
    if prop is not None:
        cr.save()
        cr.translate(0, 19)
        prop(cr, angle, p)
        cr.restore()
    circle(cr, 0, 19, 5)
    paint(cr, hand)
    cr.restore()


def _arm_angles(arms, t, phase):
    """(back arm, front arm) angles for each gesture. 0 = hanging down;
    positive turns the back arm outward, negative turns the front arm up."""
    if arms == 'swing':
        a = math.sin(phase) * 0.55
        return 0.2 + a, -0.2 + a
    if arms == 'wave':
        return 0.2, -2.55 + math.sin(t * 11) * 0.4
    if arms == 'up':
        w = math.sin(t * 9) * 0.25
        return 2.55 + w, -2.55 - w
    if arms == 'roar':                       # viking battle cry: arms up, shaking
        w = math.sin(t * 22) * 0.2
        return 2.6 + w, -2.6 - w
    if arms == 'scheme':                     # rubbing hands together, mwahaha
        r = math.sin(t * 14) * 0.13
        return -1.0 + r, 1.0 + r
    if arms == 'egypt':                      # walk like an Egyptian
        s = math.sin(t * 6) * 0.45
        return 1.57 + s, -1.57 + s
    if arms == 'lasso':                      # lasso twirling over his head
        return 0.3, -2.75 + math.sin(t * 10) * 0.08
    if arms == 'calc':                       # typing on a calculator held in front
        return -1.0 + math.sin(t * 28) * 0.12, 0.9
    if arms == 'lyre':                       # strumming a lyre held in front
        return -0.8 + math.sin(t * 12) * 0.18, 0.95
    if arms == 'fix':                        # bonking his own head with a wrench
        return 0.25, -2.85 + abs(math.sin(t * 8)) * 0.35
    if arms == 'flip':                       # chef: jerk the pan up to flip the pancake
        jerk = 0.5 if (t % 1.2) < 0.15 else 0.0
        return 0.3, -1.25 - jerk
    if arms == 'float':                      # astronaut: arms out, drifting
        d = math.sin(t * 2) * 0.2
        return 1.3 + d, -1.3 - d
    if arms == 'spell':                      # wizard: waving the wand
        return 0.3, -2.4 + math.sin(t * 7) * 0.35
    if arms == 'jig':                        # pirate: hornpipe dance
        s = math.sin(t * 8) * 0.9
        return 1.2 + s, -1.2 + s
    if arms == 'fly':                        # superhero: fist forward, other arm back
        return 1.35 + math.sin(t * 3) * 0.08, -1.65
    if arms == 'paw':                        # kitty: batting at the yarn
        return 0.25, -0.9 + math.sin(t * 9) * 0.35
    b = math.sin(t * 2.2) * 0.05
    return 0.2 + b, -0.2 - b


FRONT_ARM_GESTURES = {'scheme', 'calc', 'lyre'}   # hands in front of the body
OVER_HEAD_GESTURES = {'lasso', 'fix', 'spell'}     # front arm raised in front of the head


def _evil_eye(cr, ex, ey, openness, squint=False):
    side = -1 if ex < 0 else 1          # outer direction
    h = max(0.15, openness) * (0.55 if squint else 1.0)
    cr.save()
    cr.translate(ex, ey + 2)
    cr.scale(1, h)
    circle(cr, 0, -2, 9.5)
    cr.set_source_rgba(EYE_E[0], EYE_E[1], EYE_E[2], 0.22)
    cr.fill()
    cr.move_to(side * 6, -8)            # outer top (high)
    cr.line_to(-side * 6, -2.5)         # inner top (low) -> angry slant
    cr.line_to(-side * 5, 3)
    cr.line_to(side * 5, 3)
    cr.close_path()
    cr.set_source_rgba(*EYE_E)
    cr.fill()
    cr.restore()
    # brow
    cr.move_to(ex + side * 7, ey - 11)
    cr.line_to(ex - side * 6, ey - 6)
    paint(cr, None, EYE_E, 2.6)


def _eye(cr, ex, ey, mood, openness, eye):
    if mood in ('evil', 'laugh'):
        _evil_eye(cr, ex, ey, openness, squint=(mood == 'laugh'))
        return
    cr.set_source_rgba(*eye)
    if mood in ('roar', 'wince'):          # squeezed shut: > <
        side = -1 if ex < 0 else 1
        cr.move_to(ex - side * 5, ey - 5)
        cr.line_to(ex + side * 4, ey)
        cr.line_to(ex - side * 5, ey + 5)
        cr.set_line_width(3)
        cr.stroke()
    elif mood in ('happy', 'sing', 'cat'):
        cr.new_path()
        cr.arc(ex, ey + 3, 5.5, math.pi * 1.12, math.pi * 1.88)
        cr.set_line_width(3.2)
        cr.stroke()
    elif mood == 'sleep':
        cr.new_path()
        cr.arc(ex, ey - 1, 5, math.pi * 0.15, math.pi * 0.85)
        cr.set_line_width(2.6)
        cr.stroke()
    elif mood == 'surprised':
        circle(cr, ex, ey, 6.5)
        cr.fill()
        circle(cr, ex - 2, ey - 2.2, 1.8)
        cr.set_source_rgba(1, 1, 1, 0.9)
        cr.fill()
    elif mood == 'sad':                    # droopy eyes looking down
        h = max(1.6, 9 * openness)
        rrect(cr, ex - 4.5, ey - h / 2 + 2.5, 9, h, h / 2)
        cr.fill()
        side = -1 if ex < 0 else 1
        cr.move_to(ex - side * 5, ey - 7)    # worried brows (inner end up)
        cr.line_to(ex + side * 4, ey - 4.5)
        cr.set_line_width(2.2)
        cr.stroke()
    else:
        if mood == 'focus':                # concentrating: half closed
            openness *= 0.45
        h = max(1.6, 14 * openness)
        rrect(cr, ex - 4.8, ey - h / 2, 9.6, h, 4.8 if h > 9.6 else h / 2)
        cr.fill()
        if openness > 0.6:
            circle(cr, ex - 1.6, ey - 3.2, 1.6)
            cr.set_source_rgba(1, 1, 1, 0.9)
            cr.fill()


def _mouth(cr, mx, my, mood, eye, screen, t, talk=0.0):
    if mood in ('evil', 'laugh'):
        o = 3.5 + (abs(math.sin(t * 18)) * 3 if mood == 'laugh' else 0) + talk * 4
        cr.move_to(mx - 12, my - 5)
        cr.curve_to(mx - 6, my + o, mx + 6, my + o, mx + 12, my - 5)
        cr.curve_to(mx + 5, my - 1, mx - 5, my - 1, mx - 12, my - 5)
        cr.close_path()
        cr.set_source_rgba(*EYE_E)
        cr.fill()
        # fangs
        for fx in (-5, 5):
            cr.move_to(fx - 2.2, my - 2.2)
            cr.line_to(fx, my + 2.2)
            cr.line_to(fx + 2.2, my - 2.2)
            cr.close_path()
            cr.set_source_rgba(1, 1, 1, 0.95)
            cr.fill()
        return
    cr.set_source_rgba(*eye)
    cr.set_line_width(2.3)
    cr.new_path()
    if talk > 0.06 and mood not in ('roar', 'sleep'):   # talking: mouth follows his voice
        w = 4.2 if mood != 'sad' else 3.6
        ellipse(cr, mx, my - 1.5, w + talk * 1.5, 0.9 + talk * 4.6)
        cr.fill()
        return
    if mood == 'sad':                      # little frown
        cr.arc(mx, my + 1, 4, math.pi * 1.15, math.pi * 1.85)
        cr.stroke()
        return
    if mood == 'roar':                     # big open shout
        o = 7 + abs(math.sin(t * 22)) * 1.5
        cr.move_to(mx - 8, my - 4)
        cr.line_to(mx + 8, my - 4)
        cr.curve_to(mx + 8, my + o, mx - 8, my + o, mx - 8, my - 4)
        cr.close_path()
        cr.fill()
        ellipse(cr, mx, my + o * 0.55, 3.5, 2)
        cr.set_source_rgba(1.0, 0.5, 0.6, 1)
        cr.fill()
    elif mood == 'sing':                   # little "ooh" that wobbles
        circle(cr, mx, my - 1, 2.4 + abs(math.sin(t * 7)) * 1.6)
        cr.fill()
    elif mood == 'cat':                    # :3
        cr.arc(mx - 2.6, my - 2.5, 2.6, 0, math.pi)
        cr.new_sub_path()
        cr.arc(mx + 2.6, my - 2.5, 2.6, 0, math.pi)
        cr.stroke()
    elif mood == 'wince':                  # wobbly zigzag
        cr.move_to(mx - 6, my - 2)
        for i in range(1, 7):
            cr.line_to(mx - 6 + i * 2, my - 2 + (2 if i % 2 else 0))
        cr.stroke()
    elif mood == 'focus':
        cr.move_to(mx - 3.5, my - 2)
        cr.line_to(mx + 3.5, my - 2)
        cr.stroke()
    elif mood == 'happy':
        cr.arc(mx, my - 1.5, 5, 0, math.pi)
        cr.close_path()
        cr.fill()
    elif mood == 'surprised':
        circle(cr, mx, my, 3)
        cr.stroke()
    elif mood == 'sleep':
        circle(cr, mx, my, 1.8)
        cr.stroke()
    else:
        cr.arc(mx, my - 3, 4, math.pi * 0.15, math.pi * 0.85)
        cr.stroke()


def _horns(cr, k, color):
    if k <= 0.01:
        return
    for x, side in ((-21, -1), (21, 1)):
        cr.save()
        cr.translate(x, HEAD_TOP + 4)
        cr.scale(k, k)
        cr.move_to(-6, 0)
        cr.curve_to(-5, -8, side * 2, -12, side * 5, -15)
        cr.curve_to(side * 4, -9, 6, -6, 6, 0)
        cr.close_path()
        paint(cr, color, INK, 2.2)
        cr.restore()


def _sweat(cr, t):
    y = -100 + (t * 14) % 10
    cr.move_to(31, y - 7)
    cr.curve_to(33, y - 3, 35, y - 1, 35, y + 1.5)
    cr.curve_to(35, y + 4, 33, y + 5, 31, y + 5)
    cr.curve_to(29, y + 5, 27, y + 4, 27, y + 1.5)
    cr.curve_to(27, y - 1, 29, y - 3, 31, y - 7)
    cr.close_path()
    paint(cr, SWEAT, INK, 1.8)


def antenna_color(p):
    """The antenna glows in the colour of whatever the robot is reporting."""
    if p.antenna == 'alert':
        return ICONS.get(p.alert_kind, ICONS['bell'])[1]
    return {'evil': EYE_E, 'sleep': GREY}.get(p.antenna, BUTTER)


def draw_robot(cr, p):
    """Draw the robot with its ground point at the current origin."""
    t = p.t
    phase = p.phase
    walking = p.walking
    dangling = p.dangling
    lift = p.lift
    mood = p.mood
    look = p.look
    arms = p.arms
    outfit = OUTFITS.get(p.costume, NO_OUTFIT)
    e = max(0.0, min(1.0, p.evil))
    glitch = p.glitch

    body = lerp(BODY, BODY_E, e)
    shade = lerp(SHADE, SHADE_E, e)
    accent = lerp(MINT, RED_E, e)
    screen = lerp(SCREEN, SCREEN_E, e)
    eye = lerp(EYE, EYE_E, e)

    cr.save()
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)

    if p.shadow:
        r = max(12.0, 28 - lift * 0.8)
        ellipse(cr, 0, -1, r, r * 0.22)
        cr.set_source_rgba(0.1, 0.12, 0.2, 0.22 * max(0.3, 1 - lift / 40))
        cr.fill()

    cr.translate(0, -lift)
    sq = p.squash
    cr.scale(1 + sq, 1 - sq)
    cr.scale(p.facing, 1)

    # ---- legs
    if walking:
        legA = max(0.0, math.sin(phase)) * 5
        legB = max(0.0, -math.sin(phase)) * 5
        bob = abs(math.sin(phase)) * 2.0
    elif dangling:
        s = math.sin(t * 9)
        legA, legB = max(0.0, s) * 4, max(0.0, -s) * 4
        bob = 0.0
    else:
        legA = legB = 0.0
        bob = (math.sin(t * 2.2) + 1) * 0.7
    if mood == 'laugh':
        bob += abs(math.sin(t * 22)) * 2.5

    # ---- OUTFIT LAYER: behind everything, even the legs (capes, tails)
    if outfit.behind:
        cr.save()
        cr.translate(0, -bob)
        outfit.behind(cr, p)
        cr.restore()

    for lx, ll in ((-11, legA), (11, legB)):
        rrect(cr, lx - 5, -21 - ll, 10, 15, 4)
        paint(cr, shade)
        ellipse(cr, lx + 2, -5 - ll, 8.5, 5)
        paint(cr, accent)

    cr.translate(0, -bob)

    # ---- arms (behind the body unless the gesture is in front)
    aL, aR = _arm_angles(arms, t, phase)
    front_arms = arms in FRONT_ARM_GESTURES

    over_head = arms in OVER_HEAD_GESTURES

    def back_arm():
        _arm(cr, -21, -45, aL, shade, accent, outfit.back_hand, p)

    def front_arm():
        _arm(cr, 21, -45, aR, shade, accent, outfit.front_hand, p)

    if not front_arms:
        back_arm()
        if not over_head:
            front_arm()

    # ---- body
    rrect(cr, -22, -53, 44, 35, 11)
    paint(cr, body)
    rrect(cr, -11, -45, 22, 14, 5)
    paint(cr, shade, INK, 2)
    for i, (bx, col) in enumerate(((-5.5, CORAL), (0, BUTTER), (5.5, MINT))):
        if e > 0.5:
            on = int(t * 6 + i) % 3 == 0
            col = EYE_E if on else lerp(EYE_E, SHADE_E, 0.6)
        circle(cr, bx, -38, 2.3)
        paint(cr, col, None)

    # ---- OUTFIT LAYER: on the body (collars, ties, overalls)
    if outfit.body:
        outfit.body(cr, p)

    if front_arms:
        back_arm()
        front_arm()

    # ---- head
    cr.save()
    tilt = p.tilt + (math.sin(phase) * 0.03 if walking else 0.0)
    if mood == 'laugh':
        tilt += math.sin(t * 22) * 0.05 - 0.08
    cr.translate(0, -58)
    cr.rotate(tilt)
    cr.translate(0, 58)
    if arms == 'egypt':                      # head slides side to side
        cr.translate(math.sin(t * 6) * 3.5, 0)

    rrect(cr, -43, -93, 10, 20, 4)
    paint(cr, accent)
    rrect(cr, 33, -93, 10, 20, 4)
    paint(cr, accent)

    _horns(cr, smooth((e - 0.5) * 2), RED_E)

    # ---- OUTFIT LAYER: behind the head (headdress flaps)
    if outfit.behind_head:
        outfit.behind_head(cr, p)

    rrect(cr, -37, HEAD_TOP, 74, 58, 20)
    paint(cr, body)
    rrect(cr, -28, -104, 56, 40, 13)
    paint(cr, screen, INK, 2)
    rrect(cr, -22, -100, 13, 3.5, 1.7)
    cr.set_source_rgba(1, 1, 1, 0.14)
    cr.fill()

    openness = p.openness
    for ex in (-12, 12):
        _eye(cr, ex + look, -87, mood, openness, eye)
    cheek_a = CHEEK[3] * (1 - e)
    if cheek_a > 0.02:
        for cx in (-19, 19):
            ellipse(cr, cx + look * 0.5, -76, 4.2, 2.6)
            cr.set_source_rgba(CHEEK[0], CHEEK[1], CHEEK[2], cheek_a)
            cr.fill()
    _mouth(cr, look * 0.6, -75, mood, eye, screen, t, p.talk)

    if glitch > 0:   # scanline noise on the face screen
        cr.save()
        rrect(cr, -28, -104, 56, 40, 13)
        cr.clip()
        for _ in range(int(3 + glitch * 5)):
            y = random.uniform(-104, -64)
            cr.rectangle(-28 + random.uniform(-8, 8), y, 56, random.uniform(1, 3.5))
            c = random.choice((EYE, EYE_E, (1, 1, 1, 1)))
            cr.set_source_rgba(c[0], c[1], c[2], 0.6 * glitch)
            cr.fill()
        cr.restore()

    # ---- OUTFIT LAYER: face (glasses, beards) and head (hats, helmets)
    if outfit.face:
        outfit.face(cr, p)
    if outfit.head:
        outfit.head(cr, p)

    if p.sweat:
        _sweat(cr, t)

    # ---- antenna (last, so it pokes out of hats)
    cr.save()
    cr.translate(0, outfit.antenna_y)        # sticks out of the top of any hat
    sway = math.sin(t * 3) * 0.12 + (math.sin(phase) * 0.18 if walking else 0.0)
    if dangling:
        sway += math.sin(t * 7) * 0.25
    if arms == 'fix':                        # boing! from the wrench
        sway += math.sin(t * 25) * 0.25
    cr.rotate(sway)
    cr.move_to(0, 0)
    cr.line_to(0, -11)
    paint(cr, None, INK, 2.6)
    ant = antenna_color(p)
    glow = p.glow
    if glow > 0:
        circle(cr, 0, -15, 11)
        cr.set_source_rgba(ant[0], ant[1], ant[2], 0.35 * glow)
        cr.fill()
    circle(cr, 0, -15, 5.2)
    paint(cr, ant, INK, 2.2)
    circle(cr, -1.6, -16.8, 1.5)
    paint(cr, (1, 1, 1, 0.85), None)
    cr.restore()

    cr.restore()  # head

    if over_head:
        front_arm()

    # ---- OUTFIT LAYER: in front of everything (toys)
    if outfit.front:
        outfit.front(cr, p)
    cr.restore()


def draw_zzz(cr, t, facing=1):
    """Floating Z's above the robot's head (origin = ground point)."""
    cr.save()
    cr.select_font_face('Sans', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    for i in range(3):
        ph = (t * 0.45 + i / 3.0) % 1.0
        x = facing * (26 + ph * 18) - 5
        y = HEAD_TOP - 4 - ph * 34
        cr.set_font_size(9 + ph * 9)
        cr.set_source_rgba(INK[0], INK[1], INK[2], math.sin(ph * math.pi))
        cr.move_to(x, y)
        cr.show_text('z')
    cr.restore()


def draw_hearts(cr, ages):
    """Little hearts floating up from the head after a pat."""
    for i, age in enumerate(ages):
        if age < 0 or age > 1.4:
            continue
        k = age / 1.4
        x = math.sin(age * 5 + i) * 10 + (i % 3 - 1) * 14
        y = HEAD_TOP - 6 - k * 44
        cr.save()
        cr.push_group()
        heart_path(cr, x, y, 0.42 + 0.15 * (1 - k))
        paint(cr, PINK, INK, 2)
        cr.pop_group_to_source()
        cr.paint_with_alpha(1 - k)
        cr.restore()
