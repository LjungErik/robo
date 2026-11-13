"""What a character file says about *behaviour* (the core reads this; the
drawings are handled by robo.render).

    Character   one character file: who it is and how it acts
    Move        its signature move
    Travel      a way of getting around besides walking (fly, hang, teleport)
"""
from dataclasses import dataclass, field
from typing import Optional, Tuple

from .expr import Expr

ROLES = ('base', 'costume', 'work')
# Situations he can say something on his own in (personality.lines.<kind>), see
# robo/core/initiative.py. "{name}" is replaced by your name; "{, name}" by ", Erik"
# (or nothing if he doesn't know your name yet).
LINE_KINDS = ('first_meeting', 'morning', 'welcome_back', 'break', 'late', 'bored', 'remark',
              'question', 'sleepy', 'picked_up_happy', 'picked_up_grumpy', 'put_down',
              'task_started', 'hobby', 'dressed_up')
TRAVEL_KINDS = ('fly', 'hang', 'teleport')
# Situations an outfit suits (`wear:` in a file); Robo likes to wear it then.
# What each one means is in robo/core/outfits.py.
WEAR_SITUATIONS = ('morning', 'lunch', 'afternoon', 'evening', 'night', 'monday', 'friday',
                   'weekend', 'spring', 'summer', 'autumn', 'winter', 'halloween', 'christmas',
                   'new_year', 'valentine', 'happy', 'sad', 'bored', 'tired', 'music', 'mail',
                   'chat', 'meeting', 'fixing', 'working', 'back', 'video')


@dataclass(frozen=True)
class Move:
    gesture: str = 'up'              # arm gesture (see `gestures` in the files)
    mood: str = 'happy'              # face while doing it
    seconds: float = 3.0
    particles: str = ''              # emitter name (see `particles` in the files)
    lift: Optional[Expr] = None      # height off the ground during the move (vars: t)
    tilt: Optional[Expr] = None      # head tilt during the move


@dataclass(frozen=True)
class Travel:
    """Getting around without walking.

    fly       take off, fly to a random spot anywhere on the screen, hover,
              maybe fly on, then land
    hang      shoot a web line up to the top of the screen (gesture, `shoot` s),
              a web builds where it hits, zip up it (`speed`), hang and swing
              on it (`hover_gesture`, `swing`), then let go (`end: drop`) or
              lower himself down on the thread (`end: lower`, like a spider)
    teleport  wind up (gesture), vanish in a puff of smoke, reappear elsewhere
    """
    kind: str
    chance: float = 0.3              # chance, each time he picks something to do
    speed: float = 150.0             # design px / s
    gesture: str = ''                # arms while travelling
    hover_gesture: str = ''          # arms while hovering / hanging
    mood: str = ''                   # face while travelling ('' = unchanged)
    tilt: float = 0.0                # head tilt while moving
    stay: Tuple[float, float] = (3.0, 7.0)    # seconds hovering / hanging
    hops: Tuple[int, int] = (1, 3)   # flights before landing
    height: float = 0.0              # extra lift while airborne (room for jet flames)
    windup: float = 0.0              # teleport: seconds of gesture before the poof
    particles: str = ''              # emitter while travelling
    # hang only
    shoot: float = 0.45              # seconds for the web line to reach the top of the screen
    pause: float = 0.25              # seconds between the web sticking and zipping up
    anchor_dx: float = 31.0          # the web goes up from this far in front of his centre
    rope: float = 180.0              # how far below the web he hangs (design px, to his hand)
    swing: float = 0.25              # pendulum swing when he arrives (radians)
    lower_speed: float = 55.0        # design px / s when lowering himself down
    end: str = 'either'              # 'drop', 'lower' or 'either'
    climb_gesture: str = ''          # arms while lowering himself down


@dataclass(frozen=True)
class Character:
    id: str
    name: str = ''
    role: str = 'costume'
    base: str = 'robo'               # the base design a costume is drawn on when used as a look
    order: float = 1000.0            # position in lists (settings window)
    words: Tuple[str, ...] = ()      # what people say to ask for him ("dress up as ...")
    wear: Tuple[str, ...] = ()       # situations he likes to wear it in (WEAR_SITUATIONS)
    demand: str = ''                 # bubble icon id he demands while dressed up
    move: Optional[Move] = None
    walk_speed: float = 1.0
    walk_lift: Optional[Expr] = None   # extra height while walking (vars: phase)
    travel: Tuple[Travel, ...] = ()
    personality: dict = field(default_factory=dict, compare=False)   # see LINE_KINDS / README
    hobbies: dict = field(default_factory=dict, compare=False)       # name -> Move (idle pastimes)
    source: str = ''                 # file it came from
    spec: dict = field(default_factory=dict, compare=False, repr=False)  # the whole file

    @property
    def title(self):
        return self.name or self.id.replace('_', ' ').title()

    def ability(self, kind):
        return next((t for t in self.travel if t.kind == kind), None)

    # old names, still handy
    @property
    def particles(self):
        return self.move.particles if self.move else ''
