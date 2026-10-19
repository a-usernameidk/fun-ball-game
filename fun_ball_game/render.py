"""Draws the world: background, rings, blocks, balls, trails and particles."""

import math
import random

import pygame

from .settings import BG, theme
from .util import TAU, mix, scale

_GLOW = {}


def glow_surface(color, radius):
    key = (color, radius)
    s = _GLOW.get(key)
    if s is None:
        if len(_GLOW) > 1200:
            _GLOW.clear()
        size = radius * 2
        s = pygame.Surface((size, size))
        s.fill((0, 0, 0))
        steps = max(3, min(10, radius // 2))
        for i in range(steps):
            k = (i + 1) / steps
            rr = int(radius * (1 - k * 0.85))
            c = scale(color, 0.06 + 0.10 * k)
            pygame.draw.circle(s, c, (radius, radius), max(1, rr))
        _GLOW[key] = s
    return s


class Renderer:
    def __init__(self):
        self.font = pygame.font.Font(None, 22)
        self.amb = []          # ambient background particles (bubbles, embers...)
        self.amb_key = None

    def draw(self, surf, world, cam, extra=None):
        s = world.s
        vp = cam.viewport
        surf.set_clip(vp)
        self._background(surf, world, cam)

        # shake: temporarily nudge the camera
        ox = oy = 0.0
        if world.shake > 0.3:
            ox = random.uniform(-1, 1) * world.shake / cam.zoom
            oy = random.uniform(-1, 1) * world.shake / cam.zoom
            cam.x += ox
            cam.y += oy

        vx0, vy0, vx1, vy1 = cam.visible_rect()

        # fields first so solid stuff draws on top of them
        for blk in world.blocks:
            if blk.alive and not blk.solid and blk.category == "Fields" and _visible(blk, vx0, vy0, vx1, vy1):
                blk.draw(surf, cam)
        self._rings(surf, world, cam)
        for blk in world.blocks:
            if blk.alive and (blk.solid or blk.category != "Fields") and _visible(blk, vx0, vy0, vx1, vy1):
                blk.draw(surf, cam)

        self._balls(surf, world, cam, vx0, vy0, vx1, vy1)
        world.fx.draw(surf, cam, self.font, _BG)

        if s.show_hitboxes:
            self._hitboxes(surf, world, cam)
        if extra:
            extra(surf, cam)

        cam.x -= ox
        cam.y -= oy
        surf.set_clip(None)

    # ------------------------------------------------------------------
    def _background(self, surf, world, cam):
        global _BG
        vp = cam.viewport
        s = world.s
        th = theme(s.theme)
        if th["bg"] != _BG:
            _BG = th["bg"]
            _DIM.clear()
        surf.fill(_BG, vp)
        if th["fx"]:
            self._ambient(surf, th, cam)
        if s.show_grid:
            spacing = 50
            while spacing * cam.zoom < 16:
                spacing *= 2
            x0, y0, x1, y1 = cam.visible_rect()
            gx = math.floor(x0 / spacing) * spacing
            col, col2 = th["grid"], th["grid2"]
            while gx <= x1:
                sx, _ = cam.w2s(gx, 0)
                gy = math.floor(y0 / spacing) * spacing
                major_x = (gx // spacing) % 4 == 0
                while gy <= y1:
                    _, sy = cam.w2s(0, gy)
                    big = major_x and (gy // spacing) % 4 == 0
                    surf.fill(col2 if big else col, (int(sx) - 1, int(sy) - 1, 2 + big, 2 + big))
                    gy += spacing
                gx += spacing
        hw, hh = s.world_width / 2, s.world_height / 2
        a = cam.w2s(-hw, -hh)
        b = cam.w2s(hw, hh)
        rect = pygame.Rect(int(a[0]), int(a[1]), int(b[0] - a[0]), int(b[1] - a[1]))
        pygame.draw.rect(surf, th["border"] if s.world_walls else mix(_BG, th["border"], 0.4), rect,
                         3 if s.world_walls else 1)

    def _ambient(self, surf, th, cam):
        """Decorative background life: stars, bubbles, embers, fireflies, rain."""
        vp = cam.viewport
        kind = th["fx"]
        t = pygame.time.get_ticks() / 1000.0
        key = (kind, vp.size)
        rnd = random.Random(42)
        if self.amb_key != key:
            self.amb_key = key
            n = 160 if kind == "stars" else 70
            self.amb = [[rnd.random() * vp.w, rnd.random() * vp.h, rnd.random(), rnd.random()]
                        for _ in range(n)]
        W, H = vp.w, vp.h
        if kind == "stars":
            for i, (u, v, a, b) in enumerate(self.amb):
                depth = 0.15 + 0.5 * a
                x = (u - cam.x * depth * cam.zoom) % W
                y = (v - cam.y * depth * cam.zoom) % H
                tw = 0.5 + 0.5 * math.sin(t * (1 + 2 * b) + i)
                c = mix(_BG, (210, 220, 255), 0.25 + 0.6 * tw * a)
                size = 1 if a < 0.8 else 2
                surf.fill(c, (vp.x + int(x), vp.y + int(y), size, size))
            return
        for p in self.amb:
            u, v, a, b = p
            if kind == "bubbles":
                p[1] = (v - (0.3 + a * 0.9)) % H
                x = (u + math.sin(t * 1.5 + b * 10) * 6) % W
                pygame.draw.circle(surf, mix(_BG, (150, 210, 255), 0.25 + 0.2 * a),
                                   (vp.x + x, vp.y + p[1]), 2 + a * 4, 1)
            elif kind == "embers":
                p[1] = (v - (0.4 + a * 1.2)) % H
                x = (u + math.sin(t + b * 6) * 10) % W
                k = p[1] / H
                surf.fill(mix(_BG, (255, 140 + int(80 * a), 40), 0.2 + 0.6 * k),
                          (vp.x + int(x), vp.y + int(p[1]), 2, 2))
            elif kind == "fireflies":
                x = (u + math.sin(t * 0.4 + b * 20) * 40) % W
                y = (v + math.cos(t * 0.3 + a * 20) * 30) % H
                glow = max(0.0, math.sin(t * (0.8 + a) + b * 30))
                if glow > 0.1:
                    pygame.draw.circle(surf, mix(_BG, (200, 255, 120), glow * 0.8),
                                       (vp.x + x, vp.y + y), 1 + glow * 2)
            elif kind == "rain":
                p[1] = (v + 6 + a * 8) % H
                p[0] = (u + 1.5) % W
                col = mix(_BG, (255, 60, 200) if b < 0.5 else (0, 220, 255), 0.25 + 0.3 * a)
                x0, y0 = vp.x + p[0], vp.y + p[1]
                pygame.draw.line(surf, col, (x0, y0), (x0 - 3, y0 - 12 - a * 10), 1)

    def _rings(self, surf, world, cam):
        z = cam.zoom
        cx, cy = cam.w2s(0, 0)
        for ring in world.rings:
            R = ring.radius * z
            half = max(1.0, ring.thickness * z / 2)
            for start, width in ring.solid_arcs():
                if world.s.glow:
                    _arc_poly(surf, scale(ring.color, 0.22), cx, cy, R, half * 2.6, start, width)
                _arc_poly(surf, ring.color, cx, cy, R, half, start, width)
                _arc_poly(surf, mix(ring.color, (255, 255, 255), 0.55), cx, cy, R, max(0.5, half * 0.25),
                          start, width)

    def _balls(self, surf, world, cam, vx0, vy0, vx1, vy1):
        s = world.s
        z = cam.zoom
        circle = pygame.draw.circle
        glow = s.glow
        if s.trails:
            # inline world->screen transform: this loop runs for every ball
            cx, cy = cam.x, cam.y
            ox, oy = cam.viewport.centerx, cam.viewport.centery
            crowd = len(world.balls) > s.detail_threshold * 0.66
            lines = pygame.draw.lines
            for b in world.balls:
                h = b.history
                if len(h) > 1 and vx0 - 50 < b.x < vx1 + 50 and vy0 - 50 < b.y < vy1 + 50:
                    pts = [((x - cx) * z + ox, (y - cy) * z + oy) for x, y in h]
                    pts.append(((b.x - cx) * z + ox, (b.y - cy) * z + oy))
                    w = max(1, int(b.r * z * 0.7))
                    if crowd or len(pts) < 6:
                        lines(surf, _dim(b.color, 0.4), False, pts, w)
                    else:
                        half = len(pts) // 2
                        lines(surf, _dim(b.color, 0.18), False, pts[:half + 1], max(1, w // 2))
                        lines(surf, _dim(b.color, 0.45), False, pts[half:], w)
        cx, cy = cam.x, cam.y
        ox, oy = cam.viewport.centerx, cam.viewport.centery
        big_crowd = len(world.balls) > s.detail_threshold
        if big_crowd:
            glow = False  # level of detail: keep the frame rate up in huge swarms
        for b in world.balls:
            if b.x + b.r < vx0 or b.x - b.r > vx1 or b.y + b.r < vy0 or b.y - b.r > vy1:
                continue
            sx, sy = (b.x - cx) * z + ox, (b.y - cy) * z + oy
            r = b.r * z
            ri = max(1, int(r))
            if big_crowd and b.kind == "normal" and b.frozen <= 0:
                circle(surf, b.color, (sx, sy), r)
                continue
            if glow and ri >= 2:
                g = glow_surface(b.color, ri * 2 + 2)
                surf.blit(g, (sx - ri * 2 - 2, sy - ri * 2 - 2), special_flags=pygame.BLEND_RGB_ADD)
            if b.ghost:
                circle(surf, _dim(b.color, 0.35), (sx, sy), r)
                circle(surf, b.color, (sx, sy), r, 1)
                continue
            if b.kind == "bomb":
                circle(surf, (40, 40, 48), (sx, sy), r)
                left = max(0, 6 - b.bounces)
                circle(surf, (255, 60 + 30 * left, 40), (sx, sy - r * 0.9), max(1, r * 0.3))
                continue
            circle(surf, b.color, (sx, sy), r)
            if ri >= 4:
                circle(surf, mix(b.color, (255, 255, 255), 0.6), (sx - r * 0.3, sy - r * 0.3), r * 0.32)
            if b.frozen > 0:
                circle(surf, (200, 240, 255), (sx, sy), r + 2, 2)
            if b.kind == "magnet" and ri >= 4:
                circle(surf, (255, 255, 255), (sx, sy), r, 1)
            elif b.kind == "heavy" and ri >= 4:
                circle(surf, (90, 92, 110), (sx, sy), r, max(1, int(r * 0.2)))

    def _hitboxes(self, surf, world, cam):
        y = (255, 255, 0)
        for b in world.balls:
            pygame.draw.circle(surf, y, cam.w2s(b.x, b.y), max(1, b.r * cam.zoom), 1)
        for blk in world.blocks:
            x0, y0, x1, y1 = blk.aabb()
            a, b = cam.w2s(x0, y0), cam.w2s(x1, y1)
            pygame.draw.rect(surf, (255, 255, 0), (a[0], a[1], b[0] - a[0], b[1] - a[1]), 1)
        c = cam.w2s(0, 0)
        for ring in world.rings:
            for st in ring.gap_starts():
                e = cam.w2s(math.cos(st) * ring.radius, math.sin(st) * ring.radius)
                pygame.draw.line(surf, y, c, e, 1)
        img = self.font.render(f"balls {len(world.balls)}  blocks {len(world.blocks)}  "
                               f"particles {len(world.fx.items)}", True, y)
        surf.blit(img, (cam.viewport.x + 10, cam.viewport.bottom - 24))


_DIM = {}
_BG = BG


def _dim(color, k):
    key = (color, k)
    c = _DIM.get(key)
    if c is None:
        if len(_DIM) > 4000:
            _DIM.clear()
        c = _DIM[key] = mix(_BG, color, k)
    return c


def _visible(blk, x0, y0, x1, y1):
    e = blk.extent() + 40
    return x0 - e < blk.x < x1 + e and y0 - e < blk.y < y1 + e


def _arc_poly(surf, color, cx, cy, R, half, start, width):
    if width <= 0:
        return
    n = max(4, int(width * R / 6))
    n = min(n, 400)
    outer, inner = [], []
    for i in range(n + 1):
        a = start + width * i / n
        ca, sa = math.cos(a), math.sin(a)
        outer.append((cx + ca * (R + half), cy + sa * (R + half)))
        inner.append((cx + ca * (R - half), cy + sa * (R - half)))
    if width >= TAU - 1e-6:
        pygame.draw.circle(surf, color, (cx, cy), R + half, max(1, int(half * 2)))
        return
    pygame.draw.polygon(surf, color, outer + inner[::-1])
