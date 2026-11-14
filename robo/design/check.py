"""Check character files: `python3 -m robo --check [FILE ...]`.

Loads each file, then draws it in every situation Robo can be in (walking,
evil, talking, sitting at the laptop, flying, every mood and gesture, its
demand icon and particles) and reports anything that went wrong: typos,
unknown colours, broken expressions. With no files it checks them all.
It also writes a contact sheet PNG next to each file you name, so you can
see your design without starting Robo.
"""
import logging
import os

import cairo

from .loader import LoadError, load_file
from .registry import REGISTRY

MOODS = ('normal', 'happy', 'surprised', 'sleep', 'evil', 'laugh', 'roar', 'wince', 'sing',
         'cat', 'sad', 'focus')


class _Collect(logging.Handler):
    def __init__(self):
        super().__init__(logging.WARNING)
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


def _poses(c):
    from robo.core.pose import Pose
    as_look = c.role == 'base'
    kw = dict(skin=c.id) if as_look else dict(costume=c.id)
    poses = [Pose(t=0.3, **kw),
             Pose(t=1.1, walking=True, phase=2.3, arms='swing', facing=-1, **kw),
             Pose(t=0.8, evil=1.0, mood='laugh', arms='scheme', antenna='evil', glow=0.7,
                  glitch=1.0, **kw),
             Pose(t=0.9, dangling=True, arms='up', mood='surprised', shadow=False, sweat=True, **kw),
             Pose(t=0.9, sit=1.0, arms='type', mood='focus', antenna='hack', glow=0.8, **kw),
             Pose(t=0.5, look=3, openness=0.4, tilt=0.1, talk=0.6, antenna='alert',
                  alert_kind='mail', glow=1, **kw)]
    poses += [Pose(t=0.6, mood=m, talk=0.0, **kw) for m in MOODS]
    if c.move:
        poses += [Pose(t=t, arms=c.move.gesture, mood=c.move.mood, **kw) for t in (0.4, 1.3)]
    for a in c.travel:
        poses.append(Pose(t=0.7, arms=a.gesture or 'fly', airborne=True, travel=a.kind,
                          cruising=True, lift=a.height, shadow=False, **kw))
        poses.append(Pose(t=0.7, arms=a.hover_gesture or 'hover', airborne=True, travel=a.kind,
                          dangling=a.kind == 'hang', shadow=False, **kw))
    return poses


HAND_SLOTS = ('front_hand',)     # the far hand's things may hide behind him
MIN_SHOWING = 0.35         # a prop in a hand must show at least this much


def _pixels(draw):
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 240, 280)
    cr = cairo.Context(surf)
    cr.translate(120, 250)
    draw(cr)
    surf.flush()
    return memoryview(surf.get_data()).cast('I')


def _prop_poses(c):
    """Where a held prop must show: standing, his move, travelling. (Not walking:
    the arms swing, so a prop passes behind him for a moment, which is fine.)"""
    poses = _poses(c)
    keep = [poses[0]]
    keep += [p for p in poses if c.move and p.arms == c.move.gesture]
    keep += [p for p in poses if p.travel]
    return keep


def hidden_props(c):
    """Problems for props drawn in front_hand (the near hand) that are mostly covered
    by the robot (the arms are painted behind the body unless the gesture says
    place: front / over_head). Measured: the prop drawn alone, compared with
    what changes in the full picture when the prop is left out."""
    from dataclasses import replace
    from robo.render.robot import draw_robot
    d = REGISTRY.design(c.id if c.role == 'base' else '', '' if c.role == 'base' else c.id)
    own = {s: [fl for fl in d.slots.get(s, ()) if fl[1].startswith(f'{c.id}.layers.')]
           for s in HAND_SLOTS}
    problems = []
    for slot in HAND_SLOTS:
        if not own[slot]:
            continue
        others = {s: [fl for fl in v if fl not in own[slot]] for s, v in d.slots.items()}
        variants = {'full': d, 'without': replace(d, slots=others),
                    'alone': replace(d, parts={}, slots={slot: own[slot]})}
        worst = None
        for pose in _prop_poses(c):
            px = {}
            try:
                for name, design in variants.items():
                    REGISTRY._designs[d.key] = design
                    px[name] = _pixels(lambda cr: draw_robot(cr, pose))
            finally:
                REGISTRY._designs[d.key] = d
            prop = [i for i, v in enumerate(px['alone']) if v >> 24]
            if len(prop) < 30:             # nothing much drawn in this pose
                continue
            showing = sum(1 for i in prop if px['full'][i] != px['without'][i]) / len(prop)
            name = 'standing' if pose.arms == 'rest' else f'doing {pose.arms}'
            if pose.travel:
                name = f'{pose.travel} ({pose.arms})'
            if showing < MIN_SHOWING and (worst is None or showing < worst[0]):
                worst = (showing, name)
        if worst:
            problems.append(
                f'layers.{slot}: what he holds is hidden behind his body or head when '
                f'{worst[1]} (only {worst[0]:.0%} shows). Arms are painted behind the '
                f'body: give the gesture place: front (or over_head when the arm is '
                f'raised), and hold the prop further out from the body')
    return problems


