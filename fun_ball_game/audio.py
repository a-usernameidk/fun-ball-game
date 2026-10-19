"""Procedurally generated sound effects, so the game needs no asset files."""

import array
import math
import random

import pygame

RATE = 22050


def _tone(freq, dur, kind="sine", decay=8.0, sweep=0.0, noise=0.0, vol=0.6):
    n = int(RATE * dur)
    buf = array.array("h")
    phase = 0.0
    for i in range(n):
        t = i / RATE
        f = freq * (1 + sweep * t / dur)
        phase += f / RATE
        if kind == "square":
            s = 1.0 if (phase % 1.0) < 0.5 else -1.0
        elif kind == "tri":
            s = 4 * abs((phase % 1.0) - 0.5) - 1
        else:
            s = math.sin(phase * math.tau)
        if noise:
            s = s * (1 - noise) + random.uniform(-1, 1) * noise
        env = math.exp(-decay * t / dur) * min(1.0, i / 60)
        v = int(max(-1.0, min(1.0, s * env * vol)) * 32767)
        buf.append(v)
        buf.append(v)
    return buf


RECIPES = {
    "tick": dict(freq=900, dur=0.04, kind="tri", decay=6),
    "boing": dict(freq=220, dur=0.18, kind="sine", sweep=1.5, decay=4),
    "squish": dict(freq=140, dur=0.12, kind="sine", noise=0.4, decay=5, sweep=-0.5),
    "bumper": dict(freq=600, dur=0.12, kind="square", decay=6, sweep=0.6, vol=0.35),
    "pop": dict(freq=500, dur=0.07, kind="sine", decay=5, sweep=-0.6),
    "zap": dict(freq=1400, dur=0.12, kind="square", decay=4, sweep=-0.8, vol=0.3),
    "escape": dict(freq=660, dur=0.12, kind="tri", decay=4, sweep=0.5),
    "coin": dict(freq=1200, dur=0.15, kind="square", decay=3, sweep=0.3, vol=0.3),
    "portal": dict(freq=300, dur=0.22, kind="sine", decay=3, sweep=2.0),
    "split": dict(freq=800, dur=0.1, kind="tri", decay=4, sweep=0.8),
    "grow": dict(freq=200, dur=0.25, kind="square", decay=2, sweep=2.0, vol=0.25),
    "shrink": dict(freq=700, dur=0.25, kind="square", decay=2, sweep=-0.7, vol=0.25),
    "goal": dict(freq=520, dur=0.35, kind="tri", decay=2, sweep=0.5),
    "glass": dict(freq=2000, dur=0.25, kind="tri", noise=0.7, decay=5),
    "brick": dict(freq=180, dur=0.2, kind="square", noise=0.5, decay=5, vol=0.4),
    "boom": dict(freq=60, dur=0.6, kind="sine", noise=0.85, decay=5, sweep=-0.5, vol=0.9),
    "click": dict(freq=1000, dur=0.03, kind="tri", decay=5, vol=0.3),
    "place": dict(freq=350, dur=0.06, kind="tri", decay=5, vol=0.5),
    "achievement": dict(freq=880, dur=0.45, kind="tri", decay=2, sweep=0.5),
}


class Audio:
    def __init__(self, settings):
        self.settings = settings
        self.sounds = {}
        self.ok = False
        self.cooldown = {}
        try:
            pygame.mixer.pre_init(RATE, -16, 2, 256)
            pygame.mixer.init(RATE, -16, 2, 256)
            pygame.mixer.set_num_channels(24)
            for name, r in RECIPES.items():
                self.sounds[name] = pygame.mixer.Sound(buffer=_tone(**r).tobytes())
            self.ok = True
        except (pygame.error, Exception):  # no audio device - play silently
            self.ok = False

    def tick(self, dt):
        for k in list(self.cooldown):
            self.cooldown[k] -= dt
            if self.cooldown[k] <= 0:
                del self.cooldown[k]

    def play(self, name, strength=5.0):
        if not self.ok or not self.settings.sound or name in self.cooldown:
            return
        snd = self.sounds.get(name)
        if snd is None:
            return
        self.cooldown[name] = 3.0 if name not in ("boom", "achievement") else 6.0
        vol = self.settings.volume * min(1.0, 0.25 + strength / 10)
        ch = snd.play()
        if ch:
            ch.set_volume(vol)
