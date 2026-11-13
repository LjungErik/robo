"""Draws the robot from a Pose, using a Design built from character files.

This file is only the *rig*: it knows how a robot is put together and how it
moves (legs walk, arms rotate at the shoulders, the head tilts, the upper
body bobs and sinks when he sits). What every piece looks like comes from
the character files in robo/characters/ (see the README there).

Coordinates: origin is the point on the ground between the robot's feet,
y grows downward (so the robot lives at negative y), +x is the way he faces.

Paint order (parts come from the base design, layers from outfits):

    layer anchor                        where a web line sticks (top of the screen)
    layer tether                        the web line itself, hand to anchor
                                        (both: not mirrored; the robot swings around the anchor)
    part shadow                         (on the ground, not lifted)
    layer behind                        capes, tails, jet flames
    part legs
    arms behind the body:  part arm, layer back_hand / front_hand, part hand
    part torso,  layer body
    head:  part head_back, layer behind_head, part head, part face,
           layer face, layer head, part overlay, part antenna (at antenna_y)
    arms in front / over the head (depends on the gesture's `place`)
    layer front
    layer ground                        on the floor, not bobbing (the laptop)
"""
import math

import cairo

from robo.design import REGISTRY

from .icons import antenna_colour_for
from .interpreter import safe_draw
from .shapes import INK, PINK, heart_path, paint

HEAD_TOP = -112                     # the default design's head top (for callers that ask)


def smooth(k):
    k = max(0.0, min(1.0, k))
    return k * k * (3 - 2 * k)


def antenna_color(p):
    """The antenna glows in the colour of whatever the robot is reporting."""
    return antenna_colour_for(p.antenna, p.alert_kind)


def design_for(p):
    return REGISTRY.design(p.skin, p.costume)


def pose_env(p, design):
    """The variables a character file's expressions can read."""
    palette = dict(design.palette)
    ant = antenna_color(p)
    palette['antenna'] = lambda env: ant
    return {
        't': p.t, 'phase': p.phase, 'walking': p.walking, 'dangling': p.dangling,
        'lift': p.lift, 'squash': p.squash, 'mood': p.mood, 'openness': p.openness,
        'look': p.look, 'arms': p.arms, 'antenna': p.antenna, 'glow': p.glow,
        'shadow': p.shadow, 'tilt': p.tilt, 'evil': max(0.0, min(1.0, p.evil)),
        'glitch': p.glitch, 'sweat': p.sweat, 'zzz': p.zzz, 'talk': p.talk, 'sit': p.sit,
        'facing': p.facing, 'costume': p.costume, 'skin': p.skin or 'robo',
        'airborne': p.airborne, 'travel': p.travel, 'cruising': p.cruising,
        'hanging': p.travel == 'hang' and p.airborne,
        'flying': p.travel == 'fly' and p.airborne,
        'head_top': design.head_top, 'antenna_y': design.antenna_y,
        'web': p.web, 'web_hit': p.web_hit, 'web_gone': p.web_gone,
        'anchor_x': p.anchor[0], 'anchor_y': p.anchor[1], 'swing': p.swing,
        '_palette': palette,
    }


