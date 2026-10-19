"""Draws the world: background, rings, blocks, balls, trails and particles."""

import math
import random

import pygame

from .settings import BG
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
        world.fx.draw(surf, cam, self.font)

        if s.show_hitboxes:
            self._hitboxes(surf, world, cam)
        if extra:
            extra(surf, cam)

        cam.x -= ox
        cam.y -= oy
        surf.set_clip(None)

    # ------------------------------------------------------------------
    def _background(self, surf, world, cam):
        vp = cam.viewport
        surf.fill(BG, vp)
        s = world.s
        if s.show_grid:
            spacing = 50
            while spacing * cam.zoom < 16:
                spacing *= 2
            x0, y0, x1, y1 = cam.visible_rect()
            gx = math.floor(x0 / spacing) * spacing
            col = (30, 30, 48)
            col2 = (44, 44, 70)
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
        pygame.draw.rect(surf, (70, 70, 110) if s.world_walls else (40, 40, 60), rect,
                         3 if s.world_walls else 1)

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
                circle(surf, mix(BG, b.color, 0.35), (sx, sy), r)
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


def _dim(color, k):
    key = (color, k)
    c = _DIM.get(key)
    if c is None:
        if len(_DIM) > 4000:
            _DIM.clear()
        c = _DIM[key] = mix(BG, color, k)
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
