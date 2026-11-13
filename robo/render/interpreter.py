"""Turns the drawings in character files into Cairo drawing functions.

A drawing is a list of shapes. Every shape is a mapping with exactly one
"shape key" plus optional paint, transform and control keys:

  shape keys
    rect: [x, y, w, h]  (r: corner radius)     circle: [cx, cy, r]
    ellipse: [cx, cy, rx, ry]                  arc: [cx, cy, r, from, to]  (negative: true)
    poly: [[x, y], ...]   closed polygon       line: [[x, y], ...]  open polyline
    path: "M x y L x y C x1 y1 x2 y2 x y A cx cy r from to N ... S Z"
    star: [cx, cy, r]  (points: 5, inner: 0.45)
    sparkle: [x, y, r]                         heart: [x, y, size]
    text: "$"  (at: [x, y], size, font, bold, center)
    group: [shapes]     children share transforms / clip / alpha
    compound: [shapes]  children become ONE path, painted once (even_odd: true for holes)
    choose: [shapes]    draws the first child whose `if` is true

  paint keys
    fill: colour | {stripes: [colour, colour], step, origin}
                 | {linear: [x0, y0, x1, y1], stops: [[0, colour], [1, colour]]}
                 | {radial: [cx, cy, r0, r1], stops: [...]}
    stroke: colour (default: ink, or none for text)   lw: line width (default 2.6)
    rope: [colour, inner, outer]   thick ink outline with a coloured line on top

  control keys
    if: condition        vars: {name: expression}        for: {name: [values]}
    repeat: n (sets i)   translate: [x, y]   rotate: angle   scale: s or [sx, sy]
    clip: shape(s) (group only)   alpha: 0..1 (group only)

On a group, transforms also scale line widths; on any other shape they only
move the path. Every number may be an expression (see robo.design.expr).

Colours: "#RRGGBB", "#RRGGBBAA", a palette name, [colour, alpha],
{mix: [a, b], k: expr} or {pick: [a, b, ...], i: expr}, or none.
"""
import logging
import math
import re

import cairo

from robo.design.expr import ExprError, compile_expr

from .shapes import (BLUE, CARD, CREAM, GREEN, GREY, INK, LW, ORANGE, PINK, PURPLE, RED, SKY,
                     WHITE, YELLOW, ellipse, heart_path, hexc, rrect)

log = logging.getLogger(__name__)

BUILTIN_COLOURS = {
    'ink': INK, 'white': WHITE, 'black': hexc('#000000'), 'red': RED, 'green': GREEN,
    'yellow': YELLOW, 'blue': BLUE, 'orange': ORANGE, 'pink': PINK, 'purple': PURPLE,
    'grey': GREY, 'gray': GREY, 'card': CARD, 'sky': SKY, 'cream': CREAM,
}
MISSING = (1.0, 0.0, 1.0, 1.0)        # magenta: a colour name nobody defined

SHAPE_KEYS = ('rect', 'circle', 'ellipse', 'arc', 'poly', 'line', 'path', 'star', 'sparkle',
              'heart', 'text', 'group', 'compound', 'choose')
OTHER_KEYS = {'if', 'vars', 'for', 'repeat', 'translate', 'rotate', 'scale', 'clip', 'alpha',
              'fill', 'stroke', 'lw', 'rope', 'even_odd', 'r', 'negative', 'points', 'inner',
              'at', 'size', 'font', 'bold', 'center', 'note'}


class DrawingError(ValueError):
    pass


_warned = set()


def warn_once(key, msg, *args):
    if key not in _warned:
        _warned.add(key)
        log.warning(msg, *args)


# ---------------------------------------------------------------- colours
def parse_hex(text):
    h = text.lstrip('#')
    if not re.fullmatch(r'[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?', h):
        raise DrawingError(f'bad colour {text!r}')
    a = int(h[6:8], 16) / 255 if len(h) == 8 else 1.0
    return hexc(h[:6], a)


def compile_palette(spec, where):
    """{name: colour} -> {name: fn(env) -> rgba}. A value may be
    {good: colour, evil: colour}: it fades from one to the other as he turns evil."""
    out = {}
    for name, value in (spec or {}).items():
        out[name] = _palette_entry(value, f'{where}.{name}')
    return out