def draw_robot(cr, p, design=None):
    """Draw the robot with its ground point at the current origin."""
    d = design or design_for(p)
    rig = d.rig
    env = pose_env(p, d)
    t, phase = p.t, p.phase
    sit = smooth(p.sit)
    drop = sit * rig['sit_drop']
    sx, sy = rig['shoulder']
    arm_len = rig['arm_length']
    nx, ny = rig['neck']

    def part(name, e=env):
        fn = d.parts.get(name)
        if fn is not None:
            safe_draw(fn[0], cr, e, fn[1])

    def slot(name, e=env):
        for fn, label in d.slots.get(name, ()):
            safe_draw(fn, cr, e, label)

    cr.save()
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)

    # ---- legs and bob
    if p.walking:
        leg_a = max(0.0, math.sin(phase)) * 5
        leg_b = max(0.0, -math.sin(phase)) * 5
        bob = abs(math.sin(phase)) * 2.0
    elif p.dangling:
        s = math.sin(t * 9)
        leg_a, leg_b = max(0.0, s) * 4, max(0.0, -s) * 4
        bob = 0.0
    else:
        leg_a = leg_b = 0.0
        bob = (math.sin(t * 2.2) + 1) * 0.7
    if p.mood == 'laugh':
        bob += abs(math.sin(t * 22)) * 2.5
    bob *= 1 - sit
    env.update(leg_a=leg_a, leg_b=leg_b, bob=bob, drop=drop, sit_k=sit)

    gesture = (d.gestures.get(p.arms) or REGISTRY.gesture(p.arms) or d.gestures.get('rest')
               or REGISTRY.gesture('rest'))
    if gesture is not None:
        a_back, a_front = gesture.back(env), gesture.front(env)
        place = gesture.place
    else:
        a_back, a_front, place = 0.2, -0.2, 'behind'

    # ---- a web line to the top of the screen (not mirrored, he swings around its anchor)
    if p.web >= 0:
        sq = p.squash
        hx = p.facing * (sx - arm_len * math.sin(a_front)) * (1 + sq)
        hy = (sy + arm_len * math.cos(a_front) - bob + drop) * (1 - sq) - p.lift
        env.update(hand_x=hx, hand_y=hy)
        slot('anchor')
        ax, ay = p.anchor
        cr.translate(ax, ay)
        cr.rotate(p.swing)
        cr.translate(-ax, -ay)
        slot('tether')

    if p.shadow:
        part('shadow')

    cr.translate(0, -p.lift)
    sq = p.squash
    cr.scale(1 + sq, 1 - sq)
    cr.scale(p.facing, 1)

    if d.slots.get('behind'):
        cr.save()
        cr.translate(0, -bob + drop)
        slot('behind')
        cr.restore()

    part('legs')

    cr.save()                                # upper body (bobs, sinks when sitting)
    cr.translate(0, -bob + drop)

    # ---- arms
    def arm(side, angle, hand_slot):
        e = dict(env, side=side, angle=angle)
        cr.save()
        cr.translate(side * sx, sy)
        cr.rotate(angle)
        part('arm', e)
        if d.slots.get(hand_slot):
            cr.save()
            cr.translate(0, arm_len)
            slot(hand_slot, e)
            cr.restore()
        part('hand', e)
        cr.restore()

    def back_arm():
        arm(-1, a_back, 'back_hand')

    def front_arm():
        arm(1, a_front, 'front_hand')

    if place != 'front':
        back_arm()
        if place != 'over_head':
            front_arm()

    part('torso')
    slot('body')

    if place == 'front':
        back_arm()
        front_arm()

    # ---- head
    cr.save()
    tilt = p.tilt + (math.sin(phase) * 0.03 if p.walking else 0.0)
    if p.mood == 'laugh':
        tilt += math.sin(t * 22) * 0.05 - 0.08
    cr.translate(nx, ny)
    cr.rotate(tilt)
    cr.translate(-nx, -ny)
    if gesture is not None and gesture.head_x is not None:
        cr.translate(gesture.head_x(env), 0)

    part('head_back')
    slot('behind_head')
    part('head')
    part('face')
    slot('face')
    slot('head')
    part('overlay')
    cr.save()
    cr.translate(0, d.antenna_y)             # sticks out of the top of any hat
    part('antenna')
    cr.restore()
    cr.restore()  # head

    if place == 'over_head':
        front_arm()

    slot('front')
    cr.restore()  # upper body

    slot('ground')
    cr.restore()


def draw_zzz(cr, t, facing=1, head_top=HEAD_TOP):
    """Floating Z's above the robot's head (origin = ground point)."""
    cr.save()
    cr.select_font_face('Sans', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    for i in range(3):
        ph = (t * 0.45 + i / 3.0) % 1.0
        x = facing * (26 + ph * 18) - 5
        y = head_top - 4 - ph * 34
        cr.set_font_size(9 + ph * 9)
        cr.set_source_rgba(INK[0], INK[1], INK[2], math.sin(ph * math.pi))
        cr.move_to(x, y)
        cr.show_text('z')
    cr.restore()


def draw_hearts(cr, ages, head_top=HEAD_TOP):
    """Little hearts floating up from the head after a pat."""
    for i, age in enumerate(ages):
        if age < 0 or age > 1.4:
            continue
        k = age / 1.4
        x = math.sin(age * 5 + i) * 10 + (i % 3 - 1) * 14
        y = head_top - 6 - k * 44
        cr.save()
        cr.push_group()
        heart_path(cr, x, y, 0.42 + 0.15 * (1 - k))
        paint(cr, PINK, INK, 2)
        cr.pop_group_to_source()
        cr.paint_with_alpha(1 - k)
        cr.restore()
