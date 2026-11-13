"""Cute vector icons for the speech bubble.

Every icon is a function `icon_xxx(cr, t)` that draws inside a 48x48 box;
`t` is the number of seconds since the bubble appeared, for animation.
To add an icon: write the function, add it to ICONS, and add its name to
robo.events.KINDS. The things characters demand while dressed up are not
here: each character file draws its own (`demand:` in robo/characters/).
"""
import math

import cairo

from robo.design import REGISTRY

from .interpreter import safe_draw

from .shapes import (BLUE, CARD, CREAM, GREEN, GREY, INK, ORANGE, PINK, PURPLE, RED, SKY, hexc,
                     WHITE, YELLOW, circle, ellipse, heart_path, line, outlined_stroke,
                     paint, rrect, sparkle, speech_path)

def _battery(cr, level, color):
    rrect(cr, 5, 14, 34, 21, 5.5)
    paint(cr, WHITE)
    rrect(cr, 39, 20, 5, 9, 2)
    paint(cr, INK, None)
    if level > 0:
        rrect(cr, 9, 18, max(4, 26 * level), 13, 3)
        paint(cr, color, None)


def icon_battery_low(cr, t):
    pulse = 0.45 + 0.55 * abs(math.sin(t * 4))
    _battery(cr, 0.16, RED[:3] + (pulse,))
    circle(cr, 38, 11, 7.5)
    paint(cr, RED)
    line(cr, [(38, 7.3), (38, 11.6)], WHITE, 2.6)
    circle(cr, 38, 15, 1.4)
    paint(cr, WHITE, None)


def _bolt(cr, dx=0, dy=0):
    pts = [(25, 10), (15, 26), (22, 26), (19, 39), (30, 22), (23, 22), (26, 10)]
    cr.move_to(pts[0][0] + dx, pts[0][1] + dy)
    for x, y in pts[1:]:
        cr.line_to(x + dx, y + dy)
    cr.close_path()
    paint(cr, YELLOW, INK, 2.2)


def icon_battery_charging(cr, t):
    level = 0.25 + 0.75 * ((t * 0.6) % 1.0)
    _battery(cr, level, GREEN)
    _bolt(cr, -1, 0)


def icon_battery_full(cr, t):
    _battery(cr, 1.0, GREEN)
    tw = 0.7 + 0.3 * math.sin(t * 6)
    sparkle(cr, 41, 8, 6 * tw)
    sparkle(cr, 7, 9, 4 * (1.7 - tw))
    sparkle(cr, 22, 24.5, 4.5, WHITE)


def icon_update(cr, t):
    rrect(cr, 5, 19, 30, 23, 4)
    paint(cr, CARD)
    cr.rectangle(17, 19.8, 6, 6)
    paint(cr, CREAM, None)
    line(cr, [(5, 26), (35, 26)], INK, 2.2)
    by = 13 + math.sin(t * 5) * 1.8
    circle(cr, 35, by, 9.5)
    paint(cr, BLUE)
    line(cr, [(35, by - 4.8), (35, by + 4.2)], WHITE, 2.8)
    line(cr, [(31.2, by + 0.6), (35, by + 4.4), (38.8, by + 0.6)], WHITE, 2.8)


def icon_reboot(cr, t):
    cr.save()
    cr.translate(24, 25)
    cr.rotate(t * 1.8)
    r = 13
    a0 = -math.pi / 2 + 0.55
    a1 = a0 + 1.55 * math.pi

    def arc():
        cr.new_path()
        cr.arc(0, 0, r, a0, a1)

    outlined_stroke(cr, arc, PURPLE, 5.0, 9.5)
    px, py = r * math.cos(a1), r * math.sin(a1)
    tx, ty = -math.sin(a1), math.cos(a1)   # tangent (direction of travel)
    nx, ny = math.cos(a1), math.sin(a1)    # normal
    cr.move_to(px + tx * 7, py + ty * 7)
    cr.line_to(px + nx * 7, py + ny * 7)
    cr.line_to(px - nx * 7, py - ny * 7)
    cr.close_path()
    paint(cr, PURPLE, INK, 2.2)
    cr.restore()


def icon_mail(cr, t):
    y = 13 + math.sin(t * 3) * 1.2
    rrect(cr, 5, y, 37, 25, 4)
    paint(cr, CREAM)
    line(cr, [(6.5, y + 2), (23.5, y + 14), (40.5, y + 2)], INK, 2.4)
    circle(cr, 41, y + 0.5, 6)
    paint(cr, RED)


