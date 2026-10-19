# Fun Ball Game server (Cloudflare Workers)

This one Worker powers everything online in the game:

- **Online levels**: players upload, browse, search, like and download levels.
- **Multiplayer rooms**: build together in one world with a 5-letter room code.
- **Cloud physics**: the server runs a room's simulation so players' computers only draw it.

## Set it up (once, by the game's owner)

[![Deploy to Cloudflare](https://deploy.workers.cloudflare.com/button)](https://deploy.workers.cloudflare.com/?url=https://github.com/a-usernameidk/fun-ball-game/tree/main/server)

1. Click the button, log in to Cloudflare and press **Deploy**. Cloudflare copies this folder
   into your GitHub, creates the database and puts the server online. The server creates its
   own tables on first use, so there's nothing else to set up.
2. Copy the address it gives you, e.g. `https://fun-ball-game.yourname.workers.dev`.
3. Put that address in `fun_ball_game/net.py` on the line `GAME_SERVER = ""`. Every copy of
   the game then uses your server automatically. Players just host and share room codes.

**Updating later:** your copy is connected to Cloudflare, so pushing a change to it
redeploys by itself. To change a limit, edit `wrangler.toml` on GitHub's website and commit.

## Limits (anti-abuse)

All limits are enforced on the server, so a modified game can't get around them.
Change them in the `[vars]` section of `wrangler.toml`.

| Setting | Default | What it stops |
|---|---|---|
| `CLOUD_MAX_BALLS` | 2000 | huge ball counts in cloud rooms |
| `CLOUD_MAX_BLOCKS` | 300 | giant block machines in cloud rooms |
| `CLOUD_WORK_BUDGET` | 60000 | "lag machines": when a tick needs more collision checks than this, the room deletes its oldest balls and refuses new ones until it recovers |
| `CLOUD_MAX_SUBSTEPS` | 3 | cranking physics accuracy to burn CPU |
| `CLOUD_SESSION_MINUTES` | 20 | cloud rooms running forever (players can restart them) |
| `CLOUD_MAX_ROOMS` | 5 | too many cloud rooms at once, server-wide |
| `SPAWN_RATE` | 500 | spawning more balls than this per second per player |
| `MSG_RATE` | 60 | message spam (per player, per second) |
| `ROOM_MAX_PLAYERS` | 8 | crowded rooms |
| `UPLOADS_PER_HOUR` | 10 | level upload spam (per player) |
| `MAX_LEVEL_KB` / `MAX_LEVEL_BLOCKS` | 400 / 2000 | huge uploads |

Workers can't measure CPU time from inside a request, so the cloud sim counts collision
checks as a stand-in. That's deterministic and can't be gamed. Optionally, add a secret
called `SALT` in the Worker's settings on the Cloudflare dashboard. It's used when hashing
player IPs for rate limits and likes.

**Costs:** levels and multiplayer fit easily in Cloudflare's free plan. Cloud physics keeps a
Durable Object busy while it runs, so if lots of people use it you may want the Workers Paid
plan, or lower `CLOUD_MAX_ROOMS` / `CLOUD_SESSION_MINUTES`.

## What cloud physics supports

Rings, gravity, walls, ball collisions and escapes work exactly like the game. Most blocks
work too: walls, bouncers, ice, slime, bumpers, spinners, platforms, conveyors, spikes, saws,
doors, one-way gates, gravity wells, repulsors, black and white holes, vortexes, fans, boosts,
slow-mo, water, anti-gravity, freeze zones, portals, teleporters, splitters, cannons, lasers,
tesla coils, turbo rings, paint, grow/shrink, hoops, mines and transmuters.
Breakable blocks (glass, bricks, crates, TNT) act as solid walls in the cloud. Flippers stay
still there. Special ball powers other than rocket, balloon, phantom, hyper and rainbow are
off in the cloud.

## For developers

```bash
npm install
npx wrangler dev     # local server at http://127.0.0.1:8787
npm test             # cloud physics tests
```
