"""The simulation: balls, rings, blocks and all the physics that ties them together."""

import math
import random

from . import blocks as blockmod
from .arena import build_rings
from .balls import Ball, BALL_TYPES
from .particles import Particles
from .settings import scheme_color
from .util import hsv

BLOCK_CELL = 128
BLOCK_PAD = 48


class World:
    def __init__(self, settings, audio):
        self.s = settings
        self.audio = audio
        self.fx = Particles()
        self.balls = []
        self.blocks = []
        self.rings = []
        self.paused = False
        self.step_once = False
        self.time = 0.0
        self.shake = 0.0
        self.coins = 0
        self.toasts = []
        self.stats = dict(escapes=0, spawned=0, lost=0, bricks=0, bumps=0, goals=0,
                          teleports=0, explosions=0, glass=0, peak=0, coins_total=0,
                          blocks_placed=0)
        self._bgrid = {}
        self.rebuild_rings()

    # ------------------------------------------------------------------
    # setup / helpers
    # ------------------------------------------------------------------
    def rebuild_rings(self):
        old = [r.angle for r in self.rings]
        self.rings = build_rings(self.s)
        for r, a in zip(self.rings, old):
            r.angle = a
        for b in self.balls:
            b.layer = self.layer_for(math.hypot(b.x, b.y))

    def layer_for(self, d):
        return sum(1 for r in self.rings if r.radius < d)

    def gravity_vec(self):
        a = math.radians(self.s.gravity_angle)
        return math.cos(a) * self.s.gravity, math.sin(a) * self.s.gravity

    def notify(self, text, color=(0, 255, 204)):
        self.toasts.append((text, color))

    def sound(self, name, strength=5.0):
        self.audio.play(name, strength)

    # ------------------------------------------------------------------
    # balls
    # ------------------------------------------------------------------
    def spawn_ball(self, x, y, vx=None, vy=None, kind=None, color=None, radius=None):
        s = self.s
        if len(self.balls) >= s.max_balls:
            if s.limit_action == "Stop Spawning":
                return None
            if s.limit_action == "Pause Simulation":
                if not self.paused:
                    self.paused = True
                    self.notify("Ball limit reached - simulation paused", (255, 204, 0))
                return None
        kind = kind or s.spawn_type
        if vx is None:
            a = random.uniform(0, math.tau)
            sp = s.spawn_speed * random.uniform(0.66, 1.33)
            vx, vy = math.cos(a) * sp, math.sin(a) * sp
        b = Ball(x, y, vx, vy, radius or s.ball_radius, color or scheme_color(s.color_scheme),
                 kind, s.trail_length)
        b.layer = self.layer_for(math.hypot(x, y))
        if b.layer >= len(self.rings) and self.rings:
            b.rewarded = True  # spawned outside: no free escape reward
        if kind == "rainbow":
            b.hue = random.random()
        self.balls.append(b)
        self.stats["spawned"] += 1
        return b

    def spawn_center(self, n):
        for _ in range(n):
            if not self.spawn_ball(random.uniform(-3, 3), random.uniform(-3, 3)):
                break

    def kill_ball(self, b, effect="pop"):
        if not b.alive:
            return
        b.alive = False
        self.stats["lost"] += 1
        fx = self.fx
        if effect == "pop":
            fx.burst(b.x, b.y, b.color, 10, 3, 2.2, 24)
            self.sound("pop", 3)
        elif effect == "zap":
            fx.burst(b.x, b.y, (255, 200, 200), 12, 4, 2, 18, 0)
            self.sound("zap", 4)
        elif effect == "suck":
            fx.burst(b.x, b.y, (190, 120, 255), 5, 1.5, 2, 20, 0)
        elif effect == "goal":
            fx.burst(b.x, b.y, (255, 200, 60), 24, 5, 2.5, 30)

    def clear_balls(self):
        self.balls.clear()

    # ------------------------------------------------------------------
    # blocks
    # ------------------------------------------------------------------
    def add_block(self, blk):
        blk.alive = True
        self.blocks.append(blk)
        self.stats["blocks_placed"] += 1
        return blk

    def remove_block(self, blk):
        blk.alive = False

    def destroy_block(self, blk, effect):
        if not blk.alive:
            return
        self.remove_block(blk)
        if effect == "glass":
            self.stats["glass"] += 1
            self.fx.burst(blk.x, blk.y, (190, 240, 255), 30, 5, 3, 45, 0.15)
            self.sound("glass", 6)
        else:
            self.fx.burst(blk.x, blk.y, blk.color, 26, 4.5, 3.5, 40, 0.15)
            self.sound("brick", 6)

    def clear_blocks(self):
        self.blocks.clear()

    def block_at(self, x, y, pad=4.0):
        for blk in reversed(self.blocks):
            if blk.alive and blk.pick_contains(x, y, pad):
                return blk
        return None

    def add_coins(self, n, x, y):
        self.coins += n
        self.stats["coins_total"] += n
        self.fx.text(x, y, f"+{n}", (255, 215, 60))

    def explode(self, x, y, radius, power):
        self.stats["explosions"] += 1
        for b in self.balls:
            dx, dy = b.x - x, b.y - y
            d = math.hypot(dx, dy)
            if d < radius:
                k = (1 - d / radius) * power
                if d < 1e-3:
                    dx, dy, d = 0.0, -1.0, 1.0
                b.vx += dx / d * k
                b.vy += dy / d * k
        for blk in list(self.blocks):
            if blk.alive:
                d = math.hypot(blk.x - x, blk.y - y) - blk.extent() * 0.5
                if d < radius:
                    blk.on_explosion(self, d, radius)
        self.fx.burst(x, y, (255, 160, 40), 50, 7, 4, 40, 0.02, 0.93)
        self.fx.burst(x, y, (255, 240, 180), 20, 4, 3, 22, 0, 0.9)
        self.fx.burst(x, y, (90, 90, 100), 20, 2, 5, 70, -0.02, 0.95)
        if self.s.screen_shake:
            self.shake = min(30.0, self.shake + power * 0.9)
        self.sound("boom", 10)

    # ------------------------------------------------------------------
    # simulation
    # ------------------------------------------------------------------
    def update(self, frames):
        """Advance by `frames` 60fps-frames of wall-clock time."""
        self.fx.enabled = self.s.particles
        self.shake *= 0.85 ** frames
        if self.paused and not self.step_once:
            self.fx.update(frames * 0.3)
            return
        if self.step_once:
            frames = 1.0
            self.step_once = False
        total = frames * self.s.time_speed
        steps = max(self.s.substeps, int(math.ceil(total / 1.2)))
        steps = min(steps, 12)
        dt = total / steps
        self._build_block_grid()
        crowd = len(self.balls) > 500
        for i in range(steps):
            self._substep(dt, collide=(not crowd) or i == steps - 1)
        self._per_frame(total)
        self.fx.update(total)
        self.time += total

    def _build_block_grid(self):
        grid = {}
        for blk in self.blocks:
            if not blk.alive:
                continue
            x0, y0, x1, y1 = blk.aabb()
            for ix in range(int((x0 - BLOCK_PAD) // BLOCK_CELL), int((x1 + BLOCK_PAD) // BLOCK_CELL) + 1):
                for iy in range(int((y0 - BLOCK_PAD) // BLOCK_CELL), int((y1 + BLOCK_PAD) // BLOCK_CELL) + 1):
                    grid.setdefault((ix, iy), []).append(blk)
        self._bgrid = grid

    def _substep(self, dt, collide=True):
        s = self.s
        for r in self.rings:
            r.update(dt)
        for blk in self.blocks:
            if blk.alive:
                blk.update(dt, self)

        gx, gy = self.gravity_vec()
        drag = max(0.0, 1 - s.air_drag * dt)
        maxv = s.max_speed
        n_rings = len(self.rings)
        hw, hh = s.world_width / 2, s.world_height / 2
        walls = s.world_walls

        for b in self.balls:
            if not b.alive or b.grabbed:
                continue
            b.vx = (b.vx + gx * dt) * drag
            b.vy = (b.vy + gy * dt) * drag
            sp2 = b.vx * b.vx + b.vy * b.vy
            if sp2 > maxv * maxv:
                k = maxv / math.sqrt(sp2)
                b.vx *= k
                b.vy *= k
            b.x += b.vx * dt
            b.y += b.vy * dt
            if b.cooldown > 0:
                b.cooldown -= dt
            if n_rings:
                self._ring_collide(b, n_rings)
            if walls:
                e = s.wall_bounce * b.bounce_mul
                if b.x - b.r < -hw:
                    b.x, b.vx = -hw + b.r, abs(b.vx) * e
                    b.bounces += 1
                elif b.x + b.r > hw:
                    b.x, b.vx = hw - b.r, -abs(b.vx) * e
                    b.bounces += 1
                if b.y - b.r < -hh:
                    b.y, b.vy = -hh + b.r, abs(b.vy) * e
                    b.bounces += 1
                elif b.y + b.r > hh:
                    b.y, b.vy = hh - b.r, -abs(b.vy) * e
                    b.bounces += 1
            elif abs(b.x) > hw + 300 or abs(b.y) > hh + 300:
                b.alive = False

        # blocks
        grid = self._bgrid
        if grid:
            cell = BLOCK_CELL
            for b in self.balls:
                if not b.alive:
                    continue
                lst = grid.get((int(b.x // cell), int(b.y // cell)))
                if not lst:
                    continue
                for blk in lst:
                    if not blk.alive:
                        continue
                    if blk.solid:
                        if not b.ghost:
                            blk.collide(b, self)
                    elif blk.overlaps(b):
                        blk.touch(b, self, dt)
                    if not b.alive:
                        break

        if s.ball_collisions and collide:
            self._ball_collisions()

        if any(not b.alive for b in self.balls):
            self.balls = [b for b in self.balls if b.alive]

    def _contact(self, b, nx, ny, svx, svy, e, grip):
        rvx, rvy = b.vx - svx, b.vy - svy
        vn = rvx * nx + rvy * ny
        if vn >= 0:
            return 0.0
        tx, ty = -ny, nx
        vt = rvx * tx + rvy * ty
        vn2 = -vn * e
        vt2 = vt * (1 - grip)
        b.vx = svx + nx * vn2 + tx * vt2
        b.vy = svy + ny * vn2 + ty * vt2
        b.bounces += 1
        return -vn

    def _ring_hit(self, b, ring, nx, ny, px, py):
        s = self.s
        w = ring.speed
        impact = self._contact(b, nx, ny, -w * py, w * px,
                               s.wall_bounce * b.bounce_mul, s.wall_grip)
        if impact > 0:
            b.vx *= s.energy_boost
            b.vy *= s.energy_boost
            if impact > 3 and random.random() < 0.3:
                self.sound("tick", impact)

    def _gap_edges(self, b, ring, half):
        for ex, ey in ring.gap_edges():
            dx, dy = b.x - ex, b.y - ey
            d = math.hypot(dx, dy)
            rr = b.r + half
            if 1e-6 < d < rr:
                nx, ny = dx / d, dy / d
                b.x += nx * (rr - d)
                b.y += ny * (rr - d)
                self._ring_hit(b, ring, nx, ny, ex, ey)

    def _ring_collide(self, b, n_rings):
        d = math.hypot(b.x, b.y)
        if d < 1e-6:
            return
        L = b.layer
        if L < n_rings:
            ring = self.rings[L]
            R, half = ring.radius, ring.thickness / 2
            if d + b.r > R - half:
                theta = math.atan2(b.y, b.x)
                if ring.in_gap(theta):
                    if d > R:
                        b.layer += 1
                        if b.layer >= n_rings:
                            self._escaped(b)
                    else:
                        self._gap_edges(b, ring, half)
                elif d < R:
                    nx, ny = -b.x / d, -b.y / d
                    target = R - half - b.r
                    b.x, b.y = -nx * target, -ny * target
                    self._ring_hit(b, ring, nx, ny, -nx * R, -ny * R)
                else:
                    b.layer += 1
                    if b.layer >= n_rings:
                        self._escaped(b)
                return
        if L > 0:
            ring = self.rings[L - 1]
            R, half = ring.radius, ring.thickness / 2
            if d - b.r < R + half:
                theta = math.atan2(b.y, b.x)
                if ring.in_gap(theta):
                    if d < R:
                        b.layer -= 1
                    else:
                        self._gap_edges(b, ring, half)
                elif d > R:
                    nx, ny = b.x / d, b.y / d
                    target = R + half + b.r
                    b.x, b.y = nx * target, ny * target
                    self._ring_hit(b, ring, nx, ny, nx * R, ny * R)
                else:
                    b.layer -= 1

    def _escaped(self, b):
        if b.rewarded:
            return
        b.rewarded = True
        self.stats["escapes"] += 1
        self.fx.burst(b.x, b.y, b.color, 14, 3.5, 2.5, 30)
        self.sound("escape", 4)
        self.spawn_center(self.s.balls_per_escape)

    def _ball_collisions(self):
        balls = [b for b in self.balls if not b.ghost and b.alive]
        if len(balls) < 2:
            return
        maxr = max(b.r for b in balls)
        cs = max(16.0, min(100.0, maxr * 2))
        grid = {}
        for b in balls:
            key = (int(b.x // cs), int(b.y // cs))
            cell = grid.get(key)
            if cell is None:
                grid[key] = [b]
            else:
                cell.append(b)
        e1 = 1 + self.s.ball_bounce
        sqrt = math.sqrt
        get = grid.get
        for (cx, cy), cell in grid.items():
            n = len(cell)
            others = [cell]
            for ox, oy in ((1, 0), (0, 1), (1, 1), (1, -1)):
                o = get((cx + ox, cy + oy))
                if o:
                    others.append(o)
            for i in range(n):
                b1 = cell[i]
                x1, y1, r1 = b1.x, b1.y, b1.r
                for oi, other in enumerate(others):
                    for b2 in (other[i + 1:] if oi == 0 else other):
                        dx = b2.x - x1
                        dy = b2.y - y1
                        rr = r1 + b2.r
                        d2 = dx * dx + dy * dy
                        if d2 >= rr * rr or d2 < 1e-9:
                            continue
                        d = sqrt(d2)
                        nx, ny = dx / d, dy / d
                        m1 = 1e9 if b1.grabbed else b1.mass
                        m2 = 1e9 if b2.grabbed else b2.mass
                        tot = m1 + m2
                        ov = rr - d
                        k1, k2 = ov * m2 / tot, ov * m1 / tot
                        x1 -= nx * k1
                        y1 -= ny * k1
                        b2.x += nx * k2
                        b2.y += ny * k2
                        rv = (b2.vx - b1.vx) * nx + (b2.vy - b1.vy) * ny
                        if rv < 0:
                            j = -e1 * rv / (1 / m1 + 1 / m2)
                            b1.vx -= j / m1 * nx
                            b1.vy -= j / m1 * ny
                            b2.vx += j / m2 * nx
                            b2.vy += j / m2 * ny
                b1.x, b1.y = x1, y1

    def _per_frame(self, frames):
        s = self.s
        trails = s.trails
        n_rings = len(self.rings)
        lifetime = s.escaped_lifetime * 60
        magnets = []
        for b in self.balls:
            b.age += frames
            if trails:
                if b.history.maxlen != s.trail_length:
                    b.history = type(b.history)(b.history, maxlen=max(2, s.trail_length))
                b.history.append((b.x, b.y))
            elif b.history:
                b.history.clear()
            if n_rings and b.layer >= n_rings:
                b.free_age += frames
                if lifetime > 0 and b.free_age > lifetime:
                    self.kill_ball(b, "pop")
                    continue
            k = b.kind
            if k == "normal" or k == "tiny":
                continue
            if k == "fire":
                if random.random() < 0.6:
                    self.fx.trail(b.x, b.y, random.choice(((255, 120, 0), (255, 200, 40), (255, 60, 0))),
                                  b.r * 0.4, 20)
            elif k == "rainbow":
                b.hue = (b.hue + 0.008 * frames) % 1.0
                b.color = hsv(b.hue)
            elif k == "bomb":
                if b.bounces >= 6:
                    self.kill_ball(b, "none")
                    self.explode(b.x, b.y, 120, 10)
            elif k == "splitter":
                if b.bounces > 0:
                    b.bounces = 0
                    if b.split_depth < 3 and b.r > 3:
                        b.split_depth += 1
                        b.set_radius(b.r * 0.72)
                        nb = self.spawn_ball(b.x, b.y, -b.vy, b.vx, kind="splitter",
                                             radius=b.r / BALL_TYPES["splitter"]["size"])
                        if nb:
                            nb.split_depth = b.split_depth
                            nb.layer, nb.rewarded = b.layer, b.rewarded
            elif k == "magnet":
                magnets.append(b)
        for m in magnets[:12]:
            for b in self.balls:
                if b is m:
                    continue
                dx, dy = m.x - b.x, m.y - b.y
                d2 = dx * dx + dy * dy
                if 1 < d2 < 180 * 180:
                    d = math.sqrt(d2)
                    a = 0.25 * (1 - d / 180) * frames
                    b.vx += dx / d * a
                    b.vy += dy / d * a
        if any(not b.alive for b in self.balls):
            self.balls = [b for b in self.balls if b.alive]
        if any(not blk.alive for blk in self.blocks):
            self.blocks = [blk for blk in self.blocks if blk.alive]
        if s.limit_action == "Delete Oldest" and len(self.balls) > s.max_balls:
            del self.balls[:len(self.balls) - s.max_balls]
        self.stats["peak"] = max(self.stats["peak"], len(self.balls))
        self.audio.tick(frames)

    # ------------------------------------------------------------------
    # saving
    # ------------------------------------------------------------------
    def to_dict(self):
        return {"version": 2, "settings": self.s.to_dict(),
                "blocks": [b.to_dict() for b in self.blocks if b.alive]}

    def load_dict(self, data):
        self.s.load_dict(data.get("settings", {}))
        self.balls.clear()
        self.blocks.clear()
        self.fx.clear()
        for d in data.get("blocks", []):
            blk = blockmod.from_dict(d)
            if blk:
                self.blocks.append(blk)
        self.rings = []
        self.rebuild_rings()
        self.paused = False