def icon_chat(cr, t):
    speech_path(cr, 5, 7, 38, 27, 11, 15, 9, 8)
    paint(cr, SKY)
    for i in range(3):
        dy = math.sin(t * 6 - i * 0.9) * 1.8
        circle(cr, 15 + i * 9, 20.5 + dy, 2.7)
        paint(cr, INK, None)


def _wifi(cr, colors):
    cx, cy = 24, 37
    for r, col in zip((9, 17, 25), colors):
        def arc(r=r):
            cr.new_path()
            cr.arc(cx, cy, r, -0.75 * math.pi, -0.25 * math.pi)
        outlined_stroke(cr, arc, col)
    circle(cr, cx, cy, 3.8)
    paint(cr, colors[0], INK, 2.2)


def icon_wifi(cr, t):
    k = int((t * 2.5) % 4)
    cols = [GREEN if i < k or t > 1.6 else GREY for i in range(3)]
    _wifi(cr, cols)


def icon_wifi_off(cr, t):
    _wifi(cr, [GREY, GREY, GREY])

    def slash():
        cr.new_path()
        cr.move_to(11, 10)
        cr.line_to(37, 42)

    outlined_stroke(cr, slash, RED, 4.2, 7.8)


def icon_download(cr, t):
    dy = math.sin(t * 5) * 2.2
    pts = [(19, 5), (29, 5), (29, 19), (36, 19), (24, 31), (12, 19), (19, 19)]
    cr.move_to(pts[0][0], pts[0][1] + dy)
    for x, y in pts[1:]:
        cr.line_to(x, y + dy)
    cr.close_path()
    paint(cr, GREEN)
    line(cr, [(7, 30), (7, 41), (41, 41), (41, 30)], INK, 3.6)


def icon_calendar(cr, t):
    rrect(cr, 7, 10, 34, 31, 6)
    paint(cr, WHITE, None)
    cr.save()
    rrect(cr, 7, 10, 34, 31, 6)
    cr.clip()
    cr.rectangle(7, 10, 34, 10)
    paint(cr, RED, None)
    cr.restore()
    rrect(cr, 7, 10, 34, 31, 6)
    paint(cr)
    line(cr, [(7, 20), (41, 20)], INK, 2.2)
    for x in (16, 32):
        rrect(cr, x - 2, 5.5, 4, 9, 2)
        paint(cr, INK, None)
    for row in range(2):
        for col in range(3):
            cx, cy = 15 + col * 9, 27 + row * 7.5
            if (row, col) == (1, 1):
                circle(cr, cx, cy, 3.3 + 0.5 * math.sin(t * 6))
                paint(cr, RED, None)
            else:
                circle(cr, cx, cy, 2)
                paint(cr, GREY, None)


def icon_bell(cr, t):
    swing = max(0.0, 1.0 - (t % 2.0)) * math.sin(t * 14) * 0.38
    cr.save()
    cr.translate(24, 8)
    cr.rotate(swing)
    cr.translate(-24, -8)
    circle(cr, 24, 37, 4.2)
    paint(cr, ORANGE)
    cr.move_to(9, 35)
    cr.curve_to(12.5, 33, 14, 30, 14, 25)
    cr.line_to(14, 21)
    cr.curve_to(14, 14, 18.5, 10, 24, 10)
    cr.curve_to(29.5, 10, 34, 14, 34, 21)
    cr.line_to(34, 25)
    cr.curve_to(34, 30, 35.5, 33, 39, 35)
    cr.close_path()
    paint(cr, YELLOW)
    circle(cr, 24, 8, 2.6)
    paint(cr, YELLOW, INK, 2.2)
    cr.restore()
    if abs(swing) > 0.08:
        cr.set_source_rgba(*INK)
        cr.set_line_width(2)
        cr.new_path()
        cr.arc(24, 24, 20, math.pi * 0.85, math.pi * 1.1)
        cr.stroke()
        cr.arc(24, 24, 20, -math.pi * 0.1, math.pi * 0.15)
        cr.stroke()


def icon_alarm(cr, t):
    shake = math.sin(t * 40) * 1.3 if (t % 1.5) < 0.6 else 0
    cr.save()
    cr.translate(shake, 0)
    circle(cr, 12.5, 12.5, 6)
    paint(cr, RED)
    circle(cr, 35.5, 12.5, 6)
    paint(cr, RED)
    line(cr, [(15, 39), (11, 44)], INK, 3.2)
    line(cr, [(33, 39), (37, 44)], INK, 3.2)
    circle(cr, 24, 27, 15)
    paint(cr, WHITE)
    line(cr, [(24, 27), (24, 18.5)], INK, 2.6)
    line(cr, [(24, 27), (30, 30)], INK, 2.6)
    circle(cr, 24, 27, 1.8)
    paint(cr, INK, None)
    cr.restore()


