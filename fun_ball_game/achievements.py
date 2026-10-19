"""Little goals that pop up a toast when you reach them."""

ACHIEVEMENTS = [
    ("first_escape", "Breakout", "A ball escaped the ring.", lambda w: w.stats["escapes"] >= 1),
    ("escapes_100", "Jailbreak", "100 escapes.", lambda w: w.stats["escapes"] >= 100),
    ("escapes_1000", "Mass Exodus", "1,000 escapes.", lambda w: w.stats["escapes"] >= 1000),
    ("balls_100", "Crowded", "100 balls on screen at once.", lambda w: w.stats["peak"] >= 100),
    ("balls_500", "Ball Pit", "500 balls on screen at once.", lambda w: w.stats["peak"] >= 500),
    ("balls_1000", "Overflowing", "1,000 balls on screen at once.", lambda w: w.stats["peak"] >= 1000),
    ("builder", "Architect", "Place 25 blocks.", lambda w: w.stats["blocks_placed"] >= 25),
    ("coins_100", "Rich", "Collect 100 coins.", lambda w: w.stats["coins_total"] >= 100),
    ("coins_1000", "Loaded", "Collect 1,000 coins.", lambda w: w.stats["coins_total"] >= 1000),
    ("bricks_20", "Demolition Crew", "Break 20 bricks.", lambda w: w.stats["bricks"] >= 20),
    ("glass_10", "Bull in a China Shop", "Shatter 10 glass panes.", lambda w: w.stats["glass"] >= 10),
    ("boom_10", "Pyromaniac", "Cause 10 explosions.", lambda w: w.stats["explosions"] >= 10),
    ("teleport_50", "Thinking With Portals", "Teleport 50 balls.", lambda w: w.stats["teleports"] >= 50),
    ("goals_25", "Sharpshooter", "Sink 25 balls in a hoop.", lambda w: w.stats["goals"] >= 25),
    ("bumps_200", "Tilt!", "Hit bumpers 200 times.", lambda w: w.stats["bumps"] >= 200),
]


class Achievements:
    def __init__(self, unlocked=None):
        self.unlocked = set(unlocked or [])
        self.timer = 0.0

    def update(self, world, frames):
        self.timer += frames
        if self.timer < 20:
            return
        self.timer = 0.0
        for key, name, desc, cond in ACHIEVEMENTS:
            if key not in self.unlocked and cond(world):
                self.unlocked.add(key)
                world.notify(f"Achievement: {name} - {desc}", (255, 204, 0))
                world.sound("achievement", 8)
