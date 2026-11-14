"""Robo's wardrobe: list his outfits, remove some, export and import them.

    wardrobe()                      -> [Outfit]: every costume, and where it came from
    remove(outfit)                  -> moves its file away (to the trash if you give one)
    export(ids, path)               -> one outfit as .yaml, or several as a .zip bundle
    import_outfits(path, folder)    -> Report: what was added, what was skipped and why
    install(path, folder, problems) -> check one outfit file and copy it in (also used
                                       for the outfits Robo designs himself)

Outfits are single character files (see robo/characters/README.md). Sharing
them is safe: they are only interpreted (shapes and small expressions, never
code), and every file is checked, drawn in every pose, before it is installed.

A bundle is a zip of outfit files plus robo-outfits.json:
    {"format": "robo-outfits", "version": 1,
     "outfits": [{"id": "disco", "name": "Disco Robo", "file": "disco.yaml"}]}
The manifest is optional on import: any .yaml/.yml/.json file in the zip is tried.
"""
import io
import json
import logging
import os
import re
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from typing import List, Tuple

from .loader import EXTENSIONS, LoadError, load_file
from .registry import BUILTIN_DIR, REGISTRY

log = logging.getLogger(__name__)

FORMAT, VERSION = 'robo-outfits', 1
MANIFEST = 'robo-outfits.json'
ROBO_MADE, IMPORTED = 'robo-made', 'imported'     # sub-folders of your characters folder
MAX_FILE = 200_000                 # bytes per outfit file
MAX_FILES = 50                     # outfits per bundle
ORIGINS = {'builtin': 'Comes with Robo', 'robo': 'Robo designed it',
           'imported': 'Imported', 'yours': 'Your own file'}


@dataclass
class Outfit:
    id: str
    title: str
    origin: str                    # builtin / robo / imported / yours
    path: str

    @property
    def removable(self):
        return self.origin != 'builtin'

    @property
    def origin_words(self):
        return ORIGINS.get(self.origin, self.origin)


@dataclass
class Report:
    added: List[str] = field(default_factory=list)                 # ids
    skipped: List[Tuple[str, str]] = field(default_factory=list)   # (file name, why)

    def summary(self):
        from robo.core import characters
        parts = []
        if self.added:
            names = ', '.join(characters.title(c) for c in self.added)
            parts.append(f'Added {names}.')
        for name, why in self.skipped:
            parts.append(f'Skipped {name}: {why}.')
        return ' '.join(parts) or 'There were no outfits in that file.'


class ShareError(ValueError):
    pass


# ---------------------------------------------------------------- listing
def folders(characters_dir):
    """(robo-made folder, imported folder) inside your characters folder."""
    return os.path.join(characters_dir, ROBO_MADE), os.path.join(characters_dir, IMPORTED)


def origin_of(path):
    where = os.path.dirname(os.path.abspath(path))
    if where == os.path.abspath(BUILTIN_DIR):
        return 'builtin'
    return {ROBO_MADE: 'robo', IMPORTED: 'imported'}.get(os.path.basename(where), 'yours')


def wardrobe(registry=REGISTRY):
    """Every costume he can wear, in the usual order."""
    out = []
    for cid in registry.costumes():
        c = registry.get(cid)
        out.append(Outfit(cid, c.title, origin_of(c.source), c.source))
    return out


def find(cid, registry=REGISTRY):
    return next((o for o in wardrobe(registry) if o.id == cid), None)


def duplicate_of(spec, registry=REGISTRY, ignore=''):
    """The id of an outfit that is exactly the same (apart from its id), or None."""
    mine = {k: v for k, v in (spec or {}).items() if k != 'id'}
    for cid in registry.ids('base', 'costume', 'work'):
        if cid == ignore:
            continue
        other = registry.get(cid)
        if other is not None and {k: v for k, v in (other.spec or {}).items()
                                  if k != 'id'} == mine:
            return cid
    return None