def _palette_entry(value, where):
    if isinstance(value, dict) and ('good' in value or 'evil' in value):
        good = _palette_entry(value.get('good', '#FF00FF'), where)
        evil = _palette_entry(value['evil'], where) if 'evil' in value else None
        return EvilColour(good, evil)
    if isinstance(value, str):
        c = parse_hex(value)
        return lambda env, c=c: c
    if isinstance(value, (list, tuple)) and len(value) == 2:
        c = parse_hex(value[0])
        a = _expr(value[1], where)
        return lambda env: c[:3] + (a(env),)
    raise DrawingError(f'{where}: a palette colour is "#RRGGBB", ["#RRGGBB", alpha] '
                       f'or {{good: ..., evil: ...}}')


class EvilColour:
    """A palette colour that blends to its evil version (keeps working when a
    costume recolours only the good side)."""

    def __init__(self, good, evil):
        self.good, self.evil = good, evil

    def with_good(self, good):
        return EvilColour(good, self.evil)

    def __call__(self, env):
        g = self.good(env)
        if self.evil is None:
            return g
        k = env.get('evil', 0.0)
        if k <= 0:
            return g
        e = self.evil(env)
        return tuple(a + (b - a) * k for a, b in zip(g, e))


def compile_colour(spec, ctx, where):
    """Colour spec -> fn(env) -> rgba (or None for 'none')."""
    if spec is None or spec == 'none':
        return None
    if isinstance(spec, str):
        if spec.startswith('#'):
            c = parse_hex(spec)
            return lambda env: c
        local = ctx.palette.get(spec)
        if local is not None:
            return local
        builtin = BUILTIN_COLOURS.get(spec)

        def lookup(env, name=spec, builtin=builtin):
            fn = env['_palette'].get(name)
            if fn is not None:
                return fn(env)
            if builtin is not None:
                return builtin
            warn_once(('colour', ctx.file, name), '%s: unknown colour %r', ctx.file, name)
            return MISSING
        return lookup
    if isinstance(spec, (list, tuple)) and len(spec) == 2:
        base = compile_colour(spec[0], ctx, where)
        a = _expr(spec[1], where)
        return lambda env: base(env)[:3] + (a(env),)
    if isinstance(spec, dict) and 'mix' in spec:
        a, b = (compile_colour(c, ctx, where) for c in spec['mix'])
        k = _expr(spec.get('k', 0.5), where)

        def mix(env):
            ca, cb, kk = a(env), b(env), k(env)
            return tuple(x + (y - x) * kk for x, y in zip(ca, cb))
        return mix
    if isinstance(spec, dict) and 'pick' in spec:
        options = [compile_colour(c, ctx, where) for c in spec['pick']]
        i = _expr(spec.get('i', 0), where)
        return lambda env: options[int(i(env)) % len(options)](env)
    raise DrawingError(f'{where}: bad colour {spec!r}')


# ---------------------------------------------------------------- helpers
class Ctx:
    """What a drawing is compiled against: its file and that file's palette."""

    def __init__(self, file, palette):
        self.file = file
        self.palette = palette


def _expr(value, where):
    try:
        return compile_expr(value)
    except ExprError as e:
        raise DrawingError(f'{where}: {e}') from None


def _exprs(values, n, where):
    if not isinstance(values, (list, tuple)) or (n is not None and len(values) != n):
        raise DrawingError(f'{where}: expected a list of {n} numbers')
    return [_expr(v, f'{where}[{i}]') for i, v in enumerate(values)]


def _points(values, where):
    if not isinstance(values, (list, tuple)) or len(values) < 2:
        raise DrawingError(f'{where}: expected a list of [x, y] points')
    return [_exprs(p, 2, f'{where}[{i}]') for i, p in enumerate(values)]


# ---------------------------------------------------------------- paths
_TOKEN = re.compile(r'\{[^}]*\}|[^\s,{}]+')
_ARITY = {'M': 2, 'L': 2, 'C': 6, 'A': 5, 'N': 5, 'S': 0, 'Z': 0}


