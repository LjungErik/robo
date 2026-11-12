"""Tiny audio helpers for Robo's voice (pure Python, any platform).

    soften()     the nice voice: gentle pitch lift, volume, smooth fades
    robotize()   the robot voice: metallic shimmer, buzz and "bip-bip" chirps
                 (evil=True: deeper, buzzier, with a descending "bwoo-woo")
    envelope()   loudness per animation frame, to move his mouth
    read_wav() / write_wav()   16-bit mono audio files
"""
import array
import math
import random
import wave

CHIRP_PATTERNS = (               # (frequency Hz, seconds) beeps before he talks
    ((1046, 0.055), (1568, 0.07)),
    ((1568, 0.05), (1175, 0.05), (1760, 0.07)),
    ((880, 0.06), (1318, 0.08)),
)
EVIL_CHIRPS = (                  # low and sinister
    ((330, 0.09), (247, 0.14)),
    ((294, 0.08), (220, 0.08), (165, 0.16)),
)
COMB_SECONDS = 0.0055            # short echo = metallic "tin can" resonance
COMB_GAIN = 0.35
RING_HZ = 62.0                   # gentle ring modulation = robot buzz
RING_DEPTH = 0.18


def chirp(rate, rng=random, level=0.22, patterns=CHIRP_PATTERNS):
    out = array.array('h')
    for freq, secs in rng.choice(patterns):
        n = int(rate * secs)
        for i in range(n):
            fade = min(1.0, i / (rate * 0.006), (n - i) / (rate * 0.012))
            out.append(int(32767 * level * fade * math.sin(2 * math.pi * freq * i / rate)))
        out.extend([0] * int(rate * 0.025))
    out.extend([0] * int(rate * 0.04))
    return out


def robotize(samples, rate, volume=0.8, effect=True, rng=random, evil=False):
    """Return new samples: optional chirp + robot filter, scaled by volume."""
    ring_depth = 0.38 if evil else RING_DEPTH
    comb_gain = 0.5 if evil else COMB_GAIN
    out = (chirp(rate, rng, patterns=EVIL_CHIRPS if evil else CHIRP_PATTERNS) if effect
           else array.array('h'))
    if volume <= 0:
        return array.array('h', [0] * (len(out) + len(samples)))
    if effect:
        for i in range(len(out)):
            out[i] = int(out[i] * volume)
        d = max(1, int(rate * COMB_SECONDS * (1.6 if evil else 1.0)))
        period = rate / (RING_HZ * (0.7 if evil else 1.0))
        table = [1 - ring_depth + ring_depth * math.sin(2 * math.pi * k / period)
                 for k in range(int(period) + 1)]
        tlen = len(table) - 1
        for i, x in enumerate(samples):
            y = x + comb_gain * samples[i - d] if i >= d else x
            y *= table[i % tlen] * volume * 0.8
            out.append(32767 if y > 32767 else -32768 if y < -32768 else int(y))
    else:
        for x in samples:
            y = x * volume
            out.append(32767 if y > 32767 else -32768 if y < -32768 else int(y))
    return out


def resample(samples, factor):
    """Speed up by `factor` (>1 = higher pitch and shorter), linear interpolation."""
    if abs(factor - 1.0) < 1e-3 or not samples:
        return array.array('h', samples)
    n = int(len(samples) / factor)
    out = array.array('h', bytes(2 * n))
    last = len(samples) - 1
    for i in range(n):
        pos = i * factor
        j = int(pos)
        if j >= last:
            out[i] = samples[last]
        else:
            frac = pos - j
            out[i] = int(samples[j] * (1 - frac) + samples[j + 1] * frac)
    return out


def soften(samples, rate, volume=0.8, pitch=1.0):
    """The nice voice: lift the pitch a little (cute, not chipmunk), set the
    volume and fade the edges so nothing clicks."""
    out = resample(samples, pitch)
    fade = int(rate * 0.015)
    n = len(out)
    for i in range(n):
        k = volume
        if i < fade:
            k *= i / fade
        elif i > n - fade:
            k *= (n - i) / fade
        y = out[i] * k
        out[i] = 32767 if y > 32767 else -32768 if y < -32768 else int(y)
    out.extend([0] * int(rate * 0.08))
    return out


def envelope(samples, rate, frame_seconds=1 / 30, delay_frames=0):
    """Mouth opening (0..1) for every animation frame."""
    n = max(1, int(rate * frame_seconds))
    levels = []
    for start in range(0, len(samples), n):
        chunk = samples[start:start + n]
        rms = math.sqrt(sum(x * x for x in chunk[::4]) / max(1, len(chunk[::4])))
        levels.append(rms)
    peak = max(levels) if levels else 0
    if peak <= 0:
        return [0.0] * (len(levels) + delay_frames)
    out, prev = [], 0.0
    for v in levels:
        k = math.sqrt(v / peak)                    # perceptual: quieter sounds still show
        k = 0.0 if k < 0.12 else k
        prev = prev * 0.35 + k * 0.65              # a little smoothing
        out.append(min(1.0, prev))
    return [0.0] * delay_frames + out


def read_wav(path):
    """Returns (samples, sample_rate) of a 16-bit mono WAV file."""
    with wave.open(path) as w:
        if w.getsampwidth() != 2 or w.getnchannels() != 1:
            raise ValueError(f'{path}: expected 16-bit mono audio')
        samples = array.array('h')
        samples.frombytes(w.readframes(w.getnframes()))
        return samples, w.getframerate()


def write_wav(path, samples, rate):
    with wave.open(path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(samples.tobytes())
