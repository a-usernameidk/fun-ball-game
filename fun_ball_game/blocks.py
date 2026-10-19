"""Every placeable block, field and item.

Each class registers itself with @register so the toolbox, the inspector and
the save system all pick it up automatically. To add a new block, subclass
Block, set the class attributes and override whatever hooks you need:

    update(dt, world)       - called every physics step
    on_hit(ball, world, impact, nx, ny)   - solid blocks, after a bounce
    touch(ball, world, dt)  - non-solid blocks, while a ball overlaps
    on_explosion(world, dist, radius)     - something blew up nearby
    draw(surf, cam)         - render
"""

import math
import random

import pygame

from .balls import BALL_ORDER, BALL_TYPES
from .util import TAU, clamp, hsv, mix, point_seg_dist, rotate, scale

REGISTRY = {}
CATEGORIES = {"Blocks": [], "Fields": [], "Items": []}


def register(cls):
    REGISTRY[cls.key] = cls
    CATEGORIES[cls.category].append(cls.key)
    return cls


def create(key, x, y, **kw):
    return REGISTRY[key](x, y, **kw)


def from_dict(d):
    cls = REGISTRY.get(d.get("key"))
    if cls is None:
        return None
    b = cls(d.get("x", 0), d.get("y", 0))
    for k, v in d.items():
        if k not in ("key",) and hasattr(b, k):
            setattr(b, k, v)
    b.after_load()
    return b


# --------------------------------------------------------------------------
# drawing helpers
# --------------------------------------------------------------------------
def poly_alpha(surf, color, alpha, pts):
    """Draw a translucent filled polygon."""
    if len(pts) < 3:
        return
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    x0, y0 = int(min(xs)) - 1, int(min(ys)) - 1
    w, h = int(max(xs)) - x0 + 2, int(max(ys)) - y0 + 2
    if w <= 0 or h <= 0 or w > 4000 or h > 4000:
        return
    tmp = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.polygon(tmp, (*color, alpha), [(x - x0, y - y0) for x, y in pts])
    surf.blit(tmp, (x0, y0))


def circle_alpha(surf, color, alpha, center, radius, width=0):
    radius = int(radius)
    if radius <= 0 or radius > 3000:
        return
    tmp = pygame.Surface((radius * 2 + 2, radius * 2 + 2), pygame.SRCALPHA)
    pygame.draw.circle(tmp, (*color, alpha), (radius + 1, radius + 1), radius, width)
    surf.blit(tmp, (int(center[0]) - radius - 1, int(center[1]) - radius - 1))


def dashed_circle(surf, color, center, radius, dashes=24, phase=0.0, width=2):
    if radius < 3:
        return
    step = TAU / dashes
    cx, cy = center
    for i in range(dashes):
        a0 = phase + i * step
        a1 = a0 + step * 0.55
        pygame.draw.line(surf, color,
                         (cx + math.cos(a0) * radius, cy + math.sin(a0) * radius),
                         (cx + math.cos(a1) * radius, cy + math.sin(a1) * radius),
                         width)


# --------------------------------------------------------------------------
# base class
# --------------------------------------------------------------------------
class Block:
    key = "block"
    name = "Block"
    category = "Blocks"
    desc = ""
    shape = "rect"          # "rect" or "circle"
    solid = True
    color = (150, 150, 160)
    w, h, r = 120.0, 24.0, 20.0
    restitution = 0.85
    friction = 0.02
    touch_pad = 0.0         # how much of the ball radius counts for touching
    rotatable = True
    resizable = True
    props = []              # (attr, label, lo, hi, step) or (attr, label, [choices])
    min_size, max_size = 6, 900

    def __init__(self, x, y, angle=0.0, **kw):
        self.x, self.y, self.angle = float(x), float(y), float(angle)
        self.w, self.h, self.r = type(self).w, type(self).h, type(self).r
        self.alive = True
        self.t = random.uniform(0, 100)
        self.flash = 0.0
        for k, v in kw.items():
            setattr(self, k, v)

    # --- geometry --------------------------------------------------------
    def extent(self):
        if self.shape == "circle":
            return self.r
        return math.hypot(self.w, self.h) / 2

    def aabb(self):
        e = self.extent()
        return self.x - e, self.y - e, self.x + e, self.y + e

    def to_local(self, px, py):
        return rotate(px - self.x, py - self.y, -self.angle)

    def corners(self):
        hw, hh = self.w / 2, self.h / 2
        out = []
        for lx, ly in ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)):
            rx, ry = rotate(lx, ly, self.angle)
            out.append((self.x + rx, self.y + ry))
        return out

    def contains(self, px, py, pad=0.0):
        if self.shape == "circle":
            return math.hypot(px - self.x, py - self.y) <= self.r + pad
        lx, ly = self.to_local(px, py)
        return abs(lx) <= self.w / 2 + pad and abs(ly) <= self.h / 2 + pad

    def pick_contains(self, px, py, pad):
        """Used by the mouse. Large fields are only grabbable near the middle."""
        return self.contains(px, py, pad)

    def overlaps(self, b):
        return self.contains(b.x, b.y, b.r * self.touch_pad)

    def move_to(self, x, y):
        self.x, self.y = x, y

    def vel_at(self, px, py):
        return 0.0, 0.0

    def after_load(self):
        pass

    # --- physics ---------------------------------------------------------
    def update(self, dt, world):
        self.t += dt
        if self.flash > 0:
            self.flash = max(0.0, self.flash - 0.06 * dt)

    def collide(self, b, world):
        if self.shape == "circle":
            dx, dy = b.x - self.x, b.y - self.y
            d = math.hypot(dx, dy)
            rr = self.r + b.r
            if d >= rr:
                return None
            if d < 1e-6:
                nx, ny = 0.0, -1.0
            else:
                nx, ny = dx / d, dy / d
            return self.resolve(b, nx, ny, rr - d, world)
        lx, ly = self.to_local(b.x, b.y)
        hw, hh = self.w / 2, self.h / 2
        cx, cy = clamp(lx, -hw, hw), clamp(ly, -hh, hh)
        dx, dy = lx - cx, ly - cy
        d2 = dx * dx + dy * dy
        if d2 > b.r * b.r:
            return None
        if d2 > 1e-9:
            d = math.sqrt(d2)
            nx, ny, pen = dx / d, dy / d, b.r - d
        else:
            ox, oy = hw - abs(lx), hh - abs(ly)
            if ox < oy:
                nx, ny, pen = (1.0 if lx > 0 else -1.0), 0.0, ox + b.r
            else:
                nx, ny, pen = 0.0, (1.0 if ly > 0 else -1.0), oy + b.r
        wnx, wny = rotate(nx, ny, self.angle)
        return self.resolve(b, wnx, wny, pen, world)

    def resolve(self, b, nx, ny, pen, world):
        b.x += nx * pen
        b.y += ny * pen
        svx, svy = self.vel_at(b.x, b.y)
        rvx, rvy = b.vx - svx, b.vy - svy
        vn = rvx * nx + rvy * ny
        if vn >= 0:
            return 0.0
        tx, ty = -ny, nx
        vt = rvx * tx + rvy * ty
        e = self.restitution * b.bounce_mul
        vn2 = -vn * e
        vt2 = vt * (1.0 - self.friction)
        b.vx = svx + nx * vn2 + tx * vt2
        b.vy = svy + ny * vn2 + ty * vt2
        b.bounces += 1
        impact = -vn
        self.on_hit(b, world, impact, nx, ny)
        return impact

    def on_hit(self, b, world, impact, nx, ny):
        if impact > 2.5:
            world.sound("tick", impact)

    def touch(self, b, world, dt):
        pass

    def on_explosion(self, world, dist, radius):
        pass

    # --- drawing ---------------------------------------------------------
    def screen_poly(self, cam):
        return [cam.w2s(x, y) for x, y in self.corners()]

    def draw(self, surf, cam):
        col = mix(self.color, (255, 255, 255), self.flash * 0.7)
        if self.shape == "circle":
            c = cam.w2s(self.x, self.y)
            pygame.draw.circle(surf, col, c, max(1, self.r * cam.zoom))
            pygame.draw.circle(surf, scale(col, 1.3), c,
                               max(1, self.r * cam.zoom), max(1, int(2 * cam.zoom)))
            return
        pts = self.screen_poly(cam)
        pygame.draw.polygon(surf, scale(col, 0.75), pts)
        pygame.draw.polygon(surf, scale(col, 1.25), pts, max(1, int(2 * cam.zoom)))

    def draw_selection(self, surf, cam, color):
        if self.shape == "circle":
            pygame.draw.circle(surf, color, cam.w2s(self.x, self.y),
                               self.r * cam.zoom + 5, 2)
        else:
            pts = []
            hw, hh = self.w / 2 + 5 / cam.zoom, self.h / 2 + 5 / cam.zoom
            for lx, ly in ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)):
                rx, ry = rotate(lx, ly, self.angle)
                pts.append(cam.w2s(self.x + rx, self.y + ry))
            pygame.draw.polygon(surf, color, pts, 2)

    # --- saving ----------------------------------------------------------
    def to_dict(self):
        d = {"key": self.key, "x": round(self.x, 2), "y": round(self.y, 2),
             "angle": round(self.angle, 4), "w": self.w, "h": self.h, "r": self.r}
        for p in self.props:
            d[p[0]] = getattr(self, p[0])
        return d

    def clone(self):
        d = self.to_dict()
        d["x"] += 30
        d["y"] += 30
        return from_dict(d)