def compile_path(text, where):
    """'M x y L x y C ...' -> builder(cr, env). Commands are single capital
    letters; arguments are numbers, expressions without spaces, or {any expression}."""
    tokens = _TOKEN.findall(text)
    ops, i = [], 0
    while i < len(tokens):
        cmd = tokens[i]
        if cmd not in _ARITY:
            raise DrawingError(f'{where}: expected a path command (M L C A N S Z), got {cmd!r}')

        i += 1
        n = _ARITY[cmd]
        while True:
            args = []
            for _ in range(n):
                if i >= len(tokens) or tokens[i] in _ARITY:
                    raise DrawingError(f'{where}: {cmd} needs {n} numbers')
                tok = tokens[i]
                if len(tok) == 1 and tok.isupper():
                    raise DrawingError(f'{where}: unknown path command {tok!r} '
                                       f'(use M L C A N S Z)')
                args.append(_expr(tok[1:-1] if tok.startswith('{') else tok, where))
                i += 1
            ops.append((cmd, args))
            if n == 0 or i >= len(tokens) or tokens[i] in _ARITY:
                break

    def build(cr, env):
        for cmd, args in ops:
            v = [a(env) for a in args]
            if cmd == 'M':
                cr.move_to(*v)
            elif cmd == 'L':
                cr.line_to(*v)
            elif cmd == 'C':
                cr.curve_to(*v)
            elif cmd == 'A':
                cr.arc(*v)
            elif cmd == 'N':
                cr.arc_negative(*v)
            elif cmd == 'S':
                cr.new_sub_path()
            else:
                cr.close_path()
    return build


def _star_path(cr, cx, cy, r, points, inner):
    cr.new_sub_path()
    for i in range(points * 2):
        a = -math.pi / 2 + i * math.pi / points
        rr = r if i % 2 == 0 else r * inner
        cr.line_to(cx + math.cos(a) * rr, cy + math.sin(a) * rr)
    cr.close_path()


def _sparkle_path(cr, x, y, r):
    cr.move_to(x, y - r)
    cr.curve_to(x, y, x, y, x + r, y)
    cr.curve_to(x, y, x, y, x, y + r)
    cr.curve_to(x, y, x, y, x - r, y)
    cr.curve_to(x, y, x, y, x, y - r)
    cr.close_path()


# ---------------------------------------------------------------- shapes
def compile_drawing(spec, ctx, where='drawing'):
    """A list of shapes (or one shape) -> draw(cr, env)."""
    if spec is None:
        return _nothing
    if isinstance(spec, dict):
        spec = [spec]
    if not isinstance(spec, list):
        raise DrawingError(f'{where}: expected a list of shapes')
    shapes = [compile_shape(s, ctx, f'{where}[{i}]') for i, s in enumerate(spec)]
    if len(shapes) == 1:
        return shapes[0].draw

    def draw(cr, env):
        for s in shapes:
            s.draw(cr, env)
    return draw


def _nothing(cr, env):
    pass


class Shape:
    """draw(cr, env) paints it; path(cr, env) only adds it to the current path
    (used by compound shapes and clips)."""
    __slots__ = ('draw', 'path', 'cond')


def compile_shape(spec, ctx, where):
    if not isinstance(spec, dict):
        raise DrawingError(f'{where}: a shape must be a mapping, got {spec!r}')
    kinds = [k for k in SHAPE_KEYS if k in spec]
    if len(kinds) != 1:
        raise DrawingError(f'{where}: a shape needs exactly one of {", ".join(SHAPE_KEYS)}')
    kind = kinds[0]
    unknown = set(spec) - OTHER_KEYS - {kind}
    if unknown:
        raise DrawingError(f'{where}: unknown key(s) {", ".join(sorted(unknown))}')
    where = f'{where}.{kind}'

    if kind == 'group':
        inner = _group(spec, ctx, where)
        path = _group_path(spec, ctx, where)
    elif kind == 'choose':
        inner, path = _choose(spec, ctx, where)
    else:
        path = _path_builder(kind, spec, ctx, where)
        path = _with_path_transform(path, spec, where)
        inner = _painter(path, spec, ctx, where, text=kind == 'text')

    shape = Shape()
    shape.cond = _expr(spec['if'], f'{where}.if') if 'if' in spec else None
    shape.draw = _controls(inner, spec, shape.cond, where)
    shape.path = _controls(path, spec, shape.cond, where)
    return shape


