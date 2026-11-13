"""Reading one character file.

Character files are YAML (or JSON) and live in robo/characters/ (built in)
and ~/.config/robo/characters/ (yours; same id = replaces the built-in one).
See robo/characters/README.md for the format.

load_file(path) -> CharacterFile: the behaviour (a model.Character) plus the
compiled drawings (parts, outfit layers, gestures, particles, demand icon).
"""
import json
import os
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional

from robo.render.interpreter import (Ctx, DrawingError, compile_colour, compile_drawing,
                                     compile_palette)

from .expr import ExprError, compile_expr
from .model import LINE_KINDS, ROLES, TRAVEL_KINDS, WEAR_SITUATIONS, Character, Move, Travel

try:
    import yaml
except ImportError:                  # JSON files still work without PyYAML
    yaml = None

EXTENSIONS = ('.yaml', '.yml', '.json')

# Robot parts a base file draws, in the order they are painted (see robo/render/robot.py).
PARTS = ('shadow', 'legs', 'arm', 'hand', 'torso', 'head_back', 'head', 'face', 'overlay',
         'antenna')
# Outfit layers a costume can add (same order idea; see the README).
SLOTS = ('behind', 'body', 'behind_head', 'face', 'head', 'front', 'ground',
         'front_hand', 'back_hand', 'anchor', 'tether')
GESTURE_PLACES = ('behind', 'front', 'over_head')
RIG_KEYS = ('shoulder', 'arm_length', 'neck', 'sit_drop', 'head_top', 'antenna_y')
TOP_KEYS = {'id', 'name', 'role', 'base', 'order', 'words', 'demand', 'move', 'walk', 'travel',
            'rig', 'palette', 'recolor', 'parts', 'layers', 'antenna_y', 'gestures',
            'particles', 'about', 'author', 'personality', 'hobbies', 'wear'}
PERSONALITY_LISTS = ('traits', 'likes', 'dislikes', 'quirks')
GLYPHS = ('note', 'spark', 'star', 'magic', 'heart', 'text')


class LoadError(ValueError):
    pass


@dataclass
class Gesture:
    back: object                      # Expr: back arm angle (0 = hanging down)
    front: object                     # Expr: front arm angle
    place: str = 'behind'             # where the arms go: behind / front / over_head
    head_x: Optional[object] = None   # Expr: slide the head sideways


@dataclass
class Emitter:
    rate: float
    life: object
    at: tuple
    velocity: tuple
    defs: tuple = ()                  # (name, Expr) evaluated before the rest
    glyph: str = 'spark'
    text: str = ''
    colours: tuple = ()
    size: Optional[object] = None
    draw: Optional[Callable] = None


@dataclass
class CharacterFile:
    character: Character
    palette: Dict[str, Callable] = field(default_factory=dict)
    recolor: Dict[str, Callable] = field(default_factory=dict)
    parts: Dict[str, Callable] = field(default_factory=dict)
    layers: Dict[str, Callable] = field(default_factory=dict)
    gestures: Dict[str, Gesture] = field(default_factory=dict)
    particles: Dict[str, Emitter] = field(default_factory=dict)
    rig: dict = field(default_factory=dict)
    antenna_y: Optional[float] = None
    icon: Optional[Callable] = None   # demand icon drawing
    icon_colour: Optional[tuple] = None
    mtime: float = 0.0

    @property
    def id(self):
        return self.character.id


def read_data(path):
    with open(path, encoding='utf-8') as f:
        text = f.read()
    if path.endswith('.json'):
        return json.loads(text)
    if yaml is None:
        raise LoadError('PyYAML is not installed (sudo apt install python3-yaml); '
                        'use a .json file instead')
    return yaml.safe_load(text)


def load_file(path):
    name = os.path.basename(path)
    try:
        data = read_data(path)
    except (OSError, ValueError) as e:
        raise LoadError(f'{name}: {e}') from None
    except Exception as e:            # yaml.YAMLError
        raise LoadError(f'{name}: {e}') from None
    if not isinstance(data, dict):
        raise LoadError(f'{name}: expected a mapping at the top of the file')
    try:
        cf = parse(data, name, default_id=os.path.splitext(name)[0])
    except (DrawingError, ExprError, LoadError) as e:
        msg = str(e)
        raise LoadError(msg if msg.startswith(name) else f'{name}: {msg}') from None
    except (TypeError, AttributeError, KeyError) as e:     # wrong kind of value somewhere
        raise LoadError(f'{name}: something has the wrong type ({e})') from None
    cf.mtime = os.stat(path).st_mtime
    cf.character = _replace(cf.character, source=path)
    return cf


def _replace(c, **kw):
    from dataclasses import replace
    return replace(c, **kw)


