r"""Draws the usage card (robo/core/usage_card.py) above Robo's head, in the
style of his speech bubbles: white, ink outline, a tail pointing at him.

    ┌──────────────────────────────┐
    │ Claude · Haiku 5.5           │
    │ Session              12%     │
    │ ███░░░░░░░░░░░░░░░░░░░░░     │
    │ Week                  9%     │
    │ ██░░░░░░░░░░░░░░░░░░░░░░     │
    └──────────────\/──────────────┘
"""
import cairo

from robo.core import layout

from .shapes import GREEN, INK, ORANGE, RED, WHITE, hexc, paint, rrect, speech_path

CARD_X, CARD_Y, CARD_W = 4, 4, layout.WINDOW_W - 8
PAD = 8
TITLE_H = 15
BAR_ROW_H = 23
BAR_H = 7
TRACK = hexc('#E3E8F2')
DIM = hexc('#6B7190')


def bar_color(used):
    return GREEN if used < 0.6 else ORANGE if used < 0.85 else RED


def card_height(card):
    rows = len(card.bars) if card.bars else 1
    return PAD + TITLE_H + rows * BAR_ROW_H - (0 if card.bars else 6) + PAD - 4


def _text(cr, x, y, text, size, bold=False, color=INK, max_w=None, right=False):
    cr.select_font_face('Sans', cairo.FONT_SLANT_NORMAL,
                        cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)
    cr.set_font_size(size)
    if max_w is not None:
        while text and cr.text_extents(text).x_advance > max_w:
            text = text[:-2] + '…' if len(text) > 2 else ''
    ext = cr.text_extents(text)
    cr.move_to(x - ext.x_advance if right else x, y)
    cr.set_source_rgba(*color)
    cr.show_text(text)
    return ext.x_advance


def draw_usage_card(cr, card, scale_k=1.0):
    """Draw `card` in window design units (the caller sets up scale and offset)."""
    if card is None or scale_k <= 0.01:
        return
    h = card_height(card)
    x, y, w = CARD_X, CARD_Y, CARD_W
    tip_x, tip_y = layout.GROUND_X, y + h + layout.BUBBLE_TAIL
    cr.save()
    cr.translate(tip_x, tip_y)              # grow out of the tail tip, like a bubble
    cr.scale(scale_k, scale_k)
    cr.translate(-tip_x, -tip_y)

    def outline():
        speech_path(cr, x, y, w, h, 14, tip_x, 16, layout.BUBBLE_TAIL)
    cr.save()
    cr.translate(0, 3)
    outline()
    cr.set_source_rgba(0.1, 0.12, 0.2, 0.18)
    cr.fill()
    cr.restore()
    outline()
    paint(cr, WHITE, INK, 2.4)

    inner_x, inner_w = x + PAD + 2, w - 2 * PAD - 4
    _text(cr, inner_x, y + PAD + 10, card.title, 11, bold=True, max_w=inner_w)
    row_y = y + PAD + TITLE_H
    if not card.bars:
        _text(cr, inner_x, row_y + 10, card.note, 9.5, color=DIM, max_w=inner_w)
    for label, used, detail in card.bars:
        pct = f'{round(used * 100)}%'
        pct_w = _text(cr, inner_x + inner_w, row_y + 10, pct, 10, bold=True, right=True)
        label_w = _text(cr, inner_x, row_y + 10, label, 9.5, max_w=inner_w - pct_w - 6)
        if detail:
            _text(cr, inner_x + label_w + 5, row_y + 10, detail, 8, color=DIM,
                  max_w=inner_w - label_w - pct_w - 12)
        by = row_y + 13
        rrect(cr, inner_x, by, inner_w, BAR_H, BAR_H / 2)
        paint(cr, TRACK, None)
        if used > 0:
            rrect(cr, inner_x, by, max(BAR_H, inner_w * used), BAR_H, BAR_H / 2)
            paint(cr, bar_color(used), None)
        rrect(cr, inner_x, by, inner_w, BAR_H, BAR_H / 2)
        paint(cr, None, INK, 1.2)
        row_y += BAR_ROW_H
    cr.restore()