def _controls(fn, spec, cond, where):
    """Wrap fn with `vars`, `for` / `repeat` and `if`."""
    if 'vars' in spec:
        if not isinstance(spec['vars'], dict):
            raise DrawingError(f'{where}.vars: expected a mapping of name: expression')
        defs = [(k, _expr(v, f'{where}.vars.{k}')) for k, v in spec['vars'].items()]
        body = fn

        def fn(cr, env, body=body):
            env = dict(env)
            for k, e in defs:
                env[k] = e(env)
            body(cr, env)
    if 'repeat' in spec:
        count = _expr(spec['repeat'], f'{where}.repeat')
        inner = fn

        def fn(cr, env, inner=inner):
            for i in range(min(int(count(env)), 500)):
                e = dict(env)
                e['i'] = i
                inner(cr, e)
    if 'for' in spec:                            # outside `repeat` when both are given
        loops = spec['for']
        if not isinstance(loops, dict) or len(loops) != 1:
            raise DrawingError(f'{where}.for: expected {{name: [values]}}')
        (name, values), = loops.items()
        values = _exprs(values, None, f'{where}.for.{name}')
        inner = fn

        def fn(cr, env, inner=inner):
            for v in values:
                e = dict(env)
                e[name] = v(env)
                inner(cr, e)
    if cond is not None:
        body = fn
        if cond.code is None:                    # constant condition
            return body if cond.const else _nothing

        def fn(cr, env, body=body):
            if cond(env):
                body(cr, env)
    return fn


def _transforms(spec, where):
    """translate / rotate / scale -> apply(cr, env), or None."""
    steps = []
    if 'translate' in spec:
        tx, ty = _exprs(spec['translate'], 2, f'{where}.translate')
        steps.append(lambda cr, env: cr.translate(tx(env), ty(env)))
    if 'rotate' in spec:
        a = _expr(spec['rotate'], f'{where}.rotate')
        steps.append(lambda cr, env: cr.rotate(a(env)))
    if 'scale' in spec:
        s = spec['scale']
        if isinstance(s, (list, tuple)):
            sx, sy = _exprs(s, 2, f'{where}.scale')
        else:
            sx = sy = _expr(s, f'{where}.scale')
        steps.append(lambda cr, env: cr.scale(sx(env) or 1e-6, sy(env) or 1e-6))
    if not steps:
        return None

    def apply(cr, env):
        for step in steps:
            step(cr, env)
    return apply


def _with_path_transform(path, spec, where):
    tf = _transforms(spec, where)
    if tf is None:
        return path

    def transformed(cr, env):
        cr.save()
        tf(cr, env)
        path(cr, env)
        cr.restore()                 # the path stays; line widths are not scaled
    return transformed


def _path_builder(kind, spec, ctx, where):
    v = spec[kind]
    if kind == 'rect':
        x, y, w, h = _exprs(v, 4, where)
        r = _expr(spec.get('r', 0), f'{where}.r')

        def build(cr, env):
            rr = r(env)
            if rr > 0:
                rrect(cr, x(env), y(env), w(env), h(env), rr)
            else:
                cr.rectangle(x(env), y(env), w(env), h(env))
        return build
    if kind == 'circle':
        cx, cy, r = _exprs(v, 3, where)

        def build(cr, env):
            cr.new_sub_path()
            cr.arc(cx(env), cy(env), max(0.0, r(env)), 0, 2 * math.pi)
        return build
    if kind == 'ellipse':
        cx, cy, rx, ry = _exprs(v, 4, where)
        return lambda cr, env: ellipse(cr, cx(env), cy(env), rx(env) or 1e-6, ry(env) or 1e-6)
    if kind == 'arc':
        cx, cy, r, a1, a2 = _exprs(v, 5, where)
        neg = bool(spec.get('negative'))

        def build(cr, env):
            (cr.arc_negative if neg else cr.arc)(cx(env), cy(env), max(0.0, r(env)),
                                                 a1(env), a2(env))
        return build
    if kind in ('poly', 'line'):
        pts = _points(v, where)
        close = kind == 'poly'

        def build(cr, env):
            (x0, y0), rest = pts[0], pts[1:]
            cr.move_to(x0(env), y0(env))
            for px, py in rest:
                cr.line_to(px(env), py(env))
            if close:
                cr.close_path()
        return build
    if kind == 'path':
        if not isinstance(v, str):
            raise DrawingError(f'{where}: a path is a string like "M 0 0 L 10 0 Z"')
        return compile_path(v, where)
    if kind == 'star':
        cx, cy, r = _exprs(v, 3, where)
        n = int(spec.get('points', 5))
        inner = _expr(spec.get('inner', 0.45), f'{where}.inner')
        return lambda cr, env: _star_path(cr, cx(env), cy(env), r(env), n, inner(env))
    if kind == 'sparkle':
        x, y, r = _exprs(v, 3, where)
        return lambda cr, env: _sparkle_path(cr, x(env), y(env), r(env))
    if kind == 'heart':
        x, y, s = _exprs(v, 3, where)
        return lambda cr, env: heart_path(cr, x(env), y(env), s(env))
    if kind == 'text':
        return _text_builder(spec, where)
    if kind == 'compound':
        parts = [compile_shape(s, ctx, f'{where}[{i}]') for i, s in enumerate(_list(v, where))]

        def build(cr, env):
            for p in parts:
                p.path(cr, env)
        return build
    raise DrawingError(f'{where}: unknown shape')