def _need(cond, msg):
    if not cond:
        raise LoadError(msg)


def _num(v, where):
    _need(isinstance(v, (int, float)) and not isinstance(v, bool), f'{where}: expected a number')
    return float(v)


def _pair(v, where):
    _need(isinstance(v, (list, tuple)) and len(v) == 2, f'{where}: expected [low, high]')
    return (_num(v[0], where), _num(v[1], where))


def parse(data, name, default_id):
    unknown = set(data) - TOP_KEYS
    _need(not unknown, f'{name}: unknown key(s) {", ".join(sorted(unknown))}')
    cid = str(data.get('id', default_id))
    _need(cid.replace('_', '').replace('-', '').isalnum(), f'{name}: bad id {cid!r}')
    role = data.get('role', 'costume')
    _need(role in ROLES, f'{name}: role must be one of {", ".join(ROLES)}')

    palette = compile_palette(data.get('palette'), 'palette')
    # A base design's colours are looked up while drawing, so costumes can recolour
    # them; any other file's own palette comes first for its own drawings.
    ctx = Ctx(name, {} if role == 'base' else palette)
    cf = CharacterFile(character=None, palette=palette)
    cf.recolor = compile_palette(data.get('recolor'), 'recolor')

    for part, spec in (data.get('parts') or {}).items():
        _need(part in PARTS, f'{name}: parts.{part}: unknown part (parts are {", ".join(PARTS)})')
        cf.parts[part] = compile_drawing(spec, ctx, f'parts.{part}')
    if role == 'base':
        missing = [p for p in PARTS if p not in cf.parts]
        _need(not missing, f'{name}: a base design must draw every part; missing {missing}')
    for slot, spec in (data.get('layers') or {}).items():
        _need(slot in SLOTS, f'{name}: layers.{slot}: unknown layer (layers are {", ".join(SLOTS)})')
        cf.layers[slot] = compile_drawing(spec, ctx, f'layers.{slot}')

    rig = data.get('rig') or {}
    for k, v in rig.items():
        _need(k in RIG_KEYS, f'{name}: rig.{k}: unknown (rig keys are {", ".join(RIG_KEYS)})')
        cf.rig[k] = tuple(_num(x, f'rig.{k}') for x in v) if isinstance(v, list) else _num(v, f'rig.{k}')
    if 'antenna_y' in data:
        cf.antenna_y = _num(data['antenna_y'], 'antenna_y')

    for g, spec in (data.get('gestures') or {}).items():
        cf.gestures[g] = _gesture(spec, f'gestures.{g}')
    for p, spec in (data.get('particles') or {}).items():
        cf.particles[p] = _emitter(spec, ctx, f'particles.{p}')

    demand = data.get('demand') or {}
    icon_id = ''
    if demand:
        _need(isinstance(demand, dict) and 'icon' in demand,
              f'{name}: demand needs an icon id (demand: {{icon: pyramid, draw: [...]}})')
        icon_id = str(demand['icon'])
        if 'draw' in demand:
            cf.icon = compile_drawing(demand['draw'], ctx, 'demand.draw')
            colour = compile_colour(demand.get('color', 'yellow'), ctx, 'demand.color')
            cf.icon_colour = colour({'_palette': {}, 'evil': 0.0}) if colour else None

    walk = data.get('walk') or {}
    walk_lift = None
    if walk.get('gallop'):
        walk_lift = compile_expr('abs(sin(phase * 0.6)) * 7')
    if 'lift' in walk:
        walk_lift = compile_expr(walk['lift'])

    words = data.get('words') or ()
    _need(isinstance(words, (list, tuple)), f'{name}: words: expected a list of phrases')

    wear = data.get('wear') or ()
    _need(isinstance(wear, (list, tuple)), f'{name}: wear: expected a list of situations')
    for w in wear:
        _need(w in WEAR_SITUATIONS, f'{name}: wear: unknown situation {w!r} (situations are '
                                    f'{", ".join(WEAR_SITUATIONS)})')

    personality = _personality(data.get('personality'), name)

    cf.character = Character(
        id=cid, name=str(data.get('name', '')), role=role, base=str(data.get('base', 'robo')),
        order=float(data.get('order', 1000)),
        words=tuple(str(w).lower() for w in words),
        wear=tuple(wear),
        demand=icon_id,
        move=_move(data['move'], 'move') if data.get('move') else None,
        walk_speed=float(walk.get('speed', 1.0)), walk_lift=walk_lift,
        travel=tuple(_travel(t, f'travel[{i}]') for i, t in enumerate(data.get('travel') or ())),
        personality=personality,
        hobbies={k: _move(v, f'hobbies.{k}') for k, v in (data.get('hobbies') or {}).items()},
        spec=data,
    )
    return cf


