"""A plugin's plugin.json: who it is and what it may do.

    {
      "id": "game_buddy",                 letters, digits, _ and -
      "name": "Game buddy",
      "description": "Robo plays games with you.",
      "version": "1.0",
      "author": "you",
      "icon": "🎮",
      "permissions": ["screen", "input", "ai"],
      "entry": "plugin.py"                (default)
    }
"""
import json
import os
import re
from dataclasses import dataclass
from typing import Tuple

API_VERSION = 1
MANIFEST = 'plugin.json'
MAX_MANIFEST = 20_000

# permission -> (icon, what it lets the plugin do: "It may ...")
PERMISSIONS = {
    'screen': ('👁', 'see your screen while you show it to Robo'),
    'camera': ('📷', 'take pictures with your camera (Robo shows when it does)'),
    'input': ('🎮', 'press keys and move the mouse, once you allow it in GNOME\'s dialog'),
    'ai': ('🧠', "ask Robo's AI brain questions (it uses your AI plan)"),
}
ALWAYS = ('talk through Robo, add things you can say to him and menu items',
          'keep its own files in its own folder (nothing else of yours, no internet)')


class ManifestError(ValueError):
    pass


@dataclass(frozen=True)
class Manifest:
    id: str
    name: str
    folder: str
    description: str = ''
    version: str = ''
    author: str = ''
    icon: str = '🧩'
    permissions: Tuple[str, ...] = ()
    entry: str = 'plugin.py'

    def to_dict(self):
        return {'id': self.id, 'name': self.name, 'version': self.version,
                'permissions': list(self.permissions), 'entry': self.entry}


def load_manifest(folder):
    path = os.path.join(folder, MANIFEST)
    name = os.path.basename(folder.rstrip('/'))
    try:
        if os.path.getsize(path) > MAX_MANIFEST:
            raise ManifestError(f'{name}: {MANIFEST} is too big')
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        raise ManifestError(f'{name}: no {MANIFEST}') from None
    except (OSError, ValueError) as e:
        raise ManifestError(f'{name}: {MANIFEST}: {e}') from None
    if not isinstance(data, dict):
        raise ManifestError(f'{name}: {MANIFEST} must be an object')
    pid = str(data.get('id') or name)
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,40}', pid):
        raise ManifestError(f'{name}: bad id {pid!r}')
    perms = data.get('permissions') or []
    if not isinstance(perms, list) or any(p not in PERMISSIONS for p in perms):
        raise ManifestError(f'{name}: permissions must be a list of '
                            f'{", ".join(PERMISSIONS)}')
    entry = str(data.get('entry') or 'plugin.py')
    if os.path.basename(entry) != entry or not entry.endswith('.py'):
        raise ManifestError(f'{name}: entry must be a .py file in the plugin folder')
    if not os.path.isfile(os.path.join(folder, entry)):
        raise ManifestError(f'{name}: {entry} is missing')
    api = data.get('api', API_VERSION)
    if api != API_VERSION:
        raise ManifestError(f'{name}: made for plugin API {api}, Robo has {API_VERSION}')
    return Manifest(id=pid, name=str(data.get('name') or pid)[:60], folder=folder,
                    description=str(data.get('description') or '')[:400],
                    version=str(data.get('version') or '')[:20],
                    author=str(data.get('author') or '')[:60],
                    icon=str(data.get('icon') or '🧩')[:4],
                    permissions=tuple(dict.fromkeys(perms)), entry=entry)


def signature(folder):
    """Changes whenever a file in the plugin folder does (for hot reload)."""
    out = []
    for root, dirs, files in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if not d.startswith(('.', '__pycache__')))
        for n in sorted(files):
            if n.startswith('.') or n.endswith('.pyc'):
                continue
            p = os.path.join(root, n)
            try:
                st = os.stat(p)
            except OSError:
                continue
            out.append((os.path.relpath(p, folder), st.st_mtime_ns, st.st_size))
    return tuple(out)
