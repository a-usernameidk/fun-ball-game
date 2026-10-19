# Fun Ball Game v4.3 – Pygame Sandbox Edition

A physics sandbox about balls escaping spinning rings. Every time a ball gets out
through a gap, more balls spawn in the middle, so it snowballs fast. On top of that
there's a full level editor, **saved worlds** with 9 themes, and **45 blocks, fields and items**, **21 ball types**,
**16 ready-made levels**, online levels, multiplayer, achievements, saving and a proper in-game UI.

![Sandbox](docs/screenshot.png)

## Running it

You need **Python 3.8+**.

- **Easiest:** double-click `run.py`. It installs Pygame the first time, then starts the game.
- **Terminal:**
  ```
  pip install -r requirements.txt   # pygame + websocket-client (for multiplayer)
  python main.py
  ```
  (`python -m fun_ball_game` works too.)

Runs on Windows, macOS and Linux. Not supported on phones or tablets.

## What's in it

**Worlds:** press PLAY to see all your worlds, Minecraft style. Create as many as you like,
each with a name, a theme and a starting level. Everything in a world is saved: blocks,
balls, settings, coins, stats and the camera. Worlds save when you leave, and every 2
minutes while you play. You can also rename, duplicate or delete them, and each one gets
a thumbnail. Use QUICK PLAY to try a level without making a world.

**Online (v4.3):**
- **Multiplayer:** open a world, go to the **Online** tab and press **Host**. You get a
  5-letter code. Friends go to **ONLINE** on the main menu, type the code and press **Join**.
  You all build in the same world, see each other's cursors and can chat (Enter or T).
- **Cloud physics:** choose "Host with cloud physics" to let the server run the simulation,
  so your PC only has to draw it. The server limits balls, blocks, CPU work, session time
  and spawn speed, so nobody can overload it with a lag machine.
- **Online levels:** share a world as a level from its Online tab. Browse, play, like and
  save other people's levels from **ONLINE** on the main menu.

**Fast spawning:** in the Balls tab, set the spray rate (up to 1,000 balls a second), the
spray brush size, and the burst size for Shift+click, B and the +N button. You can also
turn on Ball Rain with R.

**World themes:** Midnight, Deep Space, Moon, Ocean, Volcano, Forest, Glacier, Neon City and
Candy Land. Each has its own background (stars, bubbles, embers, fireflies or neon rain)
and its own starting physics, e.g. low gravity on the Moon, drag in the Ocean and heavy
gravity in the Volcano.

**Tools:** Select/Move, Spawn Balls, Grab & Throw, Eraser, Explosion, Attract, Repel

**Blocks (solid):** Stone Wall, Bouncer, Ice, Slime, Glass (shatters), Gold Brick
(breakable, gives coins), Spikes, Bumper, Spinner, Moving Platform, Conveyor, TNT
(chain reactions), Saw Blade, Flipper, One-Way Gate, Timed Door, Ball Crate

**Fields (balls pass through):** Gravity Well, Repulsor, Black Hole, Vortex, Fan Zone,
Speed Boost, Slow-Mo, Water (drag + buoyancy), Anti-Gravity, White Hole (spawns balls),
Lava (sets balls on fire), Freeze Zone

**Items:** Portal (pairs by channel), Splitter, Ball Cannon, Paint Ring, Grow Mushroom,
Shrink Ray, Coin, Mine, Laser (can rotate), Goal Hoop, Tesla Coil, Transmuter,
Gravity Flip, Turbo Ring, Teleporter, Counter

**Ball types:** Normal, Heavy, Bouncy, Ghost, Fireball, Bomb, Rainbow, Splitter,
Magnet, Tiny, Gold, Ice, Seeker, Sticky, Cluster, Rocket, Balloon, Phantom, Hyper, Glass, Eater

**Levels:** Classic (the original game), Nested Rings, Pinball, Portal Maze,
Black Holes, Ball Factory, Demolition, Chaos, Arcade, Spiral Galaxy, Ice Cave, Lava Run,
Plinko, Marble Run, Rocket Lab, Empty Sandbox

