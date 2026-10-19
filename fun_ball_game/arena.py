"""The spinning rings with gaps that balls try to escape from."""

import math

from .settings import RING_COLORS
from .util import TAU, angle_in_arc


class Ring:
    def __init__(self, radius, speed, gaps, gap_size, thickness, color, angle=0.0):
        self.radius = radius
        self.speed = speed          # radians per frame
        self.gaps = max(0, gaps)
        self.gap_size = gap_size    # radians
        self.thickness = thickness
        self.color = color
        self.angle = angle

    def update(self, dt):
        self.angle = (self.angle + self.speed * dt) % TAU

    def gap_starts(self):
        if self.gaps <= 0:
            return []
        step = TAU / self.gaps
        return [(self.angle + i * step) % TAU for i in range(self.gaps)]

    def in_gap(self, theta):
        for s in self.gap_starts():
            if angle_in_arc(theta, s, self.gap_size):
                return True
        return False

    def gap_edges(self):
        """World-space (relative to centre) points at both ends of every gap."""
        pts = []
        for s in self.gap_starts():
            for a in (s, s + self.gap_size):
                pts.append((math.cos(a) * self.radius, math.sin(a) * self.radius))
        return pts

    def solid_arcs(self):
        """List of (start_angle, width) for the parts of the ring that are wall."""
        starts = self.gap_starts()
        if not starts:
            return [(0.0, TAU)]
        step = TAU / self.gaps
        w = step - self.gap_size
        if w <= 0:
            return []
        return [(s + self.gap_size, w) for s in starts]


def build_rings(s):
    """Create the ring list from Settings."""
    rings = []
    for i in range(s.ring_count):
        direction = -1 if (s.alternate_spin and i % 2) else 1
        rings.append(Ring(
            radius=s.ring_radius + i * s.ring_spacing,
            speed=s.rotation_speed * direction * (1 + 0.15 * i),
            gaps=s.gap_count,
            gap_size=s.gap_size,
            thickness=s.ring_thickness,
            color=RING_COLORS[i % len(RING_COLORS)],
            angle=i * 0.9,
        ))
    return rings