def icon_warning(cr, t):
    s = 1 + 0.05 * math.sin(t * 6)
    cr.save()
    cr.translate(24, 26)
    cr.scale(s, s)
    cr.translate(-24, -26)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    cr.move_to(24, 6)
    cr.line_to(44, 41)
    cr.line_to(4, 41)
    cr.close_path()
    paint(cr, YELLOW, INK, 3)
    line(cr, [(24, 18), (24, 29)], INK, 4.2)
    circle(cr, 24, 35, 2.3)
    paint(cr, INK, None)
    cr.restore()


def icon_music(cr, t):
    dy = math.sin(t * 5) * 1.6
    cr.move_to(18.5, 11 + dy)
    cr.line_to(38.5, 6 + dy)
    cr.line_to(38.5, 12 + dy)
    cr.line_to(18.5, 17 + dy)
    cr.close_path()
    paint(cr, PINK)
    line(cr, [(18.5, 14 + dy), (18.5, 35 + dy)], INK, 2.8)
    line(cr, [(38.5, 9 + dy), (38.5, 31 + dy)], INK, 2.8)
    ellipse(cr, 13.5, 35.5 + dy, 5.8, 4.4)
    paint(cr, PINK)
    ellipse(cr, 33.5, 31.5 + dy, 5.8, 4.4)
    paint(cr, PINK)


def icon_camera(cr, t):
    rrect(cr, 15, 10, 14, 9, 3)
    paint(cr, PURPLE)
    rrect(cr, 4, 16, 40, 25, 6)
    paint(cr, PURPLE)
    circle(cr, 24, 28.5, 8.5)
    paint(cr, WHITE)
    circle(cr, 24, 28.5, 4)
    paint(cr, INK, None)
    circle(cr, 22.6, 27, 1.3)
    paint(cr, WHITE, None)
    circle(cr, 37.5, 21.5, 2)
    paint(cr, YELLOW, None)
    if (t % 2.0) < 0.25:
        sparkle(cr, 41, 9, 7)


def icon_bluetooth(cr, t):
    s = 1 + 0.04 * math.sin(t * 5)
    cr.save()
    cr.translate(24, 24)
    cr.scale(s, s)
    cr.translate(-24, -24)
    circle(cr, 24, 24, 17)
    paint(cr, BLUE)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    line(cr, [(17, 17), (31, 30), (24, 37), (24, 11), (31, 18), (17, 31)], WHITE, 2.8)
    cr.restore()


def icon_usb(cr, t):
    dy = abs(math.sin(t * 3)) * 2.5
    cr.save()
    cr.translate(0, -dy)
    rrect(cr, 18, 5, 12, 13, 2)
    paint(cr, WHITE)
    cr.rectangle(20.8, 9, 2.6, 3.2)
    cr.rectangle(24.6, 9, 2.6, 3.2)
    paint(cr, INK, None)
    rrect(cr, 13, 17, 22, 26, 6)
    paint(cr, SKY)
    circle(cr, 24, 35, 2.5)
    paint(cr, GREEN if (t % 1.0) < 0.6 else WHITE, None)
    cr.restore()


def icon_heart(cr, t):
    s = 1.0 + 0.08 * abs(math.sin(t * 5))
    heart_path(cr, 24, 24, s)
    paint(cr, PINK)
    ellipse(cr, 16.5, 16, 2.6, 1.8)
    paint(cr, WHITE[:3] + (0.8,), None)


# ---------------------------------------------------------------- conversation
def icon_mic(cr, t):
    """Listening: a microphone with sound waves pulsing out."""
    for i in range(2):
        k = (t * 1.2 + i * 0.5) % 1.0
        for side in (-1, 1):
            cr.new_path()
            cr.arc(24, 20, 11 + k * 9, -0.45 + (math.pi if side < 0 else 0),
                   0.45 + (math.pi if side < 0 else 0))
            paint(cr, None, (SKY[0], SKY[1], SKY[2], 1 - k), 2.6)
    rrect(cr, 18, 6, 12, 22, 6)
    paint(cr, RED)
    for y in (12, 16, 20):
        line(cr, [(20.5, y), (27.5, y)], (1, 1, 1, 0.7), 1.4)
    cr.new_path()
    cr.arc(24, 21, 10, 0.1 * math.pi, 0.9 * math.pi)
    paint(cr, None, INK, 2.6)
    line(cr, [(24, 31), (24, 37)], INK, 2.6)
    line(cr, [(17, 38), (31, 38)], INK, 2.8)


