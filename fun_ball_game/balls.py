"""Ball objects and the different kinds of ball you can spawn."""

from collections import deque

# key -> definition. "color" None means "use the current colour scheme".
BALL_TYPES = {
    "normal": dict(name="Normal", color=None, size=1.0, density=1.0, bounce=1.0,
                   desc="A plain bouncy ball. Escapes spawn more of these."),
    "heavy": dict(name="Heavy", color=(150, 155, 175), size=1.5, density=5.0,
                  bounce=0.7, desc="Big and heavy. Shoves other balls around."),
    "bouncy": dict(name="Bouncy", color=(255, 120, 220), size=0.9,
                   density=0.8, bounce=1.25,
                   desc="Gains energy on every wall bounce."),
    "ghost": dict(name="Ghost", color=(190, 220, 255), size=1.0, density=0.5,
                  bounce=1.0, desc="Passes straight through blocks and other balls."),
    "fire": dict(name="Fireball", color=(255, 110, 20), size=1.0, density=1.0,
                 bounce=1.0, desc="Leaves flames and smashes glass, bricks and TNT."),
    "bomb": dict(name="Bomb Ball", color=(60, 60, 70), size=1.2, density=1.5,
                 bounce=0.9, desc="Explodes after 6 bounces."),
    "rainbow": dict(name="Rainbow", color=None, size=1.0, density=1.0, bounce=1.0,
                    desc="Cycles through every colour."),
    "splitter": dict(name="Splitter", color=(120, 255, 90), size=1.3, density=1.0,
                     bounce=1.0, desc="Splits into two smaller balls when it hits a wall."),
    "magnet": dict(name="Magnet", color=(255, 60, 60), size=1.2, density=2.0,
                   bounce=0.9, desc="Pulls nearby balls towards itself."),
    "tiny": dict(name="Tiny", color=None, size=0.45, density=1.0, bounce=1.0,
                 desc="Very small. Great for big swarms."),
}
BALL_ORDER = list(BALL_TYPES)


class Ball:
    __slots__ = ("x", "y", "vx", "vy", "r", "mass", "color", "kind", "layer",
                 "rewarded", "history", "alive", "age", "free_age", "bounces",
                 "cooldown", "split_depth", "bounce_mul", "ghost", "hue",
                 "grabbed")

    def __init__(self, x, y, vx, vy, r, color, kind="normal", trail=10):
        d = BALL_TYPES.get(kind, BALL_TYPES["normal"])
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.kind = kind
        self.r = r * d["size"]
        self.mass = self.r * self.r * d["density"]
        self.color = d["color"] or color
        self.bounce_mul = d["bounce"]
        self.ghost = kind == "ghost"
        self.layer = 0          # index of the innermost ring still around us
        self.rewarded = False   # already paid out the escape reward?
        self.history = deque(maxlen=max(2, trail))
        self.alive = True
        self.age = 0.0
        self.free_age = 0.0     # time spent outside every ring
        self.bounces = 0
        self.cooldown = 0.0     # used by portals/splitters so they don't loop
        self.split_depth = 0
        self.hue = 0.0
        self.grabbed = False

    def set_radius(self, r):
        d = BALL_TYPES.get(self.kind, BALL_TYPES["normal"])
        self.r = r
        self.mass = r * r * d["density"]
