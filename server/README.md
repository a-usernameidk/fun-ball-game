# Fun Ball Game server (Cloudflare Workers)

This one Worker powers everything online in the game:

- **Online levels**: players upload, browse, search, like and download levels (stored in D1).
- **Multiplayer rooms**: build together in one world with a 5-letter room code (Durable Objects + WebSockets).
- **Cloud physics**: the server runs a room's simulation so players' computers only draw it.

## Set it up (about 5 minutes)

You need a free [Cloudflare account](https://dash.cloudflare.com/sign-up) and [Node.js](https://nodejs.org).

```bash
cd server
npm install
npx wrangler login                       # opens your browser once
npx wrangler d1 create fun-ball-game     # prints a database_id
```

Paste the `database_id` it prints into `wrangler.toml`, then:

```bash
npm run db:remote                        # creates the tables
npx wrangler deploy                      # prints your URL, e.g. https://fun-ball-game.yourname.workers.dev
```

In the game, open **Settings > Online**, paste that URL and press **Test connection**.
Share the URL with your friends so they can use the same server.

Optional: set a private salt for hashing player IPs (used for rate limits and likes):

```bash
npx wrangler secret put SALT
```

## Limits (anti-abuse)

All limits are enforced on the server, so a modified game can't get around them.
Change them in the `[vars]` section of `wrangler.toml` and redeploy.

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
checks as a stand-in. That's deterministic and can't be gamed.

**Costs:** levels and multiplayer fit easily in Cloudflare's free plan. Cloud physics keeps a
Durable Object busy while it runs, so if lots of people use it you may want the
[Workers Paid plan](https://developers.cloudflare.com/workers/platform/pricing/), or lower
`CLOUD_MAX_ROOMS` / `CLOUD_SESSION_MINUTES`.

## What cloud physics supports

Rings, gravity, walls, ball collisions and escapes work exactly like the game. Most blocks
work too: walls, bouncers, ice, slime, bumpers, spinners, platforms, conveyors, spikes, saws,
doors, one-way gates, gravity wells, repulsors, black and white holes, vortexes, fans, boosts,
slow-mo, water, anti-gravity, freeze zones, portals, teleporters, splitters, cannons, lasers,
tesla coils, turbo rings, paint, grow/shrink, hoops, mines and transmuters.
Breakable blocks (glass, bricks, crates, TNT) act as solid walls in the cloud. Flippers stay
still there. Special ball powers other than rocket, balloon, phantom, hyper and rainbow are
off in the cloud.

## Develop locally

```bash
npm install
npm run db:local
npx wrangler dev          # http://127.0.0.1:8787
npm run test:sim          # tests for the cloud physics
```

Point the game at `http://127.0.0.1:8787` in Settings > Online.
