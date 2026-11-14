"""What Robo knows about each game: its controls, as moves he can choose.

A move is a small JSON object the AI picks ({"do": "walk", "dir": "forward",
"seconds": 1}). Each belongs to a group of controls, so you can hand him
just some of them: "you do the walking" = only the 'move' group.
Add a game by adding a Game here (Robo reloads the plugin when you save).
"""
from dataclasses import dataclass, field
from typing import Dict, Tuple

GROUPS = {
    'move': ('walking', 'walk', 'moving', 'move', 'running', 'jumping', 'driving', 'steer'),
    'look': ('looking', 'look', 'camera', 'aiming', 'aim', 'turning', 'mouse'),
    'act': ('mining', 'mine', 'digging', 'attacking', 'attack', 'fighting', 'fight',
            'building', 'build', 'shooting', 'shoot', 'clicking', 'actions', 'items'),
}


@dataclass
class Game:
    name: str
    words: Tuple[str, ...]                 # how you might call it
    about: str                             # for the AI: what the game is, how to read it
    moves: Dict[str, Tuple[str, str]] = field(default_factory=dict)   # do -> (group, help)
    keys: Dict[str, str] = field(default_factory=dict)                # name -> key
    pixels_per_degree: float = 6.7         # mouse "look" sensitivity


MINECRAFT = Game(
    'Minecraft', ('minecraft',),
    'Minecraft (first person). The crosshair in the middle is what you aim at. Trees are '
    'logs with leaves; hold attack on a block to break it. Turn to face things before '
    'walking to them. Avoid lava, deep drops and water you can\'t get out of.',
    moves={
        'walk': ('move', '{"do": "walk", "dir": "forward|back|left|right", "seconds": 0.2-3}'),
        'sprint': ('move', '{"do": "sprint", "seconds": 0.5-4} (forward, fast)'),
        'jump': ('move', '{"do": "jump"} (also jump while walking up one block: walk + jump)'),
        'sneak': ('move', '{"do": "sneak", "seconds": 0.2-3}'),
        'look': ('look', '{"do": "look", "right": degrees (-180..180), "up": degrees (-90..90)}'),
        'attack': ('act', '{"do": "attack", "seconds": 0.1-5} (hit / break the block you aim at)'),
        'use': ('act', '{"do": "use"} (place a block, eat, open a door)'),
        'hotbar': ('act', '{"do": "hotbar", "slot": 1-9}'),
        'inventory': ('act', '{"do": "inventory"} (open / close it)'),
    },
    keys={'forward': 'w', 'back': 's', 'left': 'a', 'right': 'd', 'jump': 'space',
          'sneak': 'shift', 'sprint': 'ctrl', 'inventory': 'e'})

GENERIC = Game(
    'the game', (),
    'A game on the screen. Work out from the picture what kind of game it is and what '
    'the player should do next.',
    moves={
        'walk': ('move', '{"do": "walk", "dir": "forward|back|left|right", "seconds": 0.1-3} '
                         '(W A S D)'),
        'arrow': ('move', '{"do": "arrow", "dir": "up|down|left|right", "seconds": 0.1-3}'),
        'jump': ('move', '{"do": "jump"} (space)'),
        'look': ('look', '{"do": "look", "right": degrees, "up": degrees} (mouse)'),
        'click': ('act', '{"do": "click", "button": "left|right", "seconds": 0.05-2}'),
        'key': ('act', '{"do": "key", "key": "e|q|f|r|1-9|Return|Escape|Tab"}'),
    },
    keys={'forward': 'w', 'back': 's', 'left': 'a', 'right': 'd', 'jump': 'space'})

GAMES = (MINECRAFT,)
SAFE_KEYS = {'e', 'q', 'f', 'r', 'Return', 'Escape', 'Tab'} | {str(i) for i in range(1, 10)}


def find_game(text):
    text = text.lower()
    for g in GAMES:
        if any(w in text for w in g.words):
            return g
    return GENERIC


def groups_in(text):
    """Which controls you're handing over ('you do the walking' -> {'move'})."""
    text = text.lower()
    found = {g for g, words in GROUPS.items() if any(w in text.split() for w in words)}
    return found or set(GROUPS)
