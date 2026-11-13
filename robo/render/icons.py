"""Cute vector icons for the speech bubble.

Every icon is a function `icon_xxx(cr, t)` that draws inside a 48x48 box;
`t` is the number of seconds since the bubble appeared, for animation.
To add an icon: write the function, add it to ICONS, and add its name to
robo.events.KINDS.
"""
import math

import cairo

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


# ---------------------------------------------------------------- dressed-up demands
SAND = hexc('#F3DCA8')
STONE = hexc('#E8B964')
ROBO_EYE = hexc('#7DF3FF')
BROWN = hexc('#A8693A')
AMBER = hexc('#F5B83D')
GRAPE = hexc('#9B5DE5')
OIL = hexc('#D9902B')


def icon_pyramid(cr, t):
    """Blocks drop in row by row; the finished pyramid has Robo's face on it."""
    circle(cr, 40, 8, 4.5)
    paint(cr, YELLOW, None)
    rrect(cr, 2, 38, 44, 6, 3)
    paint(cr, SAND, INK, 2)
    cycle = t % 4.0
    rows = min(4, int(cycle / 0.45))
    for r in range(rows):
        drop = max(0.0, 1 - (cycle - r * 0.45) / 0.2) * 8
        y = 31 - r * 7 - drop
        n = 4 - r
        x0 = 24 - n * 4.5
        for i in range(n):
            rrect(cr, x0 + i * 9, y, 9, 7, 1.5)
            paint(cr, STONE, INK, 1.8)
    if rows == 4 and cycle > 1.9:
        # gold capstone, his antenna and his little face: the pyramid of ME
        cr.move_to(19.5, 10)
        cr.line_to(28.5, 10)
        cr.line_to(24, 3.5)
        cr.close_path()
        paint(cr, YELLOW, INK, 1.8)
        line(cr, [(24, 3.5), (24, 0.5)], INK, 1.6)
        circle(cr, 24, 0, 1.8)
        paint(cr, RED, None)
        for ex in (20.5, 27.5):
            rrect(cr, ex - 1.4, 19, 2.8, 4, 1.4)
            paint(cr, ROBO_EYE, None)
        cr.new_path()
        cr.arc(24, 25.5, 2.2, 0.15 * math.pi, 0.85 * math.pi)
        paint(cr, None, ROBO_EYE, 1.4)
        tw = 0.6 + 0.4 * math.sin(t * 7)
        sparkle(cr, 8, 12, 4 * tw)
        sparkle(cr, 34, 18, 3 * (1.6 - tw))


def icon_horseshoe(cr, t):
    cr.save()
    cr.translate(24, 8)
    cr.rotate(math.sin(t * 3) * 0.18)
    cr.translate(-24, -8)

    def shoe():
        cr.new_path()
        cr.arc(24, 22, 12, -0.25, math.pi + 0.25)
    outlined_stroke(cr, shoe, GREY, 7, 10.5)
    for a in (0.25, 0.85, 2.3, 2.9):
        circle(cr, 24 + math.cos(a) * 12, 22 + math.sin(a) * 12, 1.2)
        paint(cr, INK, None)
    cr.restore()
    tw = 0.6 + 0.4 * math.sin(t * 6)
    sparkle(cr, 40, 10, 5 * tw)
    sparkle(cr, 8, 34, 3.5 * (1.6 - tw))


def icon_mead(cr, t):
    def handle():
        cr.new_path()
        cr.arc(32, 29, 7, -math.pi / 2, math.pi / 2)
    outlined_stroke(cr, handle, AMBER, 3, 6.5)
    rrect(cr, 9, 17, 23, 25, 4)
    paint(cr, AMBER)
    for y in (24, 35):
        line(cr, [(9, y), (32, y)], BROWN, 2)
    drip = (t * 0.8) % 1.0                  # foam sliding down the side
    rrect(cr, 27.5, 16, 5, 6 + drip * 12, 2.5)
    paint(cr, WHITE, INK, 1.8)
    for x, y, r in ((12, 16, 5), (18, 13, 5.5), (25, 14, 5.5), (30, 16, 4.5)):
        circle(cr, x, y, r)
        paint(cr, WHITE, INK, 1.8)
    for x, y, r in ((12, 16, 3.6), (18, 13, 4.1), (25, 14, 4.1), (30, 16, 3.1)):
        circle(cr, x, y, r)                 # hide the inner outlines
        paint(cr, WHITE, None)