def _text_builder(spec, where):
    text = spec['text']
    if not isinstance(text, str):
        text = str(text)
    x, y = _exprs(spec.get('at', [0, 0]), 2, f'{where}.at')
    size = _expr(spec.get('size', 10), f'{where}.size')
    font = str(spec.get('font', 'Sans'))
    weight = cairo.FONT_WEIGHT_BOLD if spec.get('bold', True) else cairo.FONT_WEIGHT_NORMAL
    center = bool(spec.get('center', False))

    def build(cr, env):
        cr.select_font_face(font, cairo.FONT_SLANT_NORMAL, weight)
        cr.set_font_size(max(0.1, size(env)))
        px, py = x(env), y(env)
        if center:
            ext = cr.text_extents(text)
            px -= ext.width / 2 + ext.x_bearing
            py -= ext.height / 2 + ext.y_bearing
        cr.move_to(px, py)
        cr.text_path(text)
    return build


def _list(v, where):
    if isinstance(v, dict):
        return [v]
    if not isinstance(v, list):
        raise DrawingError(f'{where}: expected a list of shapes')
    return v


def _group(spec, ctx, where):
    body = compile_drawing(_list(spec['group'], where), ctx, where)
    tf = _transforms(spec, where)
    clip = None
    if 'clip' in spec:
        clips = [compile_shape(s, ctx, f'{where}.clip[{i}]')
                 for i, s in enumerate(_list(spec['clip'], f'{where}.clip'))]

        def clip(cr, env):
            cr.new_path()
            for c in clips:
                c.path(cr, env)
            cr.clip()
    alpha = _expr(spec['alpha'], f'{where}.alpha') if 'alpha' in spec else None

    def draw(cr, env):
        cr.save()
        try:
            if tf:
                tf(cr, env)
            if clip:
                clip(cr, env)
            if alpha is not None:
                a = alpha(env)
                if a <= 0.001:
                    return
                cr.push_group()
                try:
                    body(cr, env)
                finally:
                    cr.pop_group_to_source()
                cr.paint_with_alpha(min(1.0, a))
            else:
                body(cr, env)
        finally:
            cr.restore()
    return draw


def _group_path(spec, ctx, where):
    shapes = [compile_shape(s, ctx, f'{where}[{i}]')
              for i, s in enumerate(_list(spec['group'], where))]
    tf = _transforms(spec, where)

    def path(cr, env):
        cr.save()
        if tf:
            tf(cr, env)
        for s in shapes:
            s.path(cr, env)
        cr.restore()
    return path


def _choose(spec, ctx, where):
    options = [compile_shape(s, ctx, f'{where}[{i}]')
               for i, s in enumerate(_list(spec['choose'], where))]

    def pick(env):
        for o in options:
            if o.cond is None or o.cond(env):
                return o
        return None

    def draw(cr, env):
        o = pick(env)
        if o is not None:
            o.draw(cr, env)

    def path(cr, env):
        o = pick(env)
        if o is not None:
            o.path(cr, env)
    return draw, path


