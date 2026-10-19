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


def galaxy(world):
    _start(world, ring_count=5, ring_radius=110, ring_spacing=55, gap_count=1, gap_size=0.5,
           rotation_speed=0.02, gravity=0.0, balls_per_escape=2, theme="Deep Space",
           color_scheme="Ocean", spawn_type="rainbow", world_walls=False, escaped_lifetime=15)
    _add(world, "vortex", 0, 0, r=480, strength=0.25)
    for i in range(16):
        a = i * math.tau / 16
        _add(world, "coin", math.cos(a) * 470, math.sin(a) * 470, value=2)
    for i in range(4):
        a = i * math.tau / 4 + 0.4
        _add(world, "blackhole", math.cos(a) * 760, math.sin(a) * 760, r=260, strength=0.7)
    world.spawn_center(4)


def ice_cave(world):
    _start(world, ring_count=0, gravity=0.14, theme="Glacier", color_scheme="Ocean",
           world_width=1800, world_height=1200, wall_grip=0.0, spawn_type="ice")
    _add(world, "cannon", -800, -480, angle=0.25, interval=30, power=11, ball_kind="normal")
    for i in range(5):
        _add(world, "ice", -560 + i * 230, -320 + i * 150, angle=0.3, w=260)
    _add(world, "freeze", 0, 0, r=140, duration=180)
    _add(world, "freeze", 520, 260, r=110)
    _add(world, "glass", 300, -200, angle=-0.5, w=200)
    _add(world, "glass", -300, 200, angle=0.5, w=200)
    for i in range(7):
        _add(world, "brick", -300 + i * 100, 520, w=90, h=30)
    _add(world, "cannon", 800, -480, angle=math.pi - 0.25, interval=50, power=10, ball_kind="sticky")


def lava_run(world):
    _start(world, ring_count=0, gravity=0.18, theme="Volcano", color_scheme="Fire",
           world_width=2000, world_height=1300)
    _add(world, "lava", 0, 600, w=1980, h=80)
    _add(world, "cannon", -920, -520, angle=0.1, interval=22, power=13)
    plats = [(-620, -300, 0.15), (-200, -120, -0.15), (220, 60, 0.15), (620, 240, -0.15)]
    for x, y, a in plats:
        _add(world, "wall", x, y, angle=a, w=300)
        _add(world, "saw", x + 60, y - 90, r=26, spin=0.3)
    _add(world, "mover", 0, 380, w=200, travel=500, speed=0.02)
    _add(world, "turbo", -420, -240)
    _add(world, "turbo", 420, 160)
    _add(world, "hoop", 880, 420, value=25)
    _add(world, "tesla", -880, 300, range=200)


def plinko(world):
    _start(world, ring_count=0, gravity=0.2, world_width=1300, world_height=1500, theme="Neon City",
           ball_bounce=0.5, wall_bounce=0.7)
    _add(world, "whitehole", 0, -680, r=60, strength=0.0, interval=12)
    for row in range(10):
        n = 9 if row % 2 == 0 else 8
        for i in range(n):
            x = (i - (n - 1) / 2) * 120
            _add(world, "bumper", x, -480 + row * 95, r=11, power=2.5)
    for i in range(9):
        x = (i - 4) * 130
        _add(world, "wall", x - 65, 560, angle=math.pi / 2, w=180, h=14)
        _add(world, "hoop" if i % 2 == 0 else "coin", x, 610 if i % 2 == 0 else 600,
             value=(5, 1, 20, 1, 50, 1, 20, 1, 5)[i], r=26 if i % 2 == 0 else 12)
    _add(world, "wall", 585, 560, angle=math.pi / 2, w=180, h=14)


def marble_run(world):
    _start(world, ring_count=0, gravity=0.16, world_width=1900, world_height=1400, theme="Forest")
    _add(world, "cannon", -880, -620, angle=0.0, interval=20, power=7)
    y = -520
    for i in range(6):
        left = i % 2 == 0
        _add(world, "conveyor", (-150 if left else 150), y, angle=0.12 if left else -0.12, w=1300,
             speed=5 if left else -5)
        y += 190
    _add(world, "door", 0, -430, angle=0.0, w=160)
    _add(world, "oneway", 600, -140, angle=0.0, w=200)
    _add(world, "counter", -600, 30)
    _add(world, "counter", 600, 220)
    _add(world, "splitter", 0, 120)
    _add(world, "paint", -300, 410, hue=0.85)
    _add(world, "transmuter", 300, 410, ball_kind="gold")
    _add(world, "hoop", 0, 640, value=10)


def rocket_lab(world):
    _start(world, ring_count=2, ring_radius=200, ring_spacing=120, gap_count=2, gap_size=0.6,
           gravity=0.08, spawn_type="rocket", theme="Moon", world_width=2200, world_height=1600,
           escaped_lifetime=12)
    _add(world, "cannon", -950, 650, angle=-0.9, interval=40, power=9, ball_kind="balloon")
    _add(world, "cannon", 950, 650, angle=math.pi + 0.9, interval=40, power=9, ball_kind="rocket")
    for i in range(6):
        a = i * math.tau / 6
        _add(world, "turbo", math.cos(a) * 480, math.sin(a) * 480)
    _add(world, "gswitch", 0, -560, turn=90)
    _add(world, "gswitch", 0, 560, turn=90)
    _add(world, "antigrav", -700, 0, w=260, h=500)
    _add(world, "slow", 700, 0, r=200)
    world.spawn_center(3)


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
    ("Spiral Galaxy", "Five rings in zero gravity, a giant vortex and four black holes.", galaxy),
    ("Ice Cave", "Slippery ice ramps, freeze zones and ice balls that freeze everything.", ice_cave),
    ("Lava Run", "Get balls over the platforms and saws without falling in the lava.", lava_run),
    ("Plinko", "Balls rain down through a field of pegs into scoring hoops.", plinko),
    ("Marble Run", "Zig-zagging conveyors, doors, counters and a gold transmuter.", marble_run),
    ("Rocket Lab", "Rockets, balloons, turbo rings and gravity that keeps turning.", rocket_lab),
    ("Empty Sandbox", "Nothing at all. Build whatever you want.", empty),
]