def _personality(spec, name):
    """personality: {traits, speech, likes, dislikes, quirks, hobbies, lines: {kind: [...]}}"""
    if not spec:
        return {}
    _need(isinstance(spec, dict), f'{name}: personality: expected a mapping')
    allowed = set(PERSONALITY_LISTS) | {'speech', 'lines'}
    unknown = set(spec) - allowed
    _need(not unknown, f'{name}: personality: unknown key(s) {", ".join(sorted(unknown))}')
    out = {}
    for key in PERSONALITY_LISTS:
        if key in spec:
            v = spec[key]
            _need(isinstance(v, list), f'{name}: personality.{key}: expected a list')
            out[key] = tuple(str(x) for x in v)
    if 'speech' in spec:
        out['speech'] = str(spec['speech'])
    lines = spec.get('lines') or {}
    _need(isinstance(lines, dict), f'{name}: personality.lines: expected a mapping')
    for kind, options in lines.items():
        _need(kind in LINE_KINDS, f'{name}: personality.lines.{kind}: unknown (kinds are '
                                  f'{", ".join(LINE_KINDS)})')
        if isinstance(options, str):
            options = [options]
        _need(isinstance(options, list) and options,
              f'{name}: personality.lines.{kind}: expected a list of lines')
        out.setdefault('lines', {})[kind] = tuple(str(o) for o in options)
    return out


def _gesture(spec, where):
    _need(isinstance(spec, dict) and 'back' in spec and 'front' in spec,
          f'{where}: expected {{back: angle, front: angle}}')
    place = spec.get('place', 'behind')
    _need(place in GESTURE_PLACES, f'{where}.place: one of {", ".join(GESTURE_PLACES)}')
    return Gesture(back=compile_expr(spec['back']), front=compile_expr(spec['front']),
                   place=place,
                   head_x=compile_expr(spec['head_x']) if 'head_x' in spec else None)


def _move(spec, where):
    _need(isinstance(spec, dict), f'{where}: expected a mapping')
    return Move(gesture=str(spec.get('gesture', 'up')), mood=str(spec.get('mood', 'happy')),
                seconds=_num(spec.get('seconds', 3.0), f'{where}.seconds'),
                particles=str(spec.get('particles', '') or ''),
                lift=compile_expr(spec['lift']) if 'lift' in spec else None,
                tilt=compile_expr(spec['tilt']) if 'tilt' in spec else None)


def _travel(spec, where):
    _need(isinstance(spec, dict) and spec.get('kind') in TRAVEL_KINDS,
          f'{where}: kind must be one of {", ".join(TRAVEL_KINDS)}')
    kw = {}
    for k in ('chance', 'speed', 'tilt', 'height', 'windup', 'shoot', 'pause', 'anchor_dx',
              'rope', 'swing', 'lower_speed'):
        if k in spec:
            kw[k] = _num(spec[k], f'{where}.{k}')
    if 'stay' in spec:
        kw['stay'] = _pair(spec['stay'], f'{where}.stay')
    if 'hops' in spec:
        lo, hi = _pair(spec['hops'], f'{where}.hops')
        kw['hops'] = (int(lo), int(hi))
    for k in ('gesture', 'hover_gesture', 'mood', 'particles', 'climb_gesture'):
        if k in spec:
            kw[k] = str(spec[k])
    if 'end' in spec:
        _need(spec['end'] in ('drop', 'lower', 'either'), f'{where}.end: drop, lower or either')
        kw['end'] = spec['end']
    return Travel(kind=spec['kind'], **kw)


def _emitter(spec, ctx, where):
    _need(isinstance(spec, dict), f'{where}: expected a mapping')
    glyph = spec.get('glyph', 'spark')
    _need(glyph in GLYPHS or 'draw' in spec, f'{where}.glyph: one of {", ".join(GLYPHS)}')

    def pair(key, default):
        v = spec.get(key, default)
        _need(isinstance(v, (list, tuple)) and len(v) == 2, f'{where}.{key}: expected [x, y]')
        return tuple(compile_expr(x) for x in v)
    return Emitter(
        rate=_num(spec.get('rate', 3), f'{where}.rate'),
        life=compile_expr(spec.get('life', 1.0)),
        at=pair('at', [0, -60]), velocity=pair('velocity', [0, -20]),
        defs=tuple((k, compile_expr(v)) for k, v in (spec.get('vars') or {}).items()),
        glyph=glyph, text=str(spec.get('text', '')),
        colours=tuple(compile_colour(c, ctx, f'{where}.colors') for c in spec.get('colors', ())),
        size=compile_expr(spec['size']) if 'size' in spec else None,
        draw=compile_drawing(spec['draw'], ctx, f'{where}.draw') if 'draw' in spec else None,
    )
