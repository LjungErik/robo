"""All character files, and the Designs (what to draw) built from them.

    REGISTRY.get('pirate')              -> Character (behaviour)
    REGISTRY.costumes()                 -> ids he can dress up as
    REGISTRY.design('robo', 'pirate')   -> Design: base robot + outfit, ready to draw

Files are read from robo/characters/ and then from any directory added with
add_directory() (the app adds ~/.config/robo/characters). A later file with
the same id replaces an earlier one, so you can even redesign Robo himself.
reload_if_changed() picks up edits while he runs.
"""
import logging
import os
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Tuple

from robo.render.interpreter import EvilColour

from .loader import EXTENSIONS, LoadError, load_file

log = logging.getLogger(__name__)

BUILTIN_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           'characters')
DEFAULT_BASE = 'robo'
RIG_DEFAULTS = dict(shoulder=(21.0, -45.0), arm_length=19.0, neck=(0.0, -58.0), sit_drop=12.0,
                    head_top=-112.0, antenna_y=None)


@dataclass
class Design:
    """Everything needed to draw one combination of base + look + outfit."""
    key: tuple
    rig: dict
    palette: Dict[str, Callable]
    parts: Dict[str, Tuple[Callable, str]]          # part -> (draw, label for errors)
    slots: Dict[str, List[Tuple[Callable, str]]]    # outfit layer -> drawings, in order
    gestures: dict
    antenna_y: float
    files: tuple = field(default=())                # ids it was built from

    @property
    def head_top(self):
        return self.rig['head_top']


