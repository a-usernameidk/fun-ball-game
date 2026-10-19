"""Small maths / colour helpers shared by everything."""

import colorsys
import math

TAU = math.tau


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def lerp(a, b, t):
    return a + (b - a) * t


def mix(c1, c2, t):
    """Blend two RGB colours. t=0 -> c1, t=1 -> c2."""
    return (int(c1[0] + (c2[0] - c1[0]) * t),
            int(c1[1] + (c2[1] - c1[1]) * t),
            int(c1[2] + (c2[2] - c1[2]) * t))


def scale(c, k):
    return (min(255, int(c[0] * k)), min(255, int(c[1] * k)),
            min(255, int(c[2] * k)))


def hsv(h, s=1.0, v=1.0):
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
    return (int(r * 255), int(g * 255), int(b * 255))


def rotate(x, y, ang):
    c, s = math.cos(ang), math.sin(ang)
    return x * c - y * s, x * s + y * c


def norm_angle(a):
    a %= TAU
    return a + TAU if a < 0 else a


def angle_in_arc(theta, start, width):
    """True if angle theta lies in the arc [start, start+width]."""
    return (theta - start) % TAU <= width


def point_seg_dist(px, py, ax, ay, bx, by):
    abx, aby = bx - ax, by - ay
    l2 = abx * abx + aby * aby
    if l2 == 0:
        return math.hypot(px - ax, py - ay)
    t = clamp(((px - ax) * abx + (py - ay) * aby) / l2, 0.0, 1.0)
    return math.hypot(px - (ax + abx * t), py - (ay + aby * t))


class Camera:
    """Maps world coordinates to a screen viewport (pan + zoom)."""

    def __init__(self, viewport, x=0.0, y=0.0, zoom=1.0):
        self.viewport = viewport  # pygame.Rect
        self.x, self.y, self.zoom = x, y, zoom

    def w2s(self, x, y):
        return ((x - self.x) * self.zoom + self.viewport.centerx,
                (y - self.y) * self.zoom + self.viewport.centery)

    def s2w(self, sx, sy):
        return ((sx - self.viewport.centerx) / self.zoom + self.x,
                (sy - self.viewport.centery) / self.zoom + self.y)

    def zoom_at(self, sx, sy, factor):
        wx, wy = self.s2w(sx, sy)
        self.zoom = clamp(self.zoom * factor, 0.2, 4.0)
        nx, ny = self.s2w(sx, sy)
        self.x += wx - nx
        self.y += wy - ny

    def visible_rect(self):
        x0, y0 = self.s2w(self.viewport.left, self.viewport.top)
        x1, y1 = self.s2w(self.viewport.right, self.viewport.bottom)
        return x0, y0, x1, y1