# ==========================================================================
# SOLID BLOCKS
# ==========================================================================
@register
class Wall(Block):
    key, name = "wall", "Stone Wall"
    desc = "A solid wall. Balls bounce off it."
    color = (110, 116, 140)

    def draw(self, surf, cam):
        super().draw(surf, cam)
        if cam.zoom * min(self.w, self.h) > 14:
            # little brick seams
            n = max(1, int(self.w // 40))
            for i in range(1, n):
                lx = -self.w / 2 + self.w * i / n
                a = rotate(lx, -self.h / 2, self.angle)
                b = rotate(lx, self.h / 2, self.angle)
                pygame.draw.line(surf, scale(self.color, 0.55),
                                 cam.w2s(self.x + a[0], self.y + a[1]),
                                 cam.w2s(self.x + b[0], self.y + b[1]), 1)


@register
class Rubber(Block):
    key, name = "rubber", "Bouncer"
    desc = "Super springy. Shoots balls off faster than they arrived."
    color = (255, 70, 170)
    restitution = 1.35
    props = [("restitution", "Bounciness", 0.5, 2.5, 0.05)]

    def on_hit(self, b, world, impact, nx, ny):
        self.flash = 1.0
        if impact > 1.0:
            world.sound("boing", impact)


@register
class Ice(Block):
    key, name = "ice", "Ice"
    desc = "Zero friction and barely any bounce. Balls slide along it."
    color = (150, 220, 255)
    restitution = 0.25
    friction = 0.0

    def draw(self, surf, cam):
        pts = self.screen_poly(cam)
        poly_alpha(surf, self.color, 120, pts)
        pygame.draw.polygon(surf, (220, 245, 255), pts, max(1, int(2 * cam.zoom)))
        a, b = pts[0], pts[2]
        pygame.draw.line(surf, (235, 250, 255), mix_pt(a, b, 0.15), mix_pt(a, b, 0.35), 1)


def mix_pt(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


@register
class Slime(Block):
    key, name = "slime", "Slime"
    desc = "Sticky goo. Kills a ball's bounce and slows it right down."
    color = (90, 220, 70)
    restitution = 0.05
    friction = 0.6

    def on_hit(self, b, world, impact, nx, ny):
        if impact > 1.5:
            world.fx.burst(b.x, b.y, self.color, 4, 1.5, 2, 20)
            world.sound("squish", impact)

    def draw(self, surf, cam):
        super().draw(surf, cam)
        if cam.zoom * self.h > 10:
            for i in range(3):
                lx = math.sin(self.t * 0.03 + i * 2.1) * self.w * 0.35
                px, py = rotate(lx, 0, self.angle)
                pygame.draw.circle(surf, (170, 255, 140),
                                   cam.w2s(self.x + px, self.y + py),
                                   max(1, self.h * 0.15 * cam.zoom))


@register
class Glass(Block):
    key, name = "glass", "Glass"
    desc = "Cracks when hit hard and shatters after a few hits."
    color = (160, 230, 255)
    restitution = 0.7
    props = [("hp", "Hit points", 1, 20, 1)]
    hp = 3

    def on_hit(self, b, world, impact, nx, ny):
        if b.kind == "fire":
            self.hp = 0
        elif impact > 1.8:
            self.hp -= 1
            world.sound("tick", impact)
        if self.hp <= 0:
            world.destroy_block(self, "glass")

    def on_explosion(self, world, dist, radius):
        world.destroy_block(self, "glass")

    def draw(self, surf, cam):
        pts = self.screen_poly(cam)
        poly_alpha(surf, self.color, 70, pts)
        pygame.draw.polygon(surf, (210, 245, 255), pts, max(1, int(2 * cam.zoom)))
        if self.hp <= 2:
            c = cam.w2s(self.x, self.y)
            for i in range(4 - self.hp):
                a = i * 2.3 + 0.5
                L = min(self.w, self.h) * 0.8 * cam.zoom
                pygame.draw.line(surf, (230, 250, 255), c,
                                 (c[0] + math.cos(a) * L, c[1] + math.sin(a) * L), 1)


@register
class Brick(Block):
    key, name = "brick", "Gold Brick"
    desc = "Breakable brick worth coins. Smash it with balls!"
    color = (240, 170, 40)
    w, h = 64.0, 28.0
    restitution = 0.9
    props = [("hp", "Hit points", 1, 30, 1), ("value", "Coins", 1, 100, 1)]
    hp = 4
    value = 5

    def on_hit(self, b, world, impact, nx, ny):
        self.flash = 0.8
        self.hp -= 4 if b.kind == "fire" else 1
        world.sound("tick", 3)
        if self.hp <= 0:
            world.add_coins(self.value, self.x, self.y)
            world.stats["bricks"] += 1
            world.destroy_block(self, "brick")

    def on_explosion(self, world, dist, radius):
        world.add_coins(self.value, self.x, self.y)
        world.stats["bricks"] += 1
        world.destroy_block(self, "brick")

    def draw(self, surf, cam):
        super().draw(surf, cam)
        if cam.zoom * self.h > 12:
            txt = str(max(0, int(self.hp)))
            font = cam_font(int(clamp(self.h * cam.zoom * 0.6, 8, 40)))
            img = font.render(txt, True, (90, 50, 0))
            surf.blit(img, img.get_rect(center=cam.w2s(self.x, self.y)))


_FONTS = {}


def cam_font(size):
    f = _FONTS.get(size)
    if f is None:
        f = pygame.font.Font(None, size + 4)
        _FONTS[size] = f
    return f


@register
class Spike(Block):
    key, name = "spike", "Spikes"
    desc = "Pops any ball that touches it."
    color = (200, 200, 215)
    h = 18.0

    def collide(self, b, world):
        if self.contains(b.x, b.y, b.r):
            world.kill_ball(b, "pop")
        return None

    def draw(self, surf, cam):
        pts = self.screen_poly(cam)
        pygame.draw.polygon(surf, (70, 70, 85), pts)
        n = max(2, int(self.w / 14))
        hw, hh = self.w / 2, self.h / 2
        for side in (-1, 1):
            for i in range(n):
                x0 = -hw + self.w * i / n
                x1 = -hw + self.w * (i + 1) / n
                tri = [(x0, 0), (x1, 0), ((x0 + x1) / 2, side * hh * 1.4)]
                tri = [rotate(a, b, self.angle) for a, b in tri]
                pygame.draw.polygon(surf, (225, 225, 240),
                                    [cam.w2s(self.x + a, self.y + b) for a, b in tri])


@register
class Bumper(Block):
    key, name = "bumper", "Bumper"
    desc = "Pinball bumper. Kicks balls away hard and scores a coin."
    shape = "circle"
    color = (255, 60, 90)
    r = 26.0
    restitution = 1.0
    props = [("power", "Kick power", 2, 30, 0.5)]
    power = 9.0

    def on_hit(self, b, world, impact, nx, ny):
        vn = b.vx * nx + b.vy * ny
        if vn < self.power:
            b.vx += nx * (self.power - vn)
            b.vy += ny * (self.power - vn)
        self.flash = 1.0
        world.stats["bumps"] += 1
        if world.stats["bumps"] % 5 == 0:
            world.add_coins(1, self.x, self.y - self.r)
        world.sound("bumper", 6)
        world.fx.burst(b.x, b.y, (255, 220, 120), 6, 3, 2, 18)

    def draw(self, surf, cam):
        c = cam.w2s(self.x, self.y)
        R = max(2, self.r * cam.zoom)
        col = mix(self.color, (255, 255, 200), self.flash)
        pygame.draw.circle(surf, scale(col, 0.4), c, R * (1.15 + 0.15 * self.flash))
        pygame.draw.circle(surf, col, c, R)
        pygame.draw.circle(surf, (255, 240, 240), c, R * 0.55)
        pygame.draw.circle(surf, col, c, R * 0.35)


@register
class Spinner(Block):
    key, name = "spinner", "Spinner"
    desc = "A rotating paddle that whacks balls around."
    color = (0, 200, 255)
    w, h = 170.0, 14.0
    restitution = 0.9
    props = [("spin", "Spin speed", -0.25, 0.25, 0.005)]
    spin = 0.05

    def update(self, dt, world):
        super().update(dt, world)
        self.angle = (self.angle + self.spin * dt) % TAU

    def vel_at(self, px, py):
        return -self.spin * (py - self.y), self.spin * (px - self.x)

    def draw(self, surf, cam):
        super().draw(surf, cam)
        pygame.draw.circle(surf, (230, 250, 255), cam.w2s(self.x, self.y),
                           max(2, 6 * cam.zoom))


@register
class Mover(Block):
    key, name = "mover", "Platform"
    desc = "Slides back and forth along its length."
    color = (180, 120, 255)
    w, h = 110.0, 20.0
    restitution = 0.85
    props = [("travel", "Travel distance", 20, 600, 5),
             ("speed", "Speed", 0.005, 0.15, 0.005)]
    travel = 150.0
    speed = 0.03

    def __init__(self, x, y, angle=0.0, **kw):
        super().__init__(x, y, angle, **kw)
        self.ox, self.oy = self.x, self.y
        self.phase = 0.0
        self.vx = self.vy = 0.0

    def after_load(self):
        self.ox, self.oy = self.x, self.y

    def move_to(self, x, y):
        self.ox, self.oy = x, y
        self.x, self.y = x, y

    def extent(self):
        return math.hypot(self.w, self.h) / 2 + self.travel

    def aabb(self):
        e = self.extent()
        return self.ox - e, self.oy - e, self.ox + e, self.oy + e

    def update(self, dt, world):
        super().update(dt, world)
        self.phase += self.speed * dt
        off = math.sin(self.phase) * self.travel
        dv = math.cos(self.phase) * self.travel * self.speed
        ca, sa = math.cos(self.angle), math.sin(self.angle)
        self.x, self.y = self.ox + ca * off, self.oy + sa * off
        self.vx, self.vy = ca * dv, sa * dv

    def vel_at(self, px, py):
        return self.vx, self.vy

    def to_dict(self):
        d = super().to_dict()
        d["x"], d["y"] = round(self.ox, 2), round(self.oy, 2)
        return d

    def draw(self, surf, cam):
        ca, sa = math.cos(self.angle), math.sin(self.angle)
        a = cam.w2s(self.ox - ca * self.travel, self.oy - sa * self.travel)
        b = cam.w2s(self.ox + ca * self.travel, self.oy + sa * self.travel)
        pygame.draw.line(surf, scale(self.color, 0.35), a, b, max(1, int(3 * cam.zoom)))
        super().draw(surf, cam)


@register
class Conveyor(Block):
    key, name = "conveyor", "Conveyor"
    desc = "Carries balls along its surface. Negative speed goes backwards."
    color = (90, 95, 110)
    w, h = 180.0, 22.0
    restitution = 0.3
    friction = 0.35
    props = [("speed", "Belt speed", -15, 15, 0.5)]
    speed = 4.0

    def vel_at(self, px, py):
        return math.cos(self.angle) * self.speed, math.sin(self.angle) * self.speed

    def draw(self, surf, cam):
        super().draw(surf, cam)
        if cam.zoom * self.h < 6:
            return
        hw, hh = self.w / 2, self.h / 2
        spacing = 24
        off = (self.t * self.speed) % spacing
        d = 1 if self.speed >= 0 else -1
        x = -hw + off
        while x < hw - 4:
            tri = [(x - 4 * d, -hh * 0.5), (x + 4 * d, 0), (x - 4 * d, hh * 0.5)]
            tri = [rotate(a, b, self.angle) for a, b in tri]
            pygame.draw.lines(surf, (255, 210, 60), False,
                              [cam.w2s(self.x + a, self.y + b) for a, b in tri],
                              max(1, int(2 * cam.zoom)))
            x += spacing


@register
class TNT(Block):
    key, name = "tnt", "TNT"
    desc = "Explodes when hit hard or caught in another blast. Chain reactions!"
    color = (220, 40, 40)
    w, h = 44.0, 44.0
    restitution = 0.6
    props = [("trigger", "Trigger impact", 0.5, 15, 0.5),
             ("blast", "Blast radius", 50, 500, 10),
             ("power", "Blast power", 2, 40, 1)]
    trigger = 3.0
    blast = 160.0
    power = 14.0

    def __init__(self, x, y, angle=0.0, **kw):
        super().__init__(x, y, angle, **kw)
        self.fuse = -1.0

    def arm(self, frames):
        if self.fuse < 0 or self.fuse > frames:
            self.fuse = frames

    def on_hit(self, b, world, impact, nx, ny):
        if impact >= self.trigger or b.kind == "fire":
            self.arm(18)

    def on_explosion(self, world, dist, radius):
        self.arm(6)

    def update(self, dt, world):
        super().update(dt, world)
        if self.fuse >= 0:
            self.fuse -= dt
            self.flash = 1.0 if int(self.fuse) % 4 < 2 else 0.0
            if self.fuse <= 0 and self.alive:
                world.remove_block(self)
                world.explode(self.x, self.y, self.blast, self.power)

    def draw(self, surf, cam):
        super().draw(surf, cam)
        if cam.zoom * self.h > 14:
            font = cam_font(int(clamp(self.h * cam.zoom * 0.45, 8, 40)))
            img = font.render("TNT", True, (255, 240, 220))
            surf.blit(img, img.get_rect(center=cam.w2s(self.x, self.y)))


# ==========================================================================
# FIELDS (balls pass through, but get pushed/pulled)
# ==========================================================================
class Field(Block):
    category = "Fields"
    solid = False
    rotatable = True

    def pick_contains(self, px, py, pad):
        if self.shape == "circle" and self.r > 60:
            return math.hypot(px - self.x, py - self.y) <= 30 + pad
        return self.contains(px, py, pad)


@register
class Attractor(Field):
    key, name = "attractor", "Gravity Well"
    desc = "Pulls balls in. (Old right-click well!)"
    shape = "circle"
    color = (0, 255, 204)
    r = 260.0
    rotatable = False
    props = [("strength", "Strength", 0.05, 3.0, 0.05)]
    strength = 0.6
    sign = 1.0

    def touch(self, b, world, dt):
        dx, dy = self.x - b.x, self.y - b.y
        d = math.hypot(dx, dy)
        if d < 6:
            return
        a = self.sign * self.strength * 0.6 * math.sqrt(max(0.0, 1 - d / self.r)) * dt
        b.vx += dx / d * a
        b.vy += dy / d * a

    def draw(self, surf, cam):
        c = cam.w2s(self.x, self.y)
        R = self.r * cam.zoom
        dashed_circle(surf, scale(self.color, 0.35), c, R, 40, self.t * 0.004)
        for i in range(3):
            k = ((self.t * 0.01 * self.sign + i / 3) % 1.0)
            if self.sign < 0:
                k = 1 - k
            rr = R * (1 - k)
            if rr > 3:
                pygame.draw.circle(surf, scale(self.color, 0.15 + 0.35 * k), c, rr, 1)
        pygame.draw.circle(surf, scale(self.color, 0.5), c, max(3, 16 * cam.zoom))
        pygame.draw.circle(surf, self.color, c, max(2, 9 * cam.zoom))


@register
class Repulsor(Attractor):
    key, name = "repulsor", "Repulsor"
    desc = "Pushes balls away. (Old left-click well!)"
    color = (255, 51, 85)
    sign = -1.0


@register
class BlackHole(Field):
    key, name = "blackhole", "Black Hole"
    desc = "Massive pull. Anything that falls into the core is gone for good."
    shape = "circle"
    color = (170, 90, 255)
    r = 320.0
    rotatable = False
    props = [("strength", "Strength", 0.2, 4.0, 0.1), ("core", "Core size", 8, 80, 1)]
    strength = 1.2
    core = 22.0

    def __init__(self, x, y, angle=0.0, **kw):
        super().__init__(x, y, angle, **kw)
        self.eaten = 0

    def touch(self, b, world, dt):
        dx, dy = self.x - b.x, self.y - b.y
        d = math.hypot(dx, dy)
        if d < self.core:
            world.kill_ball(b, "suck")
            self.eaten += 1
            self.flash = 0.6
            return
        a = self.strength * 45.0 / (d + 30.0) * (1 - d / self.r) * dt
        b.vx += dx / d * a
        b.vy += dy / d * a

    def draw(self, surf, cam):
        c = cam.w2s(self.x, self.y)
        z = cam.zoom
        dashed_circle(surf, (50, 30, 80), c, self.r * z, 48, -self.t * 0.003)
        for i in range(4):
            rr = (self.core * (2.6 - i * 0.35)) * z
            dashed_circle(surf, mix((80, 30, 140), (255, 160, 60), i / 3), c, rr,
                          10 + i * 3, self.t * (0.02 + i * 0.012), max(1, int(3 * z)))
        pygame.draw.circle(surf, mix((0, 0, 0), (255, 255, 255), self.flash * 0.3), c,
                           max(2, self.core * z))
        pygame.draw.circle(surf, (200, 120, 255), c, max(2, self.core * z), 1)


@register
class Vortex(Field):
    key, name = "vortex", "Vortex"
    desc = "Swirls balls around in a whirlpool."
    shape = "circle"
    color = (60, 160, 255)
    r = 220.0
    rotatable = False
    props = [("strength", "Strength", -2.0, 2.0, 0.05)]
    strength = 0.5

    def touch(self, b, world, dt):
        dx, dy = b.x - self.x, b.y - self.y
        d = math.hypot(dx, dy)
        if d < 5:
            return
        k = (1 - d / self.r) * dt
        t = self.strength * 0.6 * k
        b.vx += (-dy / d) * t - dx / d * abs(self.strength) * 0.12 * k
        b.vy += (dx / d) * t - dy / d * abs(self.strength) * 0.12 * k

    def draw(self, surf, cam):
        c = cam.w2s(self.x, self.y)
        R = self.r * cam.zoom
        pygame.draw.circle(surf, scale(self.color, 0.25), c, R, 1)
        sgn = 1 if self.strength >= 0 else -1
        for arm in range(4):
            pts = []
            for i in range(14):
                k = i / 13
                a = arm * TAU / 4 + sgn * (self.t * 0.03 - k * 2.2)
                pts.append((c[0] + math.cos(a) * R * k, c[1] + math.sin(a) * R * k))
            pygame.draw.lines(surf, scale(self.color, 0.6), False, pts, 2)


@register
class Wind(Field):
    key, name = "wind", "Fan Zone"
    desc = "Blows balls in the direction it's pointing."
    color = (200, 230, 255)
    w, h = 240.0, 140.0
    props = [("strength", "Strength", 0.02, 1.5, 0.02)]
    strength = 0.3

    def touch(self, b, world, dt):
        b.vx += math.cos(self.angle) * self.strength * dt
        b.vy += math.sin(self.angle) * self.strength * dt

    def draw(self, surf, cam):
        pts = self.screen_poly(cam)
        poly_alpha(surf, self.color, 18, pts)
        pygame.draw.polygon(surf, scale(self.color, 0.4), pts, 1)
        hw, hh = self.w / 2, self.h / 2
        rnd = random.Random(7)
        for i in range(10):
            ly = rnd.uniform(-hh * 0.85, hh * 0.85)
            lx = ((rnd.uniform(0, self.w) + self.t * (2 + 6 * self.strength)) % self.w) - hw
            a = rotate(lx, ly, self.angle)
            b = rotate(min(hw, lx + 22), ly, self.angle)
            pygame.draw.line(surf, scale(self.color, 0.7), cam.w2s(self.x + a[0], self.y + a[1]),
                             cam.w2s(self.x + b[0], self.y + b[1]), 1)


@register
class Booster(Field):
    key, name = "booster", "Speed Boost"
    desc = "Rockets balls forward in the arrow's direction."
    color = (255, 200, 0)
    w, h = 90.0, 36.0
    props = [("strength", "Boost", 0.1, 4.0, 0.1)]
    strength = 1.0

    def touch(self, b, world, dt):
        b.vx += math.cos(self.angle) * self.strength * dt
        b.vy += math.sin(self.angle) * self.strength * dt
        if random.random() < 0.3:
            world.fx.trail(b.x, b.y, self.color, 2, 12, 0)

    def draw(self, surf, cam):
        pts = self.screen_poly(cam)
        poly_alpha(surf, self.color, 50, pts)
        pygame.draw.polygon(surf, self.color, pts, 1)
        hw, hh = self.w / 2, self.h / 2
        for i in range(3):
            x = -hw * 0.6 + i * hw * 0.5 + (self.t * 0.6 % (hw * 0.5))
            if x > hw * 0.7:
                continue
            tri = [(x - 8, -hh * 0.6), (x + 6, 0), (x - 8, hh * 0.6)]
            tri = [rotate(a, b, self.angle) for a, b in tri]
            pygame.draw.lines(surf, self.color, False,
                              [cam.w2s(self.x + a, self.y + b) for a, b in tri],
                              max(1, int(3 * cam.zoom)))


@register
class SlowField(Field):
    key, name = "slow", "Slow-Mo"
    desc = "Everything inside moves in slow motion."
    shape = "circle"
    color = (180, 100, 255)
    r = 120.0
    rotatable = False
    props = [("strength", "Slowdown", 0.01, 0.5, 0.01)]
    strength = 0.08

    def touch(self, b, world, dt):
        k = max(0.0, 1 - self.strength * dt)
        b.vx *= k
        b.vy *= k

    def draw(self, surf, cam):
        c = cam.w2s(self.x, self.y)
        R = self.r * cam.zoom
        circle_alpha(surf, self.color, 30, c, R)
        pygame.draw.circle(surf, scale(self.color, 0.7), c, R, 1)
        for i in range(12):
            a = i * TAU / 12
            pygame.draw.line(surf, scale(self.color, 0.6),
                             (c[0] + math.cos(a) * R * 0.88, c[1] + math.sin(a) * R * 0.88),
                             (c[0] + math.cos(a) * R, c[1] + math.sin(a) * R), 1)
        a = self.t * 0.01
        pygame.draw.line(surf, self.color, c, (c[0] + math.cos(a) * R * 0.6,
                                               c[1] + math.sin(a) * R * 0.6), 2)


@register
class Water(Field):
    key, name = "water", "Water"
    desc = "Thick and floaty. Balls slow down and bob up to the surface."
    color = (30, 120, 255)
    w, h = 320.0, 150.0
    props = [("drag", "Drag", 0.0, 0.2, 0.005), ("buoyancy", "Buoyancy", 0.0, 4.0, 0.1)]
    drag = 0.03
    buoyancy = 1.6

    def touch(self, b, world, dt):
        k = max(0.0, 1 - self.drag * dt)
        b.vx *= k
        b.vy *= k
        gx, gy = world.gravity_vec()
        b.vx -= gx * self.buoyancy * dt
        b.vy -= gy * self.buoyancy * dt
        if random.random() < 0.02:
            world.fx.trail(b.x, b.y, (160, 210, 255), 2, 30, -0.05)

    def draw(self, surf, cam):
        pts = self.screen_poly(cam)
        poly_alpha(surf, self.color, 70, pts)
        hw, hh = self.w / 2, self.h / 2
        wave = []
        n = 16
        for i in range(n + 1):
            lx = -hw + self.w * i / n
            ly = -hh + math.sin(self.t * 0.08 + i * 0.9) * 3
            px, py = rotate(lx, ly, self.angle)
            wave.append(cam.w2s(self.x + px, self.y + py))
        pygame.draw.lines(surf, (140, 200, 255), False, wave, max(1, int(2 * cam.zoom)))


@register
class AntiGravity(Field):
    key, name = "antigrav", "Anti-Gravity"
    desc = "Flips gravity upside down inside the zone."
    color = (255, 120, 255)
    w, h = 200.0, 200.0
    props = [("strength", "Strength", 0.5, 4.0, 0.1)]
    strength = 1.0

    def touch(self, b, world, dt):
        gx, gy = world.gravity_vec()
        b.vx -= gx * (1 + self.strength) * dt
        b.vy -= gy * (1 + self.strength) * dt

    def draw(self, surf, cam):
        pts = self.screen_poly(cam)
        poly_alpha(surf, self.color, 22, pts)
        pygame.draw.polygon(surf, scale(self.color, 0.5), pts, 1)
        c = cam.w2s(self.x, self.y)
        s = min(self.w, self.h) * 0.2 * cam.zoom
        k = (self.t * 0.02) % 1.0
        y = c[1] + s - k * s * 2
        pygame.draw.lines(surf, self.color, False,
                          [(c[0] - s * 0.6, y + s * 0.5), (c[0], y), (c[0] + s * 0.6, y + s * 0.5)], 2)


# ==========================================================================
# ITEMS / DEVICES
# ==========================================================================
class Item(Block):
    category = "Items"
    solid = False
    shape = "circle"
    touch_pad = 1.0
    rotatable = False


PORTAL_COLORS = [(0, 170, 255), (255, 140, 0), (60, 255, 120), (255, 60, 200),
                 (255, 255, 60), (200, 200, 255)]


@register
class Portal(Item):
    key, name = "portal", "Portal"
    desc = "Place two with the same channel. Balls entering one exit the other."
    r = 26.0
    props = [("channel", "Channel", 0, 5, 1)]
    channel = 0
    resizable = True

    @property
    def color(self):
        return PORTAL_COLORS[int(self.channel) % len(PORTAL_COLORS)]

    def partner(self, world):
        for blk in world.blocks:
            if blk is not self and blk.alive and blk.key == "portal" and \
                    int(blk.channel) == int(self.channel):
                return blk
        return None

    def touch(self, b, world, dt):
        if b.cooldown > 0:
            return
        p = self.partner(world)
        if p is None:
            return
        sp = math.hypot(b.vx, b.vy) or 1.0
        off = p.r + b.r + 2
        world.fx.burst(b.x, b.y, self.color, 8, 2.5, 2, 20, 0)
        b.x, b.y = p.x + b.vx / sp * off, p.y + b.vy / sp * off
        b.history.clear()
        b.cooldown = 20
        p.flash = self.flash = 1.0
        world.fx.burst(b.x, b.y, self.color, 8, 2.5, 2, 20, 0)
        world.sound("portal", 4)
        world.stats["teleports"] += 1

    def draw(self, surf, cam):
        c = cam.w2s(self.x, self.y)
        R = max(3, self.r * cam.zoom)
        col = self.color
        pygame.draw.circle(surf, (5, 5, 15), c, R)
        for i in range(3):
            dashed_circle(surf, scale(col, 0.5 + 0.25 * i + self.flash * 0.5), c,
                          R * (1 - i * 0.22), 8, self.t * (0.05 + 0.03 * i) * (-1) ** i,
                          max(1, int(3 * cam.zoom)))
        pygame.draw.circle(surf, col, c, R, max(1, int(2 * cam.zoom)))


@register
class Splitter(Item):
    key, name = "splitter", "Splitter"
    desc = "Any ball passing through gets cloned."
    r = 22.0
    color = (120, 255, 200)
    props = [("count", "Copies", 2, 6, 1)]
    count = 2

    def touch(self, b, world, dt):
        if b.cooldown > 0 or b.split_depth > 6:
            return
        b.cooldown = 30
        b.split_depth += 1
        sp = math.hypot(b.vx, b.vy)
        base = math.atan2(b.vy, b.vx)
        for i in range(1, int(self.count)):
            a = base + (i - (self.count - 1) / 2) * 0.35
            nb = world.spawn_ball(b.x, b.y, math.cos(a) * sp, math.sin(a) * sp,
                                  kind=b.kind, color=b.color, radius=b.r / max(0.01, BALL_TYPES[b.kind]["size"]))
            if nb:
                nb.cooldown = 30
                nb.split_depth = b.split_depth
                nb.layer = b.layer
                nb.rewarded = b.rewarded
        self.flash = 1.0
        world.sound("split", 4)

    def draw(self, surf, cam):
        c = cam.w2s(self.x, self.y)
        R = max(3, self.r * cam.zoom)
        pts = [(c[0] + math.cos(self.t * 0.03 + i * TAU / 4) * R,
                c[1] + math.sin(self.t * 0.03 + i * TAU / 4) * R) for i in range(4)]
        poly_alpha(surf, self.color, 60 + int(120 * self.flash), pts)
        pygame.draw.polygon(surf, self.color, pts, 2)
        pygame.draw.circle(surf, (255, 255, 255), c, max(1, R * 0.2))


@register
class Cannon(Item):
    key, name = "cannon", "Cannon"
    desc = "Fires balls on a timer in the direction it's facing."
    shape = "rect"
    w, h = 56.0, 30.0
    color = (120, 130, 160)
    rotatable = True
    touch_pad = 0.0
    props = [("interval", "Fire every (frames)", 3, 240, 1),
             ("power", "Power", 1, 30, 0.5),
             ("ball_kind", "Ball type", BALL_ORDER)]
    interval = 40
    power = 10.0
    ball_kind = "normal"

    def __init__(self, x, y, angle=-0.6, **kw):
        super().__init__(x, y, angle, **kw)
        self.timer = 0.0

    def update(self, dt, world):
        super().update(dt, world)
        self.timer += dt
        if self.timer >= self.interval:
            self.timer = 0.0
            ca, sa = math.cos(self.angle), math.sin(self.angle)
            mx, my = self.x + ca * self.w * 0.6, self.y + sa * self.w * 0.6
            a = self.angle + random.uniform(-0.04, 0.04)
            if world.spawn_ball(mx, my, math.cos(a) * self.power, math.sin(a) * self.power,
                                kind=self.ball_kind):
                self.flash = 1.0
                world.fx.burst(mx, my, (255, 220, 150), 6, 3, 2, 14, 0, 0.9, 0.8, self.angle)
                world.sound("pop", 3)

    def draw(self, surf, cam):
        super().draw(surf, cam)
        c = cam.w2s(self.x, self.y)
        pygame.draw.circle(surf, (70, 75, 95), c, max(2, self.h * 0.55 * cam.zoom))
        ca, sa = math.cos(self.angle), math.sin(self.angle)
        if self.flash > 0.3:
            m = cam.w2s(self.x + ca * self.w * 0.6, self.y + sa * self.w * 0.6)
            pygame.draw.circle(surf, (255, 230, 150), m, max(2, 8 * self.flash * cam.zoom))


@register
class Paint(Item):
    key, name = "paint", "Paint Ring"
    desc = "Recolours every ball that passes through."
    r = 26.0
    props = [("hue", "Colour", 0.0, 1.0, 0.01)]
    hue = 0.55

    @property
    def color(self):
        return hsv(self.hue, 0.85, 1.0)

    def touch(self, b, world, dt):
        if b.kind != "rainbow":
            b.color = self.color

    def draw(self, surf, cam):
        c = cam.w2s(self.x, self.y)
        R = max(3, self.r * cam.zoom)
        for i in range(6):
            a0 = i * TAU / 6 + self.t * 0.01
            pygame.draw.arc(surf, hsv(self.hue + i * 0.03, 0.8, 1.0),
                            (c[0] - R, c[1] - R, R * 2, R * 2), a0, a0 + 0.8,
                            max(2, int(5 * cam.zoom)))


@register
class Mushroom(Item):
    key, name = "grow", "Mushroom"
    desc = "Makes balls bigger and heavier."
    r = 18.0
    color = (230, 40, 40)
    props = [("factor", "Grow factor", 1.05, 3.0, 0.05)]
    factor = 1.35

    def touch(self, b, world, dt):
        if b.cooldown > 0:
            return
        b.cooldown = 25
        b.set_radius(min(45.0, b.r * self.factor))
        self.flash = 1.0
        world.sound("grow", 4)

    def draw(self, surf, cam):
        c = cam.w2s(self.x, self.y)
        R = max(3, self.r * cam.zoom)
        pygame.draw.rect(surf, (245, 230, 200), (c[0] - R * 0.35, c[1], R * 0.7, R * 0.8))
        pygame.draw.circle(surf, mix(self.color, (255, 255, 255), self.flash * 0.5),
                           (c[0], c[1] + R * 0.1), R, draw_top_left=True, draw_top_right=True)
        for dx, dy in ((-0.45, -0.35), (0.4, -0.45), (0, -0.75)):
            pygame.draw.circle(surf, (255, 255, 255), (c[0] + dx * R, c[1] + dy * R), max(1, R * 0.16))


@register
class Shrinker(Item):
    key, name = "shrink", "Shrink Ray"
    desc = "Makes balls smaller and lighter."
    r = 18.0
    color = (60, 140, 255)
    props = [("factor", "Shrink factor", 0.3, 0.95, 0.05)]
    factor = 0.7

    def touch(self, b, world, dt):
        if b.cooldown > 0:
            return
        b.cooldown = 25
        b.set_radius(max(2.5, b.r * self.factor))
        self.flash = 1.0
        world.sound("shrink", 4)

    def draw(self, surf, cam):
        c = cam.w2s(self.x, self.y)
        R = max(3, self.r * cam.zoom)
        pygame.draw.circle(surf, scale(self.color, 0.4 + 0.6 * self.flash), c, R)
        pygame.draw.circle(surf, self.color, c, R, 2)
        for i in range(4):
            a = i * TAU / 4 + self.t * 0.02
            o = (c[0] + math.cos(a) * R * 0.85, c[1] + math.sin(a) * R * 0.85)
            n = (c[0] + math.cos(a) * R * 0.35, c[1] + math.sin(a) * R * 0.35)
            pygame.draw.line(surf, (220, 235, 255), o, n, 2)


@register
class Coin(Item):
    key, name = "coin", "Coin"
    desc = "Collect it with a ball for coins. Respawns after a while."
    r = 12.0
    color = (255, 210, 40)
    resizable = False
    props = [("value", "Value", 1, 100, 1), ("respawn", "Respawn (sec)", 1, 60, 1)]
    value = 1
    respawn = 5

    def __init__(self, x, y, angle=0.0, **kw):
        super().__init__(x, y, angle, **kw)
        self.cool = 0.0

    def update(self, dt, world):
        super().update(dt, world)
        if self.cool > 0:
            self.cool -= dt

    def touch(self, b, world, dt):
        if self.cool > 0:
            return
        self.cool = self.respawn * 60
        world.add_coins(int(self.value), self.x, self.y)
        world.fx.burst(self.x, self.y, self.color, 10, 3, 2, 22)
        world.sound("coin", 5)

    def draw(self, surf, cam):
        c = cam.w2s(self.x, self.y)
        R = max(3, self.r * cam.zoom)
        sx = max(1, abs(math.cos(self.t * 0.05)) * R)
        col = self.color if self.cool <= 0 else (70, 60, 30)
        pygame.draw.ellipse(surf, scale(col, 0.7), (c[0] - sx, c[1] - R, sx * 2, R * 2))
        pygame.draw.ellipse(surf, col, (c[0] - sx * 0.75, c[1] - R * 0.75, sx * 1.5, R * 1.5))


@register
class Mine(Item):
    key, name = "mine", "Mine"
    desc = "Blows up the moment a ball touches it."
    r = 14.0
    color = (255, 80, 60)
    props = [("blast", "Blast radius", 40, 500, 10), ("power", "Blast power", 2, 40, 1)]
    blast = 130.0
    power = 12.0

    def touch(self, b, world, dt):
        if self.alive:
            world.remove_block(self)
            world.explode(self.x, self.y, self.blast, self.power)

    def on_explosion(self, world, dist, radius):
        self.touch(None, world, 0)

    def draw(self, surf, cam):
        c = cam.w2s(self.x, self.y)
        R = max(3, self.r * cam.zoom)
        for i in range(8):
            a = i * TAU / 8
            pygame.draw.line(surf, (150, 150, 160), c, (c[0] + math.cos(a) * R * 1.35,
                                                       c[1] + math.sin(a) * R * 1.35), 2)
        pygame.draw.circle(surf, (60, 60, 70), c, R)
        blink = (self.t * 0.08) % 1 < 0.5
        pygame.draw.circle(surf, self.color if blink else (90, 30, 30), c, max(1, R * 0.35))


@register
class Laser(Item):
    key, name = "laser", "Laser"
    desc = "Zaps every ball that crosses its beam. Can rotate."
    shape = "rect"
    w, h = 32.0, 20.0
    color = (255, 40, 60)
    rotatable = True
    touch_pad = 0.0
    props = [("length", "Beam length", 50, 2000, 10), ("spin", "Spin speed", -0.08, 0.08, 0.002)]
    length = 500.0
    spin = 0.0

    def beam(self):
        ca, sa = math.cos(self.angle), math.sin(self.angle)
        ax, ay = self.x + ca * self.w / 2, self.y + sa * self.w / 2
        return ax, ay, ax + ca * self.length, ay + sa * self.length

    def update(self, dt, world):
        super().update(dt, world)
        self.angle = (self.angle + self.spin * dt) % TAU
        ax, ay, bx, by = self.beam()
        x0, x1 = min(ax, bx), max(ax, bx)
        y0, y1 = min(ay, by), max(ay, by)
        for b in world.balls:
            if b.x + b.r < x0 or b.x - b.r > x1 or b.y + b.r < y0 or b.y - b.r > y1:
                continue
            if point_seg_dist(b.x, b.y, ax, ay, bx, by) < b.r + 2:
                world.kill_ball(b, "zap")

    def draw(self, surf, cam):
        ax, ay, bx, by = self.beam()
        a, b = cam.w2s(ax, ay), cam.w2s(bx, by)
        flick = 0.8 + 0.2 * math.sin(self.t * 0.7)
        pygame.draw.line(surf, scale(self.color, 0.35 * flick), a, b, max(3, int(9 * cam.zoom)))
        pygame.draw.line(surf, self.color, a, b, max(1, int(3 * cam.zoom)))
        pygame.draw.line(surf, (255, 220, 220), a, b, 1)
        super().draw(surf, cam)


@register
class Hoop(Item):
    key, name = "hoop", "Goal Hoop"
    desc = "Sink balls in here for 10 coins each."
    r = 30.0
    color = (255, 140, 30)
    props = [("value", "Coins per ball", 1, 100, 1)]
    value = 10

    def touch(self, b, world, dt):
        if math.hypot(b.x - self.x, b.y - self.y) < self.r - b.r * 0.3:
            world.add_coins(int(self.value), self.x, self.y - self.r)
            world.stats["goals"] += 1
            world.kill_ball(b, "goal")
            self.flash = 1.0
            world.sound("goal", 6)

    def draw(self, surf, cam):
        c = cam.w2s(self.x, self.y)
        R = max(3, self.r * cam.zoom)
        circle_alpha(surf, (255, 255, 255), 20 + int(80 * self.flash), c, R)
        for i in range(6):
            a = i * TAU / 6 + self.t * 0.005
            pygame.draw.line(surf, (230, 230, 230), (c[0] + math.cos(a) * R, c[1] + math.sin(a) * R),
                             (c[0] + math.cos(a + 2.2) * R, c[1] + math.sin(a + 2.2) * R), 1)
        pygame.draw.circle(surf, mix(self.color, (255, 255, 255), self.flash), c, R,
                           max(2, int(4 * cam.zoom)))


# ==========================================================================
# v4.1 additions
# ==========================================================================
@register
class SawBlade(Block):
    key, name = "saw", "Saw Blade"
    desc = "A spinning blade that slices any ball that touches it."
    shape = "circle"
    color = (200, 205, 215)
    r = 34.0
    rotatable = False
    props = [("spin", "Spin speed", -0.6, 0.6, 0.01)]
    spin = 0.2

    def update(self, dt, world):
        super().update(dt, world)
        self.angle = (self.angle + self.spin * dt) % TAU

    def collide(self, b, world):
        if math.hypot(b.x - self.x, b.y - self.y) < self.r + b.r - 2:
            world.kill_ball(b, "pop")
            self.flash = 0.6
        return None

    def draw(self, surf, cam):
        c = cam.w2s(self.x, self.y)
        R = max(3, self.r * cam.zoom)
        pts = []
        n = 16
        for i in range(n * 2):
            a = self.angle + i * math.pi / n
            k = 1.0 if i % 2 == 0 else 0.8
            pts.append((c[0] + math.cos(a) * R * k, c[1] + math.sin(a) * R * k))
        pygame.draw.polygon(surf, mix(self.color, (255, 80, 80), self.flash), pts)
        pygame.draw.circle(surf, (120, 125, 140), c, R * 0.6)
        for i in range(3):
            a = self.angle * 2 + i * TAU / 3
            pygame.draw.line(surf, (90, 95, 110), c, (c[0] + math.cos(a) * R * 0.55,
                                                     c[1] + math.sin(a) * R * 0.55), 2)
        pygame.draw.circle(surf, (230, 230, 240), c, max(2, R * 0.14))


@register
class Flipper(Block):
    key, name = "flipper", "Flipper"
    desc = "Pinball flipper. Swings up on a timer and smacks balls into the air."
    color = (255, 90, 60)
    w, h = 130.0, 20.0
    restitution = 0.6
    props = [("interval", "Flip every (frames)", 15, 300, 5),
             ("swing", "Swing angle", 10, 120, 5),
             ("speed", "Flip speed", 0.05, 0.6, 0.01),
             ("mirror", "Mirrored (0/1)", 0, 1, 1)]
    interval = 90
    swing = 50
    speed = 0.25
    mirror = 0

    def __init__(self, x, y, angle=0.0, **kw):
        super().__init__(x, y, angle, **kw)
        self.k = 0.0
        self.up = False
        self.timer = random.uniform(0, 60)
        self.omega = 0.0
        self.cur = self._arm(0.0)

    def extent(self):
        return self.w

    def _arm(self, k):
        """(pivot_x, pivot_y, arm_angle) for flip amount k in [0, 1]."""
        base = self.angle + (math.pi if self.mirror else 0.0)
        px = self.x - math.cos(base) * self.w / 2
        py = self.y - math.sin(base) * self.w / 2
        sgn = -1 if self.mirror else 1
        return px, py, base - sgn * math.radians(self.swing) * k

    def update(self, dt, world):
        super().update(dt, world)
        self.timer += dt
        if self.timer >= self.interval:
            self.timer = 0.0
            self.up = True
        if self.up:
            self.k = min(1.0, self.k + self.speed * dt)
            if self.k >= 1.0:
                self.up = False
        else:
            self.k = max(0.0, self.k - self.speed * 0.35 * dt)
        new = self._arm(self.k)
        self.omega = clamp((new[2] - self.cur[2]) / dt, -0.6, 0.6) if dt > 0 else 0.0
        self.cur = new

    def _pose(self):
        px, py, a = self.cur
        return px + math.cos(a) * self.w / 2, py + math.sin(a) * self.w / 2, a

    def vel_at(self, x, y):
        px, py, _ = self.cur
        return -self.omega * (y - py), self.omega * (x - px)

    def _swap(self):
        saved = (self.x, self.y, self.angle)
        self.x, self.y, self.angle = self._pose()
        return saved

    def collide(self, b, world):
        saved = self._swap()
        try:
            return super().collide(b, world)
        finally:
            self.x, self.y, self.angle = saved

    def draw(self, surf, cam):
        saved = self._swap()
        super().draw(surf, cam)
        px, py, _ = self.cur
        pygame.draw.circle(surf, (255, 220, 200), cam.w2s(px, py), max(2, self.h * 0.45 * cam.zoom))
        self.x, self.y, self.angle = saved


@register
class OneWay(Block):
    key, name = "oneway", "One-Way"
    desc = "Balls pass through in the arrow's direction but bounce off the other side."
    color = (80, 200, 255)
    h = 16.0

    def collide(self, b, world):
        lx, ly = self.to_local(b.x, b.y)
        if ly > 0:  # behind the gate: let it through
            return None
        return super().collide(b, world)

    def draw(self, surf, cam):
        pts = self.screen_poly(cam)
        poly_alpha(surf, self.color, 90, pts)
        pygame.draw.polygon(surf, self.color, pts, max(1, int(2 * cam.zoom)))
        n = max(1, int(self.w / 40))
        for i in range(n):
            lx = -self.w / 2 + self.w * (i + 0.5) / n
            off = (self.t * 0.4) % 8
            tri = [(lx - 6, 4 - off), (lx, -4 - off), (lx + 6, 4 - off)]
            tri = [rotate(a, b, self.angle) for a, b in tri]
            pygame.draw.lines(surf, (230, 250, 255), False,
                              [cam.w2s(self.x + a, self.y + b) for a, b in tri], max(1, int(2 * cam.zoom)))


@register
class Door(Block):
    key, name = "door", "Door"
    desc = "A wall that opens and closes on a timer."
    color = (255, 160, 60)
    w, h = 120.0, 20.0
    props = [("open_time", "Open for (frames)", 10, 600, 10),
             ("closed_time", "Closed for (frames)", 10, 600, 10)]
    open_time = 90
    closed_time = 120

    def is_open(self):
        return (self.t % (self.open_time + self.closed_time)) >= self.closed_time

    def collide(self, b, world):
        if self.is_open():
            return None
        return super().collide(b, world)

    def draw(self, surf, cam):
        pts = self.screen_poly(cam)
        if self.is_open():
            pygame.draw.polygon(surf, scale(self.color, 0.35), pts, 1)
            return
        super().draw(surf, cam)
        left = self.closed_time - (self.t % (self.open_time + self.closed_time))
        if left < 30 and int(left) % 6 < 3:
            pygame.draw.polygon(surf, (255, 255, 255), pts, max(1, int(2 * cam.zoom)))


@register
class Crate(Block):
    key, name = "crate", "Ball Crate"
    desc = "Smash it open to release a bunch of random balls."
    color = (170, 120, 60)
    w, h = 46.0, 46.0
    restitution = 0.7
    props = [("hp", "Hit points", 1, 20, 1), ("count", "Balls inside", 1, 40, 1)]
    hp = 3
    count = 6

    def burst_open(self, world):
        if not self.alive:
            return
        world.destroy_block(self, "brick")
        world.add_coins(2, self.x, self.y)
        for _ in range(int(self.count)):
            a = random.uniform(0, TAU)
            sp = random.uniform(2, 7)
            world.spawn_ball(self.x, self.y, math.cos(a) * sp, math.sin(a) * sp,
                             kind=random.choice(BALL_ORDER))

    def on_hit(self, b, world, impact, nx, ny):
        if impact > 1.5 or b.kind == "fire":
            self.hp -= 3 if b.kind == "fire" else 1
            self.flash = 0.7
            world.sound("tick", 4)
            if self.hp <= 0:
                self.burst_open(world)

    def on_explosion(self, world, dist, radius):
        self.burst_open(world)

    def draw(self, surf, cam):
        super().draw(surf, cam)
        pts = self.screen_poly(cam)
        dark = (110, 75, 35)
        pygame.draw.line(surf, dark, pts[0], pts[2], max(1, int(3 * cam.zoom)))
        pygame.draw.line(surf, dark, pts[1], pts[3], max(1, int(3 * cam.zoom)))


@register
class WhiteHole(Field):
    key, name = "whitehole", "White Hole"
    desc = "The opposite of a black hole: pushes everything away and spits out new balls."
    shape = "circle"
    color = (255, 245, 210)
    r = 200.0
    rotatable = False
    props = [("strength", "Push", 0.0, 3.0, 0.05),
             ("interval", "Spawn every (frames)", 2, 240, 1),
             ("ball_kind", "Ball type", BALL_ORDER)]
    strength = 0.5
    interval = 20
    ball_kind = "normal"

    def __init__(self, x, y, angle=0.0, **kw):
        super().__init__(x, y, angle, **kw)
        self.timer = 0.0

    def update(self, dt, world):
        super().update(dt, world)
        self.timer += dt
        if self.timer >= self.interval:
            self.timer = 0.0
            a = random.uniform(0, TAU)
            if world.spawn_ball(self.x + math.cos(a) * 20, self.y + math.sin(a) * 20,
                                math.cos(a) * 4, math.sin(a) * 4, kind=self.ball_kind):
                self.flash = 0.5

    def touch(self, b, world, dt):
        dx, dy = b.x - self.x, b.y - self.y
        d = math.hypot(dx, dy)
        if d < 4:
            return
        a = self.strength * 0.6 * math.sqrt(max(0.0, 1 - d / self.r)) * dt
        b.vx += dx / d * a
        b.vy += dy / d * a

    def draw(self, surf, cam):
        c = cam.w2s(self.x, self.y)
        R = self.r * cam.zoom
        dashed_circle(surf, scale(self.color, 0.3), c, R, 40, -self.t * 0.004)
        for i in range(4):
            k = (self.t * 0.012 + i / 4) % 1.0
            if R * k > 3:
                pygame.draw.circle(surf, scale(self.color, 0.6 * (1 - k)), c, R * k, 1)
        pygame.draw.circle(surf, scale(self.color, 0.5), c, max(3, 20 * cam.zoom))
        pygame.draw.circle(surf, (255, 255, 255), c, max(2, (12 + 4 * self.flash) * cam.zoom))


@register
class Lava(Field):
    key, name = "lava", "Lava"
    desc = "Sets balls on fire, turning them into fireballs."
    color = (255, 80, 20)
    w, h = 260.0, 90.0
    props = [("drag", "Thickness", 0.0, 0.2, 0.005)]
    drag = 0.04

    def touch(self, b, world, dt):
        k = max(0.0, 1 - self.drag * dt)
        b.vx *= k
        b.vy *= k
        if b.kind not in ("fire", "ghost"):
            b.set_kind("fire", b.color)
            world.fx.burst(b.x, b.y, (255, 160, 40), 6, 2, 2, 20, -0.05)

    def draw(self, surf, cam):
        pts = self.screen_poly(cam)
        poly_alpha(surf, self.color, 120, pts)
        hw, hh = self.w / 2, self.h / 2
        wave = []
        for i in range(17):
            lx = -hw + self.w * i / 16
            ly = -hh + math.sin(self.t * 0.05 + i * 1.3) * 3
            px, py = rotate(lx, ly, self.angle)
            wave.append(cam.w2s(self.x + px, self.y + py))
        pygame.draw.lines(surf, (255, 210, 80), False, wave, max(1, int(3 * cam.zoom)))
        rnd = random.Random(int(self.t / 20))
        for _ in range(3):
            lx, ly = rnd.uniform(-hw * 0.9, hw * 0.9), rnd.uniform(-hh * 0.6, hh * 0.8)
            px, py = rotate(lx, ly, self.angle)
            pygame.draw.circle(surf, (255, 190, 60), cam.w2s(self.x + px, self.y + py),
                               max(1, 4 * cam.zoom), 1)


@register
class FreezeZone(Field):
    key, name = "freeze", "Freeze Zone"
    desc = "Freezes balls solid for a while. Frozen balls act like walls."
    shape = "circle"
    color = (170, 230, 255)
    r = 110.0
    rotatable = False
    props = [("duration", "Freeze time (frames)", 10, 600, 10)]
    duration = 120

    def touch(self, b, world, dt):
        if b.cooldown <= 0 and b.frozen <= 0:
            b.frozen = self.duration
            b.cooldown = self.duration + 45
            world.fx.burst(b.x, b.y, (220, 245, 255), 5, 1.5, 2, 18, 0)

    def draw(self, surf, cam):
        c = cam.w2s(self.x, self.y)
        R = self.r * cam.zoom
        circle_alpha(surf, self.color, 35, c, R)
        pygame.draw.circle(surf, scale(self.color, 0.8), c, R, 1)
        s = R * 0.35
        for i in range(3):
            a = i * math.pi / 3 + self.t * 0.003
            dx, dy = math.cos(a) * s, math.sin(a) * s
            pygame.draw.line(surf, (230, 250, 255), (c[0] - dx, c[1] - dy), (c[0] + dx, c[1] + dy), 2)


@register
class Tesla(Item):
    key, name = "tesla", "Tesla Coil"
    desc = "Zaps the nearest ball in range with lightning."
    r = 18.0
    color = (150, 180, 255)
    props = [("range", "Range", 40, 800, 10), ("interval", "Zap every (frames)", 3, 240, 1)]
    range = 220.0
    interval = 30

    def __init__(self, x, y, angle=0.0, **kw):
        super().__init__(x, y, angle, **kw)
        self.timer = 0.0
        self.bolt = None   # (x, y, life)

    def update(self, dt, world):
        super().update(dt, world)
        if self.bolt:
            bx, by, life = self.bolt
            self.bolt = (bx, by, life - dt) if life - dt > 0 else None
        self.timer += dt
        if self.timer < self.interval:
            return
        best, bd = None, self.range * self.range
        for b in world.balls:
            d2 = (b.x - self.x) ** 2 + (b.y - self.y) ** 2
            if d2 < bd and b.alive:
                best, bd = b, d2
        if best:
            self.timer = 0.0
            self.bolt = (best.x, best.y, 10.0)
            world.kill_ball(best, "zap")

    def draw(self, surf, cam):
        c = cam.w2s(self.x, self.y)
        R = max(3, self.r * cam.zoom)
        dashed_circle(surf, scale(self.color, 0.25), c, self.range * cam.zoom, 30, self.t * 0.002, 1)
        for i in range(4):
            pygame.draw.circle(surf, scale(self.color, 0.5 + i * 0.15), (c[0], c[1] - R * 0.5 * i),
                               R * (1 - i * 0.18))
        top = (c[0], c[1] - R * 1.7)
        pygame.draw.circle(surf, (230, 240, 255), top, max(2, R * 0.35))
        if self.bolt:
            bx, by, life = self.bolt
            end = cam.w2s(bx, by)
            pts = [top]
            for i in range(1, 7):
                k = i / 7
                pts.append((top[0] + (end[0] - top[0]) * k + random.uniform(-8, 8),
                            top[1] + (end[1] - top[1]) * k + random.uniform(-8, 8)))
            pts.append(end)
            pygame.draw.lines(surf, (120, 160, 255), False, pts, 5)
            pygame.draw.lines(surf, (240, 245, 255), False, pts, 2)


@register
class Transmuter(Item):
    key, name = "transmuter", "Transmuter"
    desc = "Turns every ball that passes through into the chosen ball type."
    r = 24.0
    props = [("ball_kind", "Turns balls into", BALL_ORDER)]
    ball_kind = "rainbow"

    @property
    def color(self):
        c = BALL_TYPES[self.ball_kind]["color"]
        return c or hsv(self.t * 0.005)

    def touch(self, b, world, dt):
        if b.kind != self.ball_kind and b.cooldown <= 0:
            b.set_kind(self.ball_kind, b.color)
            if b.kind == "rainbow":
                b.hue = random.random()
            b.cooldown = 10
            self.flash = 1.0
            world.fx.burst(b.x, b.y, self.color, 8, 2, 2, 18, 0)
            world.sound("split", 3)

    def draw(self, surf, cam):
        c = cam.w2s(self.x, self.y)
        R = max(3, self.r * cam.zoom)
        pts = [(c[0] + math.cos(self.t * 0.02 + i * TAU / 6) * R,
                c[1] + math.sin(self.t * 0.02 + i * TAU / 6) * R) for i in range(6)]
        poly_alpha(surf, self.color, 50 + int(100 * self.flash), pts)
        pygame.draw.polygon(surf, self.color, pts, 2)
        pygame.draw.circle(surf, self.color, c, max(2, R * 0.3))


@register
class GravitySwitch(Item):
    key, name = "gswitch", "Gravity Flip"
    desc = "When a ball touches it, the whole world's gravity turns."
    r = 18.0
    color = (255, 120, 255)
    props = [("turn", "Turn by (degrees)", 45, 315, 45)]
    turn = 180

    def __init__(self, x, y, angle=0.0, **kw):
        super().__init__(x, y, angle, **kw)
        self.cool = 0.0
        self.g = 90.0

    def update(self, dt, world):
        super().update(dt, world)
        self.g = world.s.gravity_angle
        if self.cool > 0:
            self.cool -= dt

    def touch(self, b, world, dt):
        if self.cool > 0:
            return
        self.cool = 90
        world.s.gravity_angle = (world.s.gravity_angle + self.turn) % 360
        self.flash = 1.0
        world.sound("portal", 6)
        world.fx.burst(self.x, self.y, self.color, 16, 4, 2, 24, 0)

    def draw(self, surf, cam):
        c = cam.w2s(self.x, self.y)
        R = max(3, self.r * cam.zoom)
        col = self.color if self.cool <= 0 else scale(self.color, 0.4)
        pygame.draw.circle(surf, scale(col, 0.35 + 0.5 * self.flash), c, R)
        pygame.draw.circle(surf, col, c, R, 2)
        a = math.radians(self.g)
        tip = (c[0] + math.cos(a) * R * 0.75, c[1] + math.sin(a) * R * 0.75)
        tail = (c[0] - math.cos(a) * R * 0.6, c[1] - math.sin(a) * R * 0.6)
        pygame.draw.line(surf, (255, 255, 255), tail, tip, 2)
        for s_ in (-0.5, 0.5):
            pygame.draw.line(surf, (255, 255, 255), tip, (tip[0] - math.cos(a + s_) * R * 0.4,
                                                          tip[1] - math.sin(a + s_) * R * 0.4), 2)


@register
class TurboRing(Item):
    key, name = "turbo", "Turbo Ring"
    desc = "Multiplies the speed of every ball that flies through it."
    r = 26.0
    color = (0, 255, 160)
    props = [("factor", "Speed multiplier", 1.1, 4.0, 0.1)]
    factor = 1.6

    def touch(self, b, world, dt):
        if b.cooldown > 0:
            return
        b.cooldown = 20
        b.vx *= self.factor
        b.vy *= self.factor
        self.flash = 1.0
        world.fx.burst(b.x, b.y, self.color, 6, 3, 2, 14, 0, 0.9, 0.6, math.atan2(-b.vy, -b.vx))
        world.sound("escape", 3)

    def draw(self, surf, cam):
        c = cam.w2s(self.x, self.y)
        R = max(3, self.r * cam.zoom)
        pygame.draw.circle(surf, mix(self.color, (255, 255, 255), self.flash), c, R, max(2, int(4 * cam.zoom)))
        for i in range(6):
            a = i * TAU / 6 + self.t * 0.08
            p = (c[0] + math.cos(a) * R * 0.62, c[1] + math.sin(a) * R * 0.62)
            pygame.draw.circle(surf, scale(self.color, 0.7), p, max(1, R * 0.12))


@register
class Teleporter(Item):
    key, name = "teleporter", "Teleporter"
    desc = "Beams balls to a random spot nearby."
    r = 22.0
    color = (200, 120, 255)
    props = [("range", "Range", 50, 3000, 50)]
    range = 600.0

    def touch(self, b, world, dt):
        if b.cooldown > 0:
            return
        world.fx.burst(b.x, b.y, self.color, 8, 2.5, 2, 18, 0)
        a = random.uniform(0, TAU)
        d = random.uniform(self.r + 40, max(self.r + 41, self.range))
        hw, hh = world.s.world_width / 2 - b.r, world.s.world_height / 2 - b.r
        b.x = clamp(self.x + math.cos(a) * d, -hw, hw)
        b.y = clamp(self.y + math.sin(a) * d, -hh, hh)
        b.layer = world.layer_for(math.hypot(b.x, b.y))
        b.history.clear()
        b.cooldown = 30
        self.flash = 1.0
        world.fx.burst(b.x, b.y, self.color, 8, 2.5, 2, 18, 0)
        world.sound("portal", 4)
        world.stats["teleports"] += 1

    def draw(self, surf, cam):
        c = cam.w2s(self.x, self.y)
        R = max(3, self.r * cam.zoom)
        pygame.draw.circle(surf, scale(self.color, 0.25 + 0.5 * self.flash), c, R)
        for i in range(8):
            a = i * TAU / 8 + self.t * 0.05
            k = 0.4 + 0.5 * ((i + self.t * 0.1) % 8) / 8
            pygame.draw.circle(surf, self.color, (c[0] + math.cos(a) * R * k, c[1] + math.sin(a) * R * k),
                               max(1, R * 0.1))
        pygame.draw.circle(surf, self.color, c, R, 2)


@register
class Counter(Item):
    key, name = "counter", "Counter"
    desc = "Counts every ball that passes through and pays out coins every so often."
    r = 26.0
    color = (120, 220, 255)
    props = [("every", "Pay every N balls", 1, 100, 1), ("value", "Coins per payout", 1, 100, 1)]
    every = 10
    value = 5

    def __init__(self, x, y, angle=0.0, **kw):
        super().__init__(x, y, angle, **kw)
        self.count = 0
        self.inside = {}

    def update(self, dt, world):
        super().update(dt, world)
        if self.inside:
            self.inside = {k: v for k, v in self.inside.items() if self.t - v < 3}

    def touch(self, b, world, dt):
        k = id(b)
        if k not in self.inside:
            self.count += 1
            self.flash = 0.6
            if self.count % int(self.every) == 0:
                world.add_coins(int(self.value), self.x, self.y - self.r)
                world.sound("coin", 4)
        self.inside[k] = self.t

    def draw(self, surf, cam):
        c = cam.w2s(self.x, self.y)
        R = max(3, self.r * cam.zoom)
        pygame.draw.circle(surf, scale(self.color, 0.15 + 0.4 * self.flash), c, R)
        pygame.draw.circle(surf, self.color, c, R, 2)
        if R > 10:
            font = cam_font(int(clamp(R * 0.8, 8, 40)))
            img = font.render(str(self.count), True, (230, 245, 255))
            surf.blit(img, img.get_rect(center=c))