class Registry:
    def __init__(self, directories=(BUILTIN_DIR,)):
        self.directories = list(directories)
        self.files = {}               # id -> CharacterFile
        self.errors = {}              # path -> message, for files that didn't load
        self.version = 0
        self._designs = {}
        self._signature = None
        self._loaded = False

    # ------------------------------------------------------------ loading
    def _ensure(self):
        if not self._loaded:
            self.reload()

    def add_directory(self, path):
        if path and path not in self.directories:
            self.directories.append(path)
            self._loaded = False

    def _scan(self):
        found = []
        for d in self.directories:
            try:
                names = sorted(os.listdir(d))
            except OSError:
                continue
            for n in names:
                if n.endswith(EXTENSIONS) and not n.startswith('.'):
                    p = os.path.join(d, n)
                    try:
                        found.append((p, os.stat(p).st_mtime_ns))
                    except OSError:
                        pass
        return found

    def reload(self):
        scan = self._scan()
        files, errors = {}, {}
        for path, _mtime in scan:
            try:
                cf = load_file(path)
            except LoadError as e:
                errors[path] = str(e)
                log.warning('skipping character file: %s', e)
                continue
            if cf.id in files and os.path.dirname(files[cf.id].character.source) == \
                    os.path.dirname(path):
                log.warning('%s: id %r is used twice, keeping the first', path, cf.id)
                continue
            files[cf.id] = cf
        if DEFAULT_BASE not in files or files[DEFAULT_BASE].character.role != 'base':
            raise LoadError(f'the base design {DEFAULT_BASE!r} is missing or broken: '
                            f'{errors.get(os.path.join(BUILTIN_DIR, DEFAULT_BASE + ".yaml"), "")}')
        self.files, self.errors = files, errors
        self._designs.clear()
        self._signature = scan
        self._loaded = True
        self.version += 1

    def reload_if_changed(self):
        """Re-read the files if any was added, removed or edited. Returns True if so."""
        if self._loaded and self._scan() == self._signature:
            return False
        try:
            self.reload()
        except LoadError as e:
            log.warning('%s (keeping the characters loaded before)', e)
            self._signature = self._scan()
            return False
        return True

    # ------------------------------------------------------------ lookups
    def file(self, cid):
        self._ensure()
        return self.files.get(cid)

    def get(self, cid):
        cf = self.file(cid)
        return cf.character if cf else None

    def ids(self, *roles):
        self._ensure()
        chars = [cf.character for cf in self.files.values() if cf.character.role in roles]
        return tuple(c.id for c in sorted(chars, key=lambda c: (c.order, c.title.lower())))

    def costumes(self):
        """Who he can dress up as."""
        return self.ids('costume')

    def looks(self):
        """What he can look like all the time: base designs and costumes."""
        return self.ids('base', 'costume')

    def demand_icons(self):
        """icon id -> (draw(cr, env), antenna colour)."""
        self._ensure()
        return {cf.character.demand: (cf.icon, cf.icon_colour)
                for cf in self.files.values() if cf.character.demand and cf.icon}

    def demand_ids(self):
        self._ensure()
        return frozenset(cf.character.demand for cf in self.files.values()
                         if cf.character.demand)

    def emitter(self, name):
        self._ensure()
        for cf in reversed(list(self.files.values())):
            if name in cf.particles:
                return cf.particles[name]
        return None

    def personality(self, look='', costume=''):
        """Who he is right now: Robo's own personality, then his look's, then his
        costume's (each overrides what it sets; lines per situation)."""
        self._ensure()
        base, look_cf = self.base_of(look or DEFAULT_BASE)
        out = {'lines': {}}
        for cf in (base, look_cf, self.files.get(costume) if costume else None):
            if cf is None:
                continue
            p = cf.character.personality
            for k, v in p.items():
                if k == 'lines':
                    out['lines'].update(v)
                else:
                    out[k] = v
        return out

    def hobbies(self, look='', costume=''):
        """name -> Move: what he does to pass the time (base, then look, then costume)."""
        self._ensure()
        base, look_cf = self.base_of(look or DEFAULT_BASE)
        out = {}
        for cf in (base, look_cf, self.files.get(costume) if costume else None):
            if cf is not None:
                out.update(cf.character.hobbies)
        return out

    def gesture(self, name):
        """A gesture from any loaded file (for poses the current design doesn't define)."""
        self._ensure()
        for cf in self.files.values():
            if name in cf.gestures:
                return cf.gestures[name]
        return None

    def errors_for(self, path):
        return self.errors.get(path)

    # ------------------------------------------------------------ designs
    def base_of(self, look):
        """(base file, look file or None) for a look id."""
        self._ensure()
        cf = self.files.get(look) or self.files[DEFAULT_BASE]
        if cf.character.role == 'base':
            return cf, None
        base = self.files.get(cf.character.base)
        if base is None or base.character.role != 'base':
            base = self.files[DEFAULT_BASE]
        return base, (cf if cf.character.role != 'base' else None)

    def design(self, look='', costume=''):
        self._ensure()
        key = (look or DEFAULT_BASE, costume or '')
        d = self._designs.get(key)
        if d is None:
            d = self._designs[key] = self._build(*key)
        return d

    def _build(self, look, costume):
        base, look_cf = self.base_of(look)
        layers = [cf for cf in (look_cf, self.files.get(costume)) if cf is not None]
        if layers and layers[-1] is not None and layers[-1].character.role == 'base':
            layers.pop()                       # can't wear a base design as an outfit
        rig = dict(RIG_DEFAULTS)
        rig.update(base.rig)
        palette = dict(base.palette)
        parts = {p: (fn, f'{base.id}.parts.{p}') for p, fn in base.parts.items()}
        slots = {s: [(fn, f'{base.id}.layers.{s}')] for s, fn in base.layers.items()}
        gestures = dict(base.gestures)
        antenna_y = rig['antenna_y'] if rig['antenna_y'] is not None else rig['head_top']
        for cf in layers:
            rig.update(cf.rig)
            for name, colour in cf.recolor.items():
                old = palette.get(name)
                if isinstance(old, EvilColour) and not isinstance(colour, EvilColour):
                    colour = old.with_good(colour)
                palette[name] = colour
            for p, fn in cf.parts.items():
                parts[p] = (fn, f'{cf.id}.parts.{p}')
            for s, fn in cf.layers.items():
                slots.setdefault(s, []).append((fn, f'{cf.id}.layers.{s}'))
            gestures.update(cf.gestures)
            if cf.antenna_y is not None:
                antenna_y = cf.antenna_y
        return Design(key=(look, costume), rig=rig, palette=palette, parts=parts, slots=slots,
                      gestures=gestures, antenna_y=antenna_y,
                      files=(base.id,) + tuple(cf.id for cf in layers))


REGISTRY = Registry()