**Settings:** up to 6 nested rings, plus rotation speed, gap count and size, gravity
strength and direction, time speed, bounciness, energy boost, ball limit and limit
action, colour schemes, trails, glow, particles, screen shake and sound. Nearly every
number in the game has a slider.

**Settings screen** (SETTINGS button or `O`): FPS limit from 30 up to unlimited, or type
your own; FPS counter; fullscreen; a custom ball limit (type any number) or no limit at
all; particle cap; detail level for huge swarms; physics substeps; autosave; sound.
These are your preferences, so loading levels or save files won't change them.

Click any block with the Select tool to open it in the **Inspect** tab. There you can
change its size, rotation and its own properties (bumper power, cannon fire rate and
ball type, portal channel, black hole strength, and so on).

## Controls

| Input | Action |
|---|---|
| Left click | Use the selected tool / place the selected block |
| Left drag with a block | Draw walls at any length and angle; drag fields to set their size; drag cannons/lasers to aim |
| Right click | Delete the block under the mouse, or hold to pull balls towards the cursor |
| Middle drag / WASD / arrows | Pan |
| Mouse wheel | Zoom (Shift+wheel rotates the block you're placing) |
| Space / N | Pause / step one frame |
| Q / E | Rotate selected or ghost block |
| Delete / Ctrl+D | Delete / duplicate selected block |
| Ctrl+Z | Undo |
| Ctrl+S / Ctrl+L | Save the world (or quick save in quick play) / quick load |
| B / C | Spawn a burst of balls / clear balls |
| Shift+click / R | Burst at the mouse / ball rain |
| Enter or T | Chat (in a multiplayer room) |
| 1–9 | Pick a tile in the current toolbox tab |
| + / - | Simulation speed |
| G | Snap to grid |
| Tab | Hide the UI |
| F11 | Fullscreen |
| O | Settings |
| H | Help |

Worlds (`saves/worlds/`), save slots, settings and achievements all go in the `saves/`
folder next to the game. To back up a world, copy its `.json` file.

## Setting up the online server (only the game's owner does this, once)

Players never see any of this. The game connects to one server built into it.

1. Merge this into `main`, then click
   [![Deploy to Cloudflare](https://deploy.workers.cloudflare.com/button)](https://deploy.workers.cloudflare.com/?url=https://github.com/a-usernameidk/fun-ball-game/tree/main/server)
   and press **Deploy**. It creates the server and its database for you.
2. Copy the address it gives you, e.g. `https://fun-ball-game.yourname.workers.dev`.
3. Put it in `fun_ball_game/net.py` on the `GAME_SERVER` line, and commit. (Done: the game uses
   `https://fun-ball-game.berf.workers.dev`.)

Server limits and details are in [server/README.md](server/README.md).

## Project layout

```
main.py / run.py         entry points
fun_ball_game/
  game.py                app, menu, sandbox scene, editor tools, UI panels
  world.py               simulation: rings, ball physics, collisions, explosions
  blocks.py              every block / field / item (add new ones here)
  balls.py               ball types
  arena.py               spinning rings with gaps
  render.py              drawing the world
  ui.py                  pygame widget toolkit (buttons, sliders, tabs...)
  particles.py, audio.py effects and generated sound (no asset files)
  presets.py             the built-in levels
  worlds.py, storage.py  saved worlds and save files
  net.py                 online levels, multiplayer and cloud-physics client
server/                  Cloudflare Worker: levels API, rooms, cloud physics (JavaScript)
  achievements.py        achievements
  settings.py            all settings and colour themes
legacy/v3/               the original Tkinter version
```

### Adding a new block

Subclass `Block` (or `Field` / `Item`) in `blocks.py` and decorate it with
`@register`. It shows up in the toolbox, inspector and save files automatically:

```python
@register
class Trampoline(Block):
    key, name = "trampoline", "Trampoline"
    desc = "Extra bouncy."
    color = (0, 200, 120)
    restitution = 1.8
    props = [("restitution", "Bounciness", 0.5, 3.0, 0.1)]
```

## License

MIT, see [LICENSE](LICENSE).