# ---------------------------------------------------------------- paint
def _painter(path, spec, ctx, where, text=False):
    lw = _expr(spec.get('lw', LW), f'{where}.lw')
    even_odd = bool(spec.get('even_odd'))

    if 'rope' in spec:
        rope = spec['rope']
        if not isinstance(rope, (list, tuple)) or len(rope) != 3:
            raise DrawingError(f'{where}.rope: expected [colour, inner width, outer width]')
        colour = compile_colour(rope[0], ctx, f'{where}.rope')
        inner, outer = _expr(rope[1], where), _expr(rope[2], where)

        def draw(cr, env):
            for c, w in ((INK, outer(env)), (colour(env), inner(env))):
                cr.new_path()
                path(cr, env)
                cr.set_source_rgba(*c)
                cr.set_line_width(w)
                cr.stroke()
        return draw

    fill_spec = spec.get('fill')
    fill = stripes = gradient = None
    if isinstance(fill_spec, dict) and 'stripes' in fill_spec:
        stripes = _stripes(fill_spec, ctx, f'{where}.fill')
    elif isinstance(fill_spec, dict) and ('linear' in fill_spec or 'radial' in fill_spec):
        gradient = _gradient(fill_spec, ctx, f'{where}.fill')
    elif fill_spec is not None:
        fill = compile_colour(fill_spec, ctx, f'{where}.fill')
    if 'stroke' in spec:
        stroke = compile_colour(spec['stroke'], ctx, f'{where}.stroke')
    elif text and (fill or stripes or gradient):
        stroke = None
    else:
        stroke = lambda env: INK          # noqa: E731

    def draw(cr, env):
        cr.new_path()
        path(cr, env)
        if even_odd:
            cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
        if stripes is not None:
            stripes(cr, env, path)
        elif gradient is not None:
            cr.set_source(gradient(env))
            cr.fill_preserve() if stroke else cr.fill()
        elif fill is not None:
            c = fill(env)
            if c is not None:
                cr.set_source_rgba(*c)
                cr.fill_preserve() if stroke else cr.fill()
        if even_odd:
            cr.set_fill_rule(cairo.FILL_RULE_WINDING)
        if stroke is not None:
            c = stroke(env)
            if c is not None:
                cr.set_source_rgba(*c)
                cr.set_line_width(lw(env))
                cr.stroke()
                return
        cr.new_path()
    return draw


def _stripes(spec, ctx, where):
    colours = spec['stripes']
    if not isinstance(colours, (list, tuple)) or len(colours) != 2:
        raise DrawingError(f'{where}.stripes: expected [base colour, stripe colour]')
    base, stripe = (compile_colour(c, ctx, where) for c in colours)
    step = _expr(spec.get('step', 4), f'{where}.step')
    origin = _expr(spec.get('origin', 0), f'{where}.origin')

    def fill(cr, env, path):
        cr.save()
        cr.clip_preserve()
        cr.set_source_rgba(*base(env))
        cr.fill()
        x1, y1, x2, y2 = cr.clip_extents()
        s, o = max(0.5, step(env)), origin(env)
        k = math.floor((y1 - o) / s)
        y = o + k * s
        cr.set_source_rgba(*stripe(env))
        while y < y2:
            if k % 2:
                cr.rectangle(x1, y, x2 - x1, s)
            y += s
            k += 1
        cr.fill()
        cr.restore()
        cr.new_path()
        path(cr, env)                      # path again, for the outline
    return fill


def _gradient(spec, ctx, where):
    stops = []
    for i, st in enumerate(spec.get('stops', [])):
        if not isinstance(st, (list, tuple)) or len(st) != 2:
            raise DrawingError(f'{where}.stops[{i}]: expected [offset, colour]')
        stops.append((_expr(st[0], where), compile_colour(st[1], ctx, where)))
    if 'linear' in spec:
        x0, y0, x1, y1 = _exprs(spec['linear'], 4, f'{where}.linear')

        def make(env):
            return cairo.LinearGradient(x0(env), y0(env), x1(env), y1(env))
    else:
        cx, cy, r0, r1 = _exprs(spec['radial'], 4, f'{where}.radial')

        def make(env):
            x, y = cx(env), cy(env)
            return cairo.RadialGradient(x, y, max(0.0, r0(env)), x, y, max(0.01, r1(env)))

    def gradient(env):
        g = make(env)
        for off, col in stops:
            g.add_color_stop_rgba(off(env), *col(env))
        return g
    return gradient


def safe_draw(fn, cr, env, key):
    """Run a compiled drawing; a broken character file never crashes Robo."""
    cr.save()
    try:
        fn(cr, env)
    except Exception as e:                # noqa: BLE001  (user files can do anything wrong)
        warn_once(('draw', key, str(e)), 'character file %s: %s', key, e)
    finally:
        cr.restore()
