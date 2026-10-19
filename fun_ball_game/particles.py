"""Lightweight particle effects (sparks, shards, smoke, text pop-ups)."""

import math
import random

import pygame

from .util import mix
from .settings import BG

MAX_PARTICLES = 4000
_FADE = {}


class Particles:
    def __init__(self):
        # each particle: [x, y, vx, vy, life, max_life, color, size, gravity, drag]
        self.items = []
        self.texts = []  # [x, y, text, color, life]
        self.enabled = True
        self.max = MAX_PARTICLES

    def clear(self):
        self.items.clear()
        self.texts.clear()

    def burst(self, x, y, color, n=12, speed=3.0, size=2.5, life=30,
              gravity=0.05, drag=0.96, spread=math.tau, angle=0.0):
        if not self.enabled:
            return
        room = self.max - len(self.items)
        n = min(n, room)
        for _ in range(n):
            a = angle + random.uniform(-spread / 2, spread / 2)
            sp = random.uniform(0.2, 1.0) * speed
            lf = random.uniform(0.6, 1.0) * life
            self.items.append([x, y, math.cos(a) * sp, math.sin(a) * sp, lf, lf,
                               color, random.uniform(0.6, 1.0) * size, gravity, drag])

    def trail(self, x, y, color, size=2.0, life=18, gravity=-0.03):
        if not self.enabled or len(self.items) >= self.max:
            return
        self.items.append([x + random.uniform(-2, 2), y + random.uniform(-2, 2),
                           random.uniform(-0.4, 0.4), random.uniform(-0.4, 0.4),
                           life, life, color, size, gravity, 0.97])

    def text(self, x, y, text, color):
        if len(self.texts) < 60:
            self.texts.append([x, y, text, color, 60.0])

    def update(self, dt):
        keep = []
        for p in self.items:
            p[4] -= dt
            if p[4] <= 0:
                continue
            p[2] = p[2] * p[9] ** dt
            p[3] = p[3] * p[9] ** dt + p[8] * dt
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            keep.append(p)
        self.items = keep
        tk = []
        for t in self.texts:
            t[4] -= dt
            t[1] -= 0.6 * dt
            if t[4] > 0:
                tk.append(t)
        self.texts = tk

    def draw(self, surf, cam, font, bg=BG):
        z = cam.zoom
        vx0, vy0, vx1, vy1 = cam.visible_rect()
        cx, cy = cam.x, cam.y
        ox, oy = cam.viewport.centerx, cam.viewport.centery
        circle = pygame.draw.circle
        cache = _FADE
        for x, y, _, _, life, ml, color, size, _, _ in self.items:
            if x < vx0 or x > vx1 or y < vy0 or y > vy1:
                continue
            k = life / ml
            level = int(k * 8)
            key = (color, level, bg)
            col = cache.get(key)
            if col is None:
                if len(cache) > 5000:
                    cache.clear()
                col = cache[key] = mix(bg, color, min(1.0, (level + 1) / 8 * 1.4))
            circle(surf, col, ((x - cx) * z + ox, (y - cy) * z + oy),
                   max(1, int(size * z * (0.4 + 0.6 * k))))
        for x, y, text, color, life in self.texts:
            sx, sy = cam.w2s(x, y)
            img = font.render(text, True, mix(bg, color, min(1.0, life / 30)))
            surf.blit(img, img.get_rect(center=(int(sx), int(sy))))
