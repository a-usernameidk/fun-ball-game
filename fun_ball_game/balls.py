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
    "gold": dict(name="Gold", color=(255, 200, 40), size=1.0, density=2.5, bounce=0.95,
                 desc="Earns a coin every 5 bounces."),
    "ice": dict(name="Ice", color=(170, 230, 255), size=1.0, density=1.2, bounce=0.9,
                desc="Freezes any ball it bumps into for 2 seconds."),
    "seeker": dict(name="Seeker", color=(255, 90, 255), size=0.9, density=1.0, bounce=1.0,
                   desc="Homes in on the nearest coin, hoop, brick or crate."),
    "sticky": dict(name="Sticky", color=(130, 210, 60), size=1.0, density=1.0, bounce=0.5,
                   desc="Sticks to whatever it hits for a second, then drops off."),
    "cluster": dict(name="Cluster", color=(255, 170, 0), size=1.4, density=1.5, bounce=0.9,
                    desc="Bursts into 6 tiny balls on its 3rd bounce."),
    "rocket": dict(name="Rocket", color=(255, 80, 40), size=0.9, density=1.0, bounce=0.9,
                   desc="Keeps accelerating in whatever direction it's going."),
    "balloon": dict(name="Balloon", color=(255, 120, 160), size=1.3, density=0.3, bounce=0.8,
                    desc="Floats upwards against gravity. Pops on its 3rd bounce."),
    "phantom": dict(name="Phantom", color=(150, 120, 255), size=1.0, density=1.0, bounce=1.0,
                    desc="Flickers between solid and ghost every second."),
    "hyper": dict(name="Hyper", color=(0, 255, 120), size=0.9, density=1.0, bounce=1.0,
                  desc="Randomly changes direction every half second."),
    "glass": dict(name="Glass", color=(200, 240, 255), size=1.0, density=1.0, bounce=1.0,
                  desc="Shatters the first time it hits anything hard."),
    "eater": dict(name="Eater", color=(40, 40, 40), size=1.2, density=3.0, bounce=0.8,
                  desc="Swallows smaller balls it touches and grows bigger."),
}
BALL_ORDER = list(BALL_TYPES)


class Ball:
    __slots__ = ("x", "y", "vx", "vy", "r", "mass", "color", "kind", "layer",
                 "rewarded", "history", "alive", "age", "free_age", "bounces",
                 "cooldown", "split_depth", "bounce_mul", "ghost", "hue",
                 "grabbed", "frozen", "prev_bounces", "nid")

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
        self.frozen = 0.0       # frames left frozen in place (freeze zone, ice ball...)
        self.prev_bounces = 0
        self.nid = 0            # network id in multiplayer / cloud rooms

    def set_radius(self, r):
        d = BALL_TYPES.get(self.kind, BALL_TYPES["normal"])
        self.r = r
        self.mass = r * r * d["density"]

    def set_kind(self, kind, color):
        """Turn this ball into another type, keeping its base size and speed."""
        old = BALL_TYPES.get(self.kind, BALL_TYPES["normal"])
        d = BALL_TYPES.get(kind, BALL_TYPES["normal"])
        base = self.r / old["size"]
        self.kind = kind
        self.r = base * d["size"]
        self.mass = self.r * self.r * d["density"]
        self.color = d["color"] or (self.color if old["color"] is None else color)
        self.bounce_mul = d["bounce"]
        self.ghost = kind == "ghost"
        self.bounces = self.prev_bounces = 0