# ---------------------------------------------------------------- removing
def remove(outfit, trash=None, registry=REGISTRY):
    """Take an outfit out of his wardrobe. `trash(path)` moves it to the trash
    (the desktop's); without one it goes to a hidden .removed folder next to it,
    so it can still be fetched back. Built-in outfits can't be removed."""
    if not outfit.removable:
        raise ShareError(f'{outfit.title} comes with Robo and can\'t be removed '
                         '(untick it under Characters instead)')
    if trash is not None:
        trash(outfit.path)
    else:
        keep = os.path.join(os.path.dirname(outfit.path), '.removed')
        os.makedirs(keep, exist_ok=True)
        os.replace(outfit.path, os.path.join(keep, os.path.basename(outfit.path)))
    registry.reload()
    log.info('removed outfit %s (%s)', outfit.id, outfit.path)


# ---------------------------------------------------------------- exporting
def _shareable_text(outfit):
    with open(outfit.path, encoding='utf-8') as f:
        text = f.read()
    if outfit.path.endswith('.json'):
        return text
    header = (f'# A Robo outfit: {outfit.title}. Exported {time.strftime("%Y-%m-%d")}.\n'
              "# To wear it: Robo's Settings → Characters → Wardrobe → Import.\n")
    return text if text.startswith('# A Robo outfit:') else header + text