def icon_receipt(cr, t):
    """A receipt that just keeps on unrolling."""
    length = 10 + min(1.0, (t % 3.2) / 2.2) * 28
    top, bottom = 5, 5 + length
    cr.move_to(13, top)
    cr.line_to(35, top)
    cr.line_to(35, bottom)
    x = 35.0
    while x > 13:                           # torn zig-zag edge
        cr.line_to(x - 2.75, bottom - 2.5)
        cr.line_to(max(13, x - 5.5), bottom)
        x -= 5.5
    cr.close_path()
    paint(cr, WHITE, INK, 2)
    y = top + 6
    while y < bottom - 6:
        line(cr, [(17, y), (31 if int(y) % 3 else 27, y)], GREY, 1.8)
        y += 4.5
    rrect(cr, 9, 2, 30, 6, 3)               # the roll
    paint(cr, CREAM, INK, 2)
    if length > 34:
        circle(cr, 34, 36, 7)
        paint(cr, RED, INK, 1.8)
        cr.select_font_face('Sans', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(10)
        ext = cr.text_extents('$')
        cr.move_to(34 - ext.width / 2 - ext.x_bearing, 36 - ext.height / 2 - ext.y_bearing)
        cr.set_source_rgba(*WHITE)
        cr.show_text('$')


def icon_oilcan(cr, t):
    def spout():
        cr.new_path()
        cr.move_to(28, 27)
        cr.line_to(41, 14)
    outlined_stroke(cr, spout, GREY, 3, 6)

    def handle():
        cr.new_path()
        cr.arc(9, 30, 6, math.pi / 2, math.pi * 1.5)
    outlined_stroke(cr, handle, RED, 2.6, 5.6)
    cr.move_to(13, 23)
    cr.line_to(16, 16)
    cr.line_to(22, 16)
    cr.line_to(25, 23)
    cr.close_path()
    paint(cr, RED)
    rrect(cr, 8, 22, 22, 19, 4)
    paint(cr, RED)
    circle(cr, 19, 31, 4)
    paint(cr, YELLOW, INK, 1.6)
    k = (t * 1.1) % 1.0                     # drip... drip...
    dy = 16 + k * k * 24
    cr.move_to(41, dy - 3.5)
    cr.curve_to(43.5, dy, 43.5, dy + 2.5, 41, dy + 2.5)
    cr.curve_to(38.5, dy + 2.5, 38.5, dy, 41, dy - 3.5)
    cr.close_path()
    paint(cr, OIL, INK, 1.4)


def icon_grapes(cr, t):
    cr.save()
    cr.translate(24, 6)
    cr.rotate(math.sin(t * 3) * 0.1)
    cr.translate(-24, -6)
    line(cr, [(24, 5), (24, 12)], BROWN, 2.6)
    cr.save()
    cr.translate(31, 9)
    cr.rotate(-0.5)
    ellipse(cr, 0, 0, 7, 3.5)
    cr.restore()
    paint(cr, GREEN)
    for row, n in enumerate((4, 3, 2, 1)):
        for i in range(n):
            cx = 24 - (n - 1) * 3.6 + i * 7.2
            cy = 16 + row * 6.5
            circle(cr, cx, cy, 4.3)
            paint(cr, GRAPE, INK, 1.8)
            circle(cr, cx - 1.4, cy - 1.4, 1.1)
            paint(cr, (1, 1, 1, 0.7), None)
    cr.restore()



def icon_cupcake(cr, t):
    dy = -abs(math.sin(t * 3)) * 1.5
    cr.save()
    cr.translate(0, dy)
    cr.move_to(12, 27)                        # striped wrapper
    cr.line_to(36, 27)
    cr.line_to(32.5, 43)
    cr.line_to(15.5, 43)
    cr.close_path()
    paint(cr, SKY)
    for x in (18, 22, 26, 30):
        line(cr, [(x, 29), (x - (x - 24) * 0.15, 41)], WHITE, 1.6)
    for x, y, rx, ry in ((24, 25, 14, 6), (24, 19, 10.5, 5.5), (24, 13.5, 6.5, 4.5)):
        ellipse(cr, x, y, rx, ry)
        paint(cr, hexc('#FFD1E8'))
    for (x, y), col in zip(((17, 24), (29, 22), (22, 18), (27, 15), (20, 26)),
                           (YELLOW, BLUE, GREEN, RED, PURPLE)):
        line(cr, [(x, y), (x + 2, y - 1)], col, 1.8)
    line(cr, [(24, 6), (27, 2)], BROWN, 1.6)
    circle(cr, 24, 7.5, 3.6)
    paint(cr, RED)
    cr.restore()


def icon_rocket(cr, t):
    dy = math.sin(t * 4) * 1.5
    cr.save()
    cr.translate(0, dy)
    flick = abs(math.sin(t * 20)) * 4
    cr.move_to(19.5, 36)                      # flame
    cr.curve_to(20, 42, 24, 44 + flick, 24, 46 + flick)
    cr.curve_to(24, 44 + flick, 28, 42, 28.5, 36)
    cr.close_path()
    paint(cr, ORANGE, INK, 1.6)
    cr.move_to(22, 36)
    cr.line_to(24, 41 + flick * 0.6)
    cr.line_to(26, 36)
    cr.close_path()
    paint(cr, YELLOW, None)
    for side in (-1, 1):                      # fins
        cr.move_to(24 + side * 6.5, 25)
        cr.line_to(24 + side * 13, 37)
        cr.line_to(24 + side * 6.5, 34)
        cr.close_path()
        paint(cr, RED)
    cr.move_to(24, 3)
    cr.curve_to(32, 9, 32.5, 24, 30.5, 34)
    cr.line_to(17.5, 34)
    cr.curve_to(15.5, 24, 16, 9, 24, 3)
    cr.close_path()
    paint(cr, WHITE)
    circle(cr, 24, 18, 4.6)
    paint(cr, SKY)
    cr.restore()
    sparkle(cr, 8, 12, 3.5 * (0.6 + 0.4 * math.sin(t * 6)))
    sparkle(cr, 41, 28, 3 * (0.6 + 0.4 * math.cos(t * 5)))


def icon_potion(cr, t):
    for i in range(3):                        # bubbles rising out of the bottle
        k = (t * 0.9 + i / 3) % 1.0
        circle(cr, 24 + math.sin(k * 6 + i) * 4, 9 - k * 9, 1.4 + k * 1.6)
        paint(cr, hexc('#D9B8FF'), INK, 1.2)
    rrect(cr, 19.5, 7, 9, 5, 1.5)              # cork
    paint(cr, BROWN, INK, 1.6)
    rrect(cr, 20.5, 11, 7, 9, 1.5)
    paint(cr, WHITE)
    circle(cr, 24, 30, 13)
    paint(cr, PURPLE)
    cr.save()
    circle(cr, 24, 30, 13)
    cr.clip()
    wave = math.sin(t * 4) * 1.2
    cr.move_to(10, 24 + wave)
    cr.curve_to(18, 21 - wave, 30, 27 + wave, 38, 24 - wave)
    cr.line_to(38, 17)
    cr.line_to(10, 17)
    cr.close_path()
    paint(cr, (1, 1, 1, 0.75), None)
    cr.restore()
    circle(cr, 24, 30, 13)
    paint(cr, None, INK, 2.4)
    ellipse(cr, 18.5, 33, 2, 3.5)
    paint(cr, (1, 1, 1, 0.55), None)
    sparkle(cr, 38, 40, 3.5 * (0.6 + 0.4 * math.sin(t * 7)))


def icon_treasure(cr, t):
    lift = abs(math.sin(t * 3)) * 3
    for x, col in ((16, YELLOW), (24, ORANGE), (31, YELLOW)):    # coins peeking out
        circle(cr, x, 24 - lift * 0.6, 3.6)
        paint(cr, col, INK, 1.4)
    rrect(cr, 7, 24, 34, 17, 3)
    paint(cr, BROWN)
    cr.save()
    cr.translate(0, -lift)
    cr.move_to(7, 24)
    cr.curve_to(7, 12, 41, 12, 41, 24)
    cr.close_path()
    paint(cr, BROWN)
    cr.restore()
    for x in (13, 35):
        line(cr, [(x, 24), (x, 41)], YELLOW, 2.4)
    rrect(cr, 21, 25, 6, 7, 1.5)
    paint(cr, YELLOW, INK, 1.4)
    tw = 0.6 + 0.4 * math.sin(t * 6)
    sparkle(cr, 9, 10, 4 * tw)
    sparkle(cr, 40, 8, 3 * (1.6 - tw))


def icon_kitten(cr, t):
    blink = (t % 3.0) < 0.15
    for side in (-1, 1):
        cr.move_to(24 + side * 13, 22)
        cr.line_to(24 + side * 12, 7)
        cr.line_to(24 + side * 3, 15)
        cr.close_path()
        paint(cr, ORANGE)
        cr.move_to(24 + side * 11, 18)
        cr.line_to(24 + side * 10.5, 11)
        cr.line_to(24 + side * 6, 15)
        cr.close_path()
        paint(cr, hexc('#FF9CC2'), None)
    ellipse(cr, 24, 27, 15, 12.5)
    paint(cr, ORANGE)
    for x in (18, 30):
        if blink:
            line(cr, [(x - 2.5, 26), (x + 2.5, 26)], INK, 2)
        else:
            ellipse(cr, x, 26, 2.8, 3.6)
            paint(cr, INK, None)
            circle(cr, x - 0.9, 24.6, 1.1)
            paint(cr, WHITE, None)
    cr.move_to(22.5, 30)
    cr.line_to(25.5, 30)
    cr.line_to(24, 31.8)
    cr.close_path()
    paint(cr, hexc('#FF7AB6'), None)
    cr.new_path()
    cr.arc(22, 32, 2, 0, math.pi)
    cr.new_sub_path()
    cr.arc(26, 32, 2, 0, math.pi)
    paint(cr, None, INK, 1.4)
    for side in (-1, 1):
        for dy in (-1.5, 1.5):
            line(cr, [(24 + side * 8, 31 + dy * 0.3), (24 + side * 17, 30 + dy * 1.6)], INK, 1)
    for i in range(2):                        # little "help!" pleas
        k = (t * 0.8 + i / 2) % 1.0
        sparkle(cr, 40 - i * 32, 10 - k * 6, 3 * (1 - k))


def icon_fish(cr, t):
    cr.save()
    cr.translate(22, 24)
    cr.rotate(math.sin(t * 6) * 0.12)
    cr.translate(-22, -24)
    cr.move_to(32, 24)                        # tail
    cr.line_to(42, 16)
    cr.line_to(41, 32)
    cr.close_path()
    paint(cr, BLUE)
    ellipse(cr, 21, 24, 14, 9)
    paint(cr, SKY)
    cr.new_path()
    cr.arc(26, 24, 7, math.pi * 0.6, math.pi * 1.4)
    paint(cr, None, BLUE, 1.6)
    circle(cr, 14, 22, 2.6)
    paint(cr, WHITE, INK, 1.4)
    circle(cr, 13.5, 22, 1.1)
    paint(cr, INK, None)
    cr.restore()
    for i in range(3):
        k = (t * 0.7 + i / 3) % 1.0
        circle(cr, 6 + i * 2, 18 - k * 14, 1.2 + k * 1.4)
        paint(cr, None, BLUE, 1.2)



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
    # demands made while dressed up (see robo.core.characters)
    'pyramid': (icon_pyramid, YELLOW),
    'horseshoe': (icon_horseshoe, GREY),
    'mead': (icon_mead, ORANGE),
    'receipt': (icon_receipt, GREEN),
    'oilcan': (icon_oilcan, RED),
    'grapes': (icon_grapes, PURPLE),
    'cupcake': (icon_cupcake, PINK),
    'rocket': (icon_rocket, RED),
    'potion': (icon_potion, PURPLE),
    'treasure': (icon_treasure, YELLOW),
    'kitten': (icon_kitten, ORANGE),
    'fish': (icon_fish, BLUE),
    # conversation
    'mic': (icon_mic, SKY),
    'thinking': (icon_thinking, YELLOW),
    # tasks
    'task_done': (icon_task_done, GREEN),
}


def draw_icon(cr, kind, t):
    fn = ICONS.get(kind, ICONS['bell'])[0]
    cr.save()
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    fn(cr, t)
    cr.restore()