def icon_thinking(cr, t):
    """Thinking: a little gear turning and dots bouncing."""
    cr.save()
    cr.translate(24, 18)
    cr.rotate(t * 2.5)
    cr.new_path()
    teeth = 8
    step = math.pi / teeth
    for i in range(teeth * 2):
        cr.arc(0, 0, 11 if i % 2 == 0 else 8.5, i * step, (i + 1) * step)
    cr.close_path()
    paint(cr, YELLOW)
    circle(cr, 0, 0, 3.5)
    paint(cr, WHITE, INK, 2)
    cr.restore()
    for i in range(3):
        dy = -abs(math.sin(t * 6 - i * 0.7)) * 3
        circle(cr, 15 + i * 9, 38 + dy, 2.8)
        paint(cr, INK, None)


# ---------------------------------------------------------------- tasks
def icon_task_done(cr, t):
    """Task finished: a green laptop screen with a big check mark."""
    rrect(cr, 7, 9, 34, 24, 4)
    paint(cr, hexc('#22253A'))
    rrect(cr, 3, 33, 42, 6, 3)
    paint(cr, hexc('#E3D9BF'))
    k = min(1.0, t * 2.5)                 # the check draws itself
    pts = [(15, 21), (21, 27), (33, 14)]
    if k < 0.4:
        a = k / 0.4
        seg = [pts[0], (pts[0][0] + (pts[1][0] - pts[0][0]) * a,
                        pts[0][1] + (pts[1][1] - pts[0][1]) * a)]
    else:
        a = (k - 0.4) / 0.6
        seg = [pts[0], pts[1], (pts[1][0] + (pts[2][0] - pts[1][0]) * a,
                                pts[1][1] + (pts[2][1] - pts[1][1]) * a)]
    line(cr, seg, GREEN, 3.6)
    tw = 0.7 + 0.3 * math.sin(t * 6)
    sparkle(cr, 42, 7, 5 * tw)


BUTTER = hexc('#FFD54F')
ANTENNA_STATES = {'evil': hexc('#FF3B4E'), 'sleep': GREY, 'hack': hexc('#39FF7A')}

# name -> (draw function, accent colour used for the robot's antenna)
ICONS = {
    'battery_low': (icon_battery_low, RED),
    'battery_charging': (icon_battery_charging, GREEN),
    'battery_full': (icon_battery_full, GREEN),
    'update': (icon_update, BLUE),
    'reboot': (icon_reboot, PURPLE),
    'mail': (icon_mail, ORANGE),
    'chat': (icon_chat, SKY),
    'wifi': (icon_wifi, GREEN),
    'wifi_off': (icon_wifi_off, RED),
    'download': (icon_download, GREEN),
    'calendar': (icon_calendar, RED),
    'alarm': (icon_alarm, ORANGE),
    'bell': (icon_bell, YELLOW),
    'warning': (icon_warning, YELLOW),
    'music': (icon_music, PINK),
    'camera': (icon_camera, PURPLE),
    'bluetooth': (icon_bluetooth, BLUE),
    'usb': (icon_usb, SKY),
    'heart': (icon_heart, PINK),
    # conversation
    'mic': (icon_mic, SKY),
    'thinking': (icon_thinking, YELLOW),
    # tasks
    'task_done': (icon_task_done, GREEN),
}


def icon_kinds():
    """Every icon a bubble can show: the built-in ones plus the characters' demands."""
    return frozenset(ICONS) | frozenset(REGISTRY.demand_icons())


def antenna_colour_for(antenna, alert_kind=''):
    """The antenna glows in the colour of whatever the robot is reporting."""
    if antenna == 'alert':
        if alert_kind in ICONS:
            return ICONS[alert_kind][1]
        demand = REGISTRY.demand_icons().get(alert_kind)
        if demand and demand[1]:
            return demand[1]
        return ICONS['bell'][1]
    return ANTENNA_STATES.get(antenna, BUTTER)


def draw_icon(cr, kind, t):
    cr.save()
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    if kind in ICONS:
        ICONS[kind][0](cr, t)
    else:
        demand = REGISTRY.demand_icons().get(kind)
        if demand:                       # drawn from the character's file
            safe_draw(demand[0], cr, {'t': t, '_palette': {}, 'evil': 0.0}, f'icon {kind}')
        else:
            ICONS['bell'][0](cr, t)
    cr.restore()