def check(paths=(), sheet=True, out=print):
    """Returns the number of problems found."""
    from robo.render.effects import draw_particles
    from robo.render.icons import draw_icon
    from robo.render.robot import draw_robot
    from robo.core.effects import Effects
    import random

    problems = 0
    if paths:
        for p in paths:
            REGISTRY.add_directory(os.path.dirname(os.path.abspath(p)))
    REGISTRY.reload()
    for path, err in REGISTRY.errors.items():
        if not paths or os.path.abspath(path) in {os.path.abspath(p) for p in paths}:
            out(f'✗ {err}')
            problems += 1
    targets = []
    for p in paths:
        try:
            targets.append(load_file(p).character)
        except LoadError:
            continue
    if not paths:
        targets = [REGISTRY.get(cid) for cid in REGISTRY.ids('base', 'costume', 'work')]

    from robo.render import interpreter
    handler = _Collect()
    root = logging.getLogger()
    others, root.handlers = root.handlers, [handler]      # report problems once, below
    try:
        for c in targets:
            c = REGISTRY.get(c.id) or c
            handler.messages.clear()
            interpreter._warned.clear()
            poses = _poses(c)
            cols = 8
            rows = (len(poses) + 1 + cols - 1) // cols
            surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 170 * cols, 220 * rows)
            cr = cairo.Context(surf)
            cr.set_source_rgb(0.93, 0.95, 0.98)
            cr.paint()
            for i, pose in enumerate(poses):
                cr.save()
                cr.translate((i % cols) * 170 + 85, (i // cols) * 220 + 200)
                draw_robot(cr, pose)
                cr.restore()
            if c.demand:
                i = len(poses)
                cr.save()
                cr.translate((i % cols) * 170 + 37, (i // cols) * 220 + 60)
                cr.scale(2, 2)
                for t in (0.2, 1.3, 2.9):
                    draw_icon(cr, c.demand, t)
                cr.restore()
            emitters = ([c.move.particles] if c.move and c.move.particles else []) + \
                [a.particles for a in c.travel if a.particles]
            fx = Effects(random.Random(1))
            for name in emitters:
                if REGISTRY.emitter(name) is None:
                    handler.messages.append(f'particles {name!r} are not defined in any file')
                for k in range(30):
                    fx.emit(name, k * 0.05, 0.05, 1)
            cr.save()
            cr.translate(85, 200)
            draw_particles(cr, fx.particles, 1.0)
            cr.restore()
            for g in ([c.move.gesture] if c.move else []) + \
                    [x for a in c.travel for x in (a.gesture, a.hover_gesture) if x]:
                if REGISTRY.design(c.id if c.role == 'base' else '', c.id).gestures.get(g) is None \
                        and REGISTRY.gesture(g) is None:
                    handler.messages.append(f'gesture {g!r} is not defined in any file')
            if c.role == 'costume':
                handler.messages.extend(hidden_props(c))
            msgs = sorted(set(handler.messages))
            problems += len(msgs)
            mark = '✓' if not msgs else '✗'
            out(f'{mark} {c.id} ({os.path.basename(c.source)}): '
                f'{"ok" if not msgs else str(len(msgs)) + " problem(s)"}')
            for m in msgs:
                out(f'    {m}')
            if sheet and paths and any(os.path.abspath(p) == os.path.abspath(c.source)
                                       for p in paths):
                png = os.path.splitext(c.source)[0] + '.preview.png'
                surf.write_to_png(png)
                out(f'    preview: {png}')
    finally:
        root.handlers = others
    return problems
