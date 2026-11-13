"""Particles: little things that fly out during signature moves.

The kinds of particle (numbers, notes, sparks, ...) are defined in the
character files (`particles:`), see robo/characters/README.md.
Positions are in robot coordinates (origin = ground point between his
feet, y up is negative, design pixels); x already includes facing.
"""
import logging
from dataclasses import dataclass

from robo.design import REGISTRY

log = logging.getLogger(__name__)
MAX_PARTICLES = 200


@dataclass(frozen=True)
class Particle:
    glyph: str        # 'note', 'spark', 'star', 'magic', 'heart' or a text character
    born: float
    life: float
    x: float
    y: float
    vx: float
    vy: float
    kind: str = ''    # emitter name (its file says how to draw it)
    index: int = 0    # running number, picks the colour


class Effects:
    def __init__(self, rng):
        self.rng = rng
        self.particles = []
        self._debt = 0.0
        self._count = 0
        self._env = {'rand': rng.uniform, 'choice': lambda *v: rng.choice(v)}

    def emit(self, kind, now, dt, facing):
        """Spawn particles of `kind` at its rate for this frame."""
        em = REGISTRY.emitter(kind)
        if em is None:
            return
        self._debt += em.rate * dt
        while self._debt >= 1:
            self._debt -= 1
            try:
                self._spawn(kind, em, now, facing)
            except Exception as e:          # noqa: BLE001  (a broken file must not crash him)
                log.warning('particles %r: %s', kind, e)
                self._debt = 0.0
                return

    def _spawn(self, kind, em, now, facing):
        env = dict(self._env, f=facing, facing=facing)
        for name, expr in em.defs:
            env[name] = expr(env)
        if em.glyph == 'text':
            glyph = self.rng.choice(em.text) if em.text else '?'
        else:
            glyph = em.glyph
        self._count += 1
        self.particles.append(Particle(
            glyph, now, float(em.life(env)), float(em.at[0](env)), float(em.at[1](env)),
            float(em.velocity[0](env)), float(em.velocity[1](env)), kind, self._count))
        if len(self.particles) > MAX_PARTICLES:
            del self.particles[0]

    def update(self, now):
        self.particles = [p for p in self.particles if now - p.born < p.life]