def export(ids, path, registry=REGISTRY):
    """Write outfits to `path`: a .zip bundle (any number), or one outfit's own
    file (.yaml / .json). Returns the path written."""
    outfits = [o for o in (find(cid, registry) for cid in ids) if o is not None]
    if not outfits:
        raise ShareError('no outfits to export')
    if not path.lower().endswith('.zip'):
        if len(outfits) > 1:
            raise ShareError('several outfits go in a .zip bundle')
        _write_atomic(path, _shareable_text(outfits[0]))
        return path
    manifest = {'format': FORMAT, 'version': VERSION, 'exported': time.strftime('%Y-%m-%d'),
                'outfits': []}
    tmp = path + '.tmp'
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as z:
        for o in outfits:
            name = o.id + os.path.splitext(o.path)[1]
            z.writestr(name, _shareable_text(o))
            manifest['outfits'].append({'id': o.id, 'name': o.title, 'file': name})
        z.writestr(MANIFEST, json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
    os.replace(tmp, path)
    return path


def suggested_name(ids, registry=REGISTRY):
    if len(ids) == 1:
        o = find(ids[0], registry)
        return f'{ids[0]}.robo-outfit' + (os.path.splitext(o.path)[1] if o else '.yaml')
    return f'robo-outfits-{time.strftime("%Y-%m-%d")}.zip'


def _write_atomic(path, text):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(text)
    os.replace(tmp, path)


# ---------------------------------------------------------------- importing
def import_outfits(path, folder, registry=REGISTRY):
    """Install the outfits in a .yaml/.yml/.json file or a .zip bundle into `folder`."""
    report = Report()
    name = os.path.basename(path)
    if zipfile.is_zipfile(path):
        with tempfile.TemporaryDirectory(prefix='robo-import-') as tmp:
            for member, problem in _unzip(path, tmp):
                if problem:
                    report.skipped.append((member, problem))
                else:
                    _import_one(os.path.join(tmp, member), member, folder, report, registry)
        return report
    if not path.lower().endswith(EXTENSIONS):
        raise ShareError(f'{name} is not an outfit file (.yaml, .json or a .zip bundle)')
    _import_one(path, name, folder, report, registry)
    return report


def _unzip(path, tmp):
    """Yield (file name, problem or None); good files are extracted flat into tmp."""
    with zipfile.ZipFile(path) as z:
        members = [m for m in z.infolist() if not m.is_dir()
                   and os.path.basename(m.filename) != MANIFEST
                   and not os.path.basename(m.filename).startswith('.')
                   and m.filename.lower().endswith(EXTENSIONS)]
        if len(members) > MAX_FILES:
            raise ShareError(f'the bundle has {len(members)} outfits; at most {MAX_FILES}')
        seen = set()
        for m in members:
            base = os.path.basename(m.filename)
            if base in seen:
                yield base, 'two files have this name'
                continue
            seen.add(base)
            if m.file_size > MAX_FILE:
                yield base, 'the file is too big'
                continue
            with z.open(m) as src:          # don't trust file_size: read at most MAX_FILE
                data = src.read(MAX_FILE + 1)
            if len(data) > MAX_FILE:
                yield base, 'the file is too big'
                continue
            with open(os.path.join(tmp, base), 'wb') as f:
                f.write(data)
            yield base, None


def _import_one(path, name, folder, report, registry):
    try:
        spec = load_file(path).character.spec
    except LoadError as e:
        report.skipped.append((name, str(e).split(': ', 1)[-1]))
        return
    same = duplicate_of(spec, registry)
    if same:
        from robo.core import characters
        report.skipped.append((name, f'you already have it ({characters.title(same)})'))
        return
    problems = []
    header = f'# Imported on {time.strftime("%Y-%m-%d")} from {name}.\n'
    cid = install(path, folder, problems, header=header, registry=registry)
    if cid:
        report.added.append(cid)
    else:
        report.skipped.append((name, problems[0] if problems else 'it did not load'))


# ---------------------------------------------------------------- installing
def install(path, folder, problems, header='', registry=REGISTRY):
    """Check an outfit file and copy it into `folder` (renamed if its id is taken).
    Returns its id, or None with the reason appended to `problems`."""
    from .check import check

    try:
        with open(path, encoding='utf-8') as f:
            text = f.read()
        if len(text) > MAX_FILE:
            raise LoadError('the file is too big')
        character = load_file(path).character
    except (OSError, UnicodeDecodeError, LoadError) as e:
        problems.append(str(e))
        return None
    if character.role != 'costume':
        problems.append(f'{character.id} is a {character.role}, not a costume')
        return None
    out = io.StringIO()
    where = os.path.dirname(os.path.abspath(path))
    had = where in registry.directories
    try:
        n = check([path], sheet=False, out=lambda line: out.write(line + '\n'))
    finally:
        if not had:                    # check() adds the file's folder: take it out again
            registry.directories[:] = [d for d in registry.directories if d != where]
    if n:
        lines = [l.strip() for l in out.getvalue().splitlines() if l.strip()]
        problems.append(lines[-1] if lines else 'it did not draw cleanly')
        registry.reload()
        return None
    registry.add_directory(folder)
    registry.reload()
    cid = re.sub(r'[^a-z0-9_]', '_', character.id.lower()).strip('_') or 'outfit'
    base, k = cid, 2
    while registry.get(cid) is not None:
        cid, k = f'{base}_{k}', k + 1
    ext = '.json' if path.endswith('.json') else '.yaml'
    if ext == '.json':
        data = json.loads(text)
        data['id'] = cid
        text = json.dumps(data, indent=2, ensure_ascii=False) + '\n'
    else:
        if cid != character.id or not re.search(r'^id:', text, flags=re.M):
            if re.search(r'^id:', text, flags=re.M):
                text = re.sub(r'^id:.*$', f'id: {cid}', text, count=1, flags=re.M)
            else:
                text = f'id: {cid}\n' + text
        text = header + text
    os.makedirs(folder, exist_ok=True)
    target = os.path.join(folder, cid + ext)
    _write_atomic(target, text)
    registry.reload()
    log.info('installed outfit %s (%s)', cid, target)
    return cid


def removable_first(outfits: List[Outfit]) -> List[Outfit]:
    """Yours to manage first (his designs, imports, your files), then the built-in ones."""
    return sorted(outfits, key=lambda o: (not o.removable, o.title.lower()))
