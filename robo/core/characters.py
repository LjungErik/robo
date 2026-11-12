"""The characters Robo can dress up as.

Each character has an outfit (drawn by robo.render.costumes, same id), a
signature move he does now and then, and a demand he makes in his bubble.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Character:
    id: str
    demand: str                  # bubble icon: what he demands
    move: str                    # arm gesture for his signature move
    move_mood: str               # face while doing it
    move_seconds: float
    particles: Optional[str] = None   # what flies out during the move (see effects.py)
    walk_speed: float = 1.0
    gallop: bool = False         # bouncy walk
    name: str = ''               # shown in the settings window
    move_lift: str = ''          # '', 'float', 'bounce' or 'fly': leaves the ground during the move

    @property
    def title(self):
        return self.name or self.id.title()


CHARACTERS = {c.id: c for c in (
    # Walks like an Egyptian and demands a pyramid of himself.
    Character('pharaoh', demand='pyramid', move='egypt', move_mood='happy', move_seconds=4.0,
              walk_speed=0.8),
    # Twirls his lasso, gallops on an invisible horse and wants a lucky horseshoe.
    Character('cowboy', demand='horseshoe', move='lasso', move_mood='happy', move_seconds=3.5,
              walk_speed=1.5, gallop=True),
    # Lets out a mighty battle cry, then demands mead.
    Character('viking', demand='mead', move='roar', move_mood='roar', move_seconds=2.2),
    # Types furiously on his calculator (numbers fly out) and wants receipts. All of them.
    Character('accountant', demand='receipt', move='calc', move_mood='focus', move_seconds=3.5,
              particles='numbers', walk_speed=1.2),
    # "Fixes" himself by bonking his own head with a wrench; asks for an oil can.
    Character('mechanic', demand='oilcan', move='fix', move_mood='wince', move_seconds=2.5,
              particles='sparks'),
    # Plays the lyre while notes float up; would like grapes, peeled.
    Character('roman', name='Roman emperor', demand='grapes', move='lyre', move_mood='sing',
              move_seconds=4.5, particles='notes', walk_speed=0.7),
    # Flips a pancake sky-high and catches it; would love a cupcake.
    Character('chef', demand='cupcake', move='flip', move_mood='happy', move_seconds=3.6),
    # Floats around in zero gravity among the stars, moon-walks, wants a rocket.
    Character('astronaut', demand='rocket', move='float', move_mood='happy', move_seconds=4.5,
              particles='stars', move_lift='float', walk_speed=0.8, gallop=True),
    # Waves his wand, sparkles everywhere; demands a bubbling potion.
    Character('wizard', demand='potion', move='spell', move_mood='focus', move_seconds=3.0,
              particles='magic', walk_speed=0.8),
    # Dances a jig with his parrot; wants treasure, obviously.
    Character('pirate', demand='treasure', move='jig', move_mood='happy', move_seconds=3.5,
              particles='notes', move_lift='bounce'),
    # Flies up, fist first, cape trailing; looking for a kitten to rescue.
    Character('superhero', demand='kitten', move='fly', move_mood='happy', move_seconds=3.5,
              particles='stars', move_lift='fly', walk_speed=1.6),
    # Bats at a ball of yarn, :3 face, little hearts; asks for a fish.
    Character('kitty', demand='fish', move='paw', move_mood='cat', move_seconds=3.5,
              particles='hearts'),
)}

DEMAND_ICONS = frozenset(c.demand for c in CHARACTERS.values())
