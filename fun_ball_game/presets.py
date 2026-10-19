"""Ready-made levels you can load from the menu or the World tab."""

import math

from .blocks import create
from .settings import PREF_FIELDS


def _start(world, **settings):
    world.s.reset()
    for k, v in settings.items():
        if k not in PREF_FIELDS:  # never override the player's own preferences
            setattr(world.s, k, v)
    world.balls.clear()
    world.blocks.clear()
    world.fx.clear()
    world.rings = []
    world.rebuild_rings()
    world.paused = False


def _add(world, key, x, y, angle=0.0, **kw):
    blk = create(key, x, y, angle=angle, **kw)
    world.blocks.append(blk)
    return blk


def classic(world):
    """The original game: one spinning ring, one gap."""
    _start(world)
    world.spawn_center(1)


def nested(world):
    _start(world, ring_count=4, ring_radius=140, ring_spacing=60, gap_count=2, gap_size=0.45,
           rotation_speed=0.03, balls_per_escape=3, max_balls=800)
    world.spawn_center(3)


def pinball(world):
    _start(world, ring_count=1, ring_radius=150, gap_count=3, gap_size=0.5, max_balls=500,
           escaped_lifetime=30, world_width=1800, world_height=1300)
    for i in range(6):
        a = i * math.tau / 6
        _add(world, "bumper", math.cos(a) * 340, math.sin(a) * 340)
    for i in range(4):
        a = i * math.tau / 4 + math.pi / 4
        _add(world, "spinner", math.cos(a) * 480, math.sin(a) * 480, spin=0.06 * (-1) ** i)
    _add(world, "rubber", -500, 560, angle=0.35, w=360)
    _add(world, "rubber", 500, 560, angle=-0.35, w=360)
    _add(world, "hoop", 0, 560)
    for i in range(10):
        _add(world, "coin", -450 + i * 100, -560)
    world.spawn_center(2)


