"""Particles: little things that fly out during signature moves.

Positions are in robot coordinates (origin = ground point between his
feet, y up is negative, design pixels); x already includes facing.
"""
from dataclasses import dataclass

NUMBER_GLYPHS = '+−×%$=7349'


@dataclass(frozen=True)
class Particle:
    glyph: str        # 'note', 'spark' or a text character
    born: float
    life: float
    x: float
    y: float
    vx: float
    vy: float


# particle kind -> (per second, spawn function(rng, facing) -> (glyph, life, x, y, vx, vy))
EMITTERS = {
    # out of the calculator / lyre, away from his face, toward the side he faces
    'numbers': (3.5, lambda rng, f: (rng.choice(NUMBER_GLYPHS), 1.3,
                                     f * 18, -46, f * rng.uniform(18, 34), rng.uniform(-34, -18))),
    'notes': (2.2, lambda rng, f: ('note', 1.8,
                                   f * 20, -50, f * rng.uniform(14, 26), rng.uniform(-28, -16))),
    'sparks': (9.0, lambda rng, f: ('spark', 0.45,
                                    f * 36, -86, f * rng.uniform(5, 40), rng.uniform(-40, 10))),
    # twinkling stars all around him (astronaut, superhero)
    'stars': (4.0, lambda rng, f: ('star', 1.4, rng.uniform(-48, 48), rng.uniform(-140, -20),
                                   0.0, rng.uniform(-8, -2))),
    # colourful sparkles out of the wizard's wand tip
    'magic': (12.0, lambda rng, f: ('magic', 0.8, f * 34, -84, f * rng.uniform(-10, 34),
                                    rng.uniform(-36, 14))),
    # green ones and zeros rising from the hacker's laptop
    # (out past the sides of his head, so his face stays visible)
    'binary': (4.0, lambda rng, f: _binary(rng)),
    # little hearts while the kitty plays
    'hearts': (1.6, lambda rng, f: ('heart', 1.5, f * rng.uniform(14, 30), -46,
                                    f * rng.uniform(0, 10), rng.uniform(-30, -18))),
}


def _binary(rng):
    side = rng.choice((-1, 1))
    return (rng.choice('01'), 1.4, side * rng.uniform(24, 32), -36,
            side * rng.uniform(10, 20), rng.uniform(-30, -20))


class Effects:
    def __init__(self, rng):
        self.rng = rng
        self.particles = []
        self._debt = 0.0

    def emit(self, kind, now, dt, facing):
        """Spawn particles of `kind` at its rate for this frame."""
        rate, spawn = EMITTERS[kind]
        self._debt += rate * dt
        while self._debt >= 1:
            self._debt -= 1
            glyph, life, x, y, vx, vy = spawn(self.rng, facing)
            self.particles.append(Particle(glyph, now, life, x, y, vx, vy))

    def update(self, now):
        self.particles = [p for p in self.particles if now - p.born < p.life]
