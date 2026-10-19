"""All tweakable settings plus colour themes.

Every value here is shown somewhere in the in-game settings panel, so the
names double as the "save file" keys.
"""

import random
from dataclasses import dataclass, asdict, fields

# --------------------------------------------------------------------------
# UI theme
# --------------------------------------------------------------------------
BG = (12, 12, 20)
BG2 = (18, 18, 30)
PANEL = (20, 20, 32)
PANEL_LIGHT = (30, 30, 48)
PANEL_HOVER = (42, 42, 64)
BORDER = (48, 48, 72)
TEXT = (230, 232, 245)
TEXT_DIM = (140, 144, 170)
ACCENT = (0, 255, 204)
ACCENT2 = (255, 46, 136)
WARN = (255, 204, 0)
DANGER = (255, 60, 80)

# --------------------------------------------------------------------------
# Ball colour schemes (the old game had these too)
# --------------------------------------------------------------------------
COLOR_SCHEMES = {
    "Neon Mix": [(0, 255, 204), (255, 0, 85), (255, 204, 0), (204, 0, 255),
                 (0, 204, 255), (51, 255, 102)],
    "Fire": [(255, 0, 0), (255, 102, 0), (255, 204, 0), (255, 255, 0)],
    "Matrix": [(0, 255, 0), (0, 204, 102), (51, 255, 153), (0, 140, 50)],
    "Pastel": [(255, 153, 153), (153, 255, 153), (153, 153, 255),
               (255, 255, 153), (255, 190, 240)],
    "Ocean": [(0, 120, 255), (0, 200, 255), (100, 255, 255), (0, 255, 170)],
    "Sunset": [(255, 94, 98), (255, 153, 102), (255, 210, 120), (190, 80, 200)],
    "Mono": [(240, 240, 240), (180, 180, 190), (120, 120, 140)],
    "Random": None,
}

RING_COLORS = [(255, 51, 136), (0, 220, 255), (255, 204, 0), (150, 90, 255),
               (60, 255, 120)]

LIMIT_ACTIONS = ["Delete Oldest", "Stop Spawning", "Pause Simulation"]


def scheme_color(name):
    pal = COLOR_SCHEMES.get(name)
    if not pal:
        return (random.randint(60, 255), random.randint(60, 255),
                random.randint(60, 255))
    return random.choice(pal)


@dataclass
class Settings:
    # --- arena -----------------------------------------------------------
    ring_count: int = 1
    ring_radius: float = 220.0
    ring_spacing: float = 70.0
    rotation_speed: float = 0.035
    alternate_spin: bool = True
    gap_count: int = 1
    gap_size: float = 0.65
    ring_thickness: float = 8.0
    world_walls: bool = True
    world_width: int = 2400
    world_height: int = 1600

    # --- spawning --------------------------------------------------------
    balls_per_escape: int = 2
    max_balls: int = 600
    limit_action: str = "Delete Oldest"
    ball_radius: float = 9.0
    spawn_speed: float = 4.5
    spawn_type: str = "normal"
    escaped_lifetime: float = 20.0  # seconds a free ball lives (0 = forever)

    # --- physics ---------------------------------------------------------
    gravity: float = 0.12
    gravity_angle: float = 90.0  # degrees, 90 = straight down
    time_speed: float = 1.0
    substeps: int = 2
    wall_bounce: float = 1.0
    energy_boost: float = 1.03
    wall_grip: float = 0.05
    air_drag: float = 0.0
    ball_collisions: bool = True
    ball_bounce: float = 0.95
    max_speed: float = 30.0

    # --- visuals ---------------------------------------------------------
    color_scheme: str = "Neon Mix"
    trails: bool = True
    trail_length: int = 10
    glow: bool = True
    particles: bool = True
    screen_shake: bool = True
    show_grid: bool = True
    show_hitboxes: bool = False
    snap_to_grid: bool = False

    # --- audio -----------------------------------------------------------
    sound: bool = True
    volume: float = 0.5

    # --- display & performance ------------------------------------------
    fps_limit: int = 60          # 0 = unlimited
    show_fps: bool = True
    unlimited_balls: bool = False
    max_particles: int = 4000
    detail_threshold: int = 900  # above this many balls glow/highlights switch off
    autosave: bool = True

    def to_dict(self):
        return asdict(self)

    def load_dict(self, data, skip=()):
        names = {f.name: f for f in fields(self)}
        for k, v in data.items():
            if k in names and k not in skip:
                try:
                    setattr(self, k, type(getattr(self, k))(v))
                except (TypeError, ValueError):
                    pass

    def reset(self, keep_prefs=True):
        """Back to defaults. Player preferences survive unless keep_prefs=False."""
        prefs = self.prefs()
        self.load_dict(Settings().to_dict())
        if keep_prefs:
            self.load_dict(prefs)

    def prefs(self):
        return {k: getattr(self, k) for k in PREF_FIELDS}

    def ball_limit(self):
        return float("inf") if self.unlimited_balls else self.max_balls


# Player preferences: kept when loading levels or save files, stored in the profile.
PREF_FIELDS = ("sound", "volume", "fps_limit", "show_fps", "max_balls", "unlimited_balls",
               "limit_action", "max_particles", "detail_threshold", "autosave", "glow",
               "particles", "screen_shake", "trails", "trail_length", "substeps")

FPS_OPTIONS = [30, 45, 60, 75, 90, 120, 144, 165, 240, 360, 0]