def portals(world):
    _start(world, ring_count=2, ring_radius=160, ring_spacing=80, gap_count=2, gap_size=0.5,
           escaped_lifetime=25, max_balls=600)
    pts = [(-600, -400), (600, 400), (600, -400), (-600, 400), (0, -600), (0, 600)]
    for i, (x, y) in enumerate(pts):
        _add(world, "portal", x, y, channel=i // 2)
    _add(world, "vortex", -650, 0)
    _add(world, "vortex", 650, 0, strength=-0.5)
    _add(world, "splitter", 0, -360)
    _add(world, "splitter", 0, 360)
    world.spawn_center(2)


def black_hole(world):
    _start(world, ring_count=1, ring_radius=120, gap_count=4, gap_size=0.35, gravity=0.0,
           balls_per_escape=3, max_balls=900, escaped_lifetime=0, world_walls=False,
           rotation_speed=0.05)
    _add(world, "blackhole", 520, 0, r=420)
    _add(world, "blackhole", -520, 0, r=420, strength=0.8)
    for i in range(12):
        a = i * math.tau / 12
        _add(world, "coin", math.cos(a) * 300, math.sin(a) * 300)
    world.spawn_center(4)


def factory(world):
    _start(world, ring_count=0, gravity=0.18, max_balls=700, world_width=2000, world_height=1300)
    _add(world, "cannon", -880, -520, angle=0.2, interval=25, power=12)
    _add(world, "conveyor", -600, -300, angle=0.12, w=420, speed=6)
    _add(world, "splitter", -320, -220)
    _add(world, "conveyor", -100, -40, angle=-0.15, w=420, speed=-6)
    _add(world, "paint", -380, 80, hue=0.0)
    _add(world, "conveyor", -560, 240, angle=0.18, w=380, speed=7)
    _add(world, "grow", -310, 330)
    _add(world, "booster", -150, 380, angle=-0.4, strength=1.6)
    _add(world, "water", 250, 480, w=600, h=160)
    _add(world, "wall", 250, 580, w=640, h=24)
    _add(world, "wall", -60, 480, angle=math.pi / 2, w=220)
    _add(world, "wall", 560, 480, angle=math.pi / 2, w=220)
    _add(world, "mover", 600, -100, angle=math.pi / 2, w=140, travel=200)
    _add(world, "hoop", 820, 300)
    _add(world, "antigrav", 820, -300, w=200, h=300)
    _add(world, "laser", 960, 560, angle=-math.pi / 2 - 0.4, length=500, spin=0.012)


def demolition(world):
    _start(world, ring_count=0, gravity=0.2, max_balls=500, world_width=2000, world_height=1200)
    _add(world, "wall", 250, 520, w=1100, h=30)
    # a tower of bricks, glass and TNT
    for row in range(8):
        for col in range(6):
            x = 30 + col * 70 + (35 if row % 2 else 0)
            y = 470 - row * 32
            key = "tnt" if (row, col) in ((2, 2), (5, 3), (7, 1)) else ("glass" if (row + col) % 3 == 0 else "brick")
            if key == "tnt":
                _add(world, key, x, y, w=60, h=28)
            else:
                _add(world, key, x, y, w=64, h=28)
    _add(world, "cannon", -750, 400, angle=-0.35, interval=60, power=17, ball_kind="heavy")
    _add(world, "cannon", -750, 200, angle=-0.1, interval=90, power=15, ball_kind="fire")
    _add(world, "cannon", -750, 0, angle=0.2, interval=150, power=14, ball_kind="bomb")
    for i in range(5):
        _add(world, "mine", 700 + i * 40, 490)


def chaos(world):
    _start(world, ring_count=3, ring_radius=160, ring_spacing=55, gap_count=3, gap_size=0.4,
           balls_per_escape=2, max_balls=1200, color_scheme="Random", spawn_type="rainbow")
    for i in range(8):
        a = i * math.tau / 8
        _add(world, "bumper" if i % 2 else "splitter", math.cos(a) * 520, math.sin(a) * 520)
    _add(world, "vortex", 0, 0, r=700, strength=0.15)
    for i in range(4):
        a = i * math.tau / 4 + math.pi / 4
        _add(world, "rubber", math.cos(a) * 760, math.sin(a) * 760, angle=a + math.pi / 2, w=300)
    world.spawn_center(3)


def arcade(world):
    _start(world, ring_count=0, gravity=0.2, world_width=1700, world_height=1400,
           wall_bounce=0.9, escaped_lifetime=0)
    _add(world, "whitehole", 0, -560, r=90, strength=0.2, interval=25, ball_kind="gold")
    for i, x in enumerate((-480, -240, 0, 240, 480)):
        _add(world, "crate", x, -380, count=5)
    _add(world, "saw", -330, -150, spin=0.25)
    _add(world, "saw", 330, -150, spin=-0.25)
    _add(world, "bumper", -110, -40)
    _add(world, "bumper", 110, -40)
    _add(world, "counter", 0, -160)
    _add(world, "turbo", -560, 60)
    _add(world, "turbo", 560, 60)
    _add(world, "transmuter", 0, 120, ball_kind="seeker")
    _add(world, "door", -560, 260, w=220, angle=0.4)
    _add(world, "door", 560, 260, w=220, angle=-0.4)
    _add(world, "oneway", -760, 0, angle=math.pi / 2, w=260)
    _add(world, "oneway", 760, 0, angle=-math.pi / 2, w=260)
    _add(world, "wall", -430, 420, angle=0.45, w=360)
    _add(world, "wall", 430, 420, angle=-0.45, w=360)
    _add(world, "flipper", -170, 540, angle=0.45, interval=70)
    _add(world, "flipper", 170, 540, angle=-0.45, interval=70, mirror=1)
    _add(world, "lava", 0, 670, w=500, h=60)
    _add(world, "tesla", -760, 600, range=260)
    _add(world, "tesla", 760, 600, range=260)
    _add(world, "freeze", -700, -560, r=90)
    _add(world, "teleporter", 700, -560)
    _add(world, "gswitch", 0, 360, turn=180)
    for i in range(6):
        _add(world, "coin", -250 + i * 100, 260)


def empty(world):
    _start(world, ring_count=0)


PRESETS = [
    ("Classic", "The original: one spinning ring, one gap. Every escape spawns two more.", classic),
    ("Nested Rings", "Four rings spinning in opposite directions. Can they get out?", nested),
    ("Pinball", "Bumpers, spinners and bouncers outside the ring. Sink balls in the hoop!", pinball),
    ("Portal Maze", "Portals, splitters and vortexes. Balls go everywhere.", portals),
    ("Black Holes", "No gravity. Two black holes eat everything that escapes.", black_hole),
    ("Ball Factory", "Cannons, conveyors, paint, water and a laser. A Rube Goldberg machine.", factory),
    ("Demolition", "Knock down a tower of bricks, glass and TNT with heavy, fire and bomb balls.", demolition),
    ("Chaos", "Three rings, rainbow balls, splitters, bumpers and a giant vortex.", chaos),
    ("Arcade", "Flippers, saws, crates, doors, tesla coils and a gravity switch. New in v4.1!", arcade),
    ("Empty Sandbox", "Nothing at all. Build whatever you want.", empty),
]
