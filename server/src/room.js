// A multiplayer room. One Durable Object per room code.
//
// Normal rooms are a relay: messages from one player are passed on to everyone
// else, and the first player is the "host" who keeps balls in sync.
//
// Cloud rooms also run the physics here (see sim.js) and stream binary ball
// snapshots to every player, so their computers only have to draw.

import { Sim } from "./sim.js";

const TICK_MS = 33;          // ~30 physics ticks per second
const STATS_EVERY = 30;      // send stats about once a second
const BALANCE_EVERY = 150;   // re-balance cloud power about every 5 seconds

// Fewer snapshots per second when there are lots of balls (players' games smooth the gaps).
// Energy used per second: 0.25 when calm, 1.0 at full load (a full bar lasts 1h of mayhem
// or about 4h of calm building with the default 60-minute bar).
function drainPerSecond(load) {
  return 0.25 + 0.75 * Math.max(0, Math.min(1, load));
}

function snapshotEvery(balls) {
  return balls <= 3000 ? 3 : balls <= 6000 ? 4 : 5;
}
const COLORS = [[0, 255, 204], [255, 46, 136], [255, 204, 0], [120, 160, 255], [80, 255, 120],
                [255, 140, 40], [200, 120, 255], [255, 255, 255]];

function intVar(env, name, dflt) {
  const v = parseInt(env[name], 10);
  return Number.isFinite(v) && v > 0 ? v : dflt;
}

export function limitsFrom(env) {
  return {
    maxPlayers: intVar(env, "ROOM_MAX_PLAYERS", 8),
    msgRate: intVar(env, "MSG_RATE", 60),               // messages per second per player
    spawnRate: intVar(env, "SPAWN_RATE", 2000),          // balls per second per player
    maxMsgBytes: intVar(env, "MAX_MSG_KB", 1024) * 1024,
    maxBalls: intVar(env, "CLOUD_MAX_BALLS", 10000),        // a room alone on a quiet day gets this
    minBalls: intVar(env, "CLOUD_MIN_BALLS", 1000),         // a room never drops below this
    poolBalls: intVar(env, "CLOUD_POOL_BALLS", 20000),      // shared by all cloud rooms running at once
    roomKBps: intVar(env, "CLOUD_ROOM_KBPS", 6000),         // ball data a room may stream, all players combined
    dailyHours: parseFloat(env.CLOUD_DAILY_HOURS ?? "20") || 0, // cloud-room hours per day (0 = no limit)
    maxSendBalls: intVar(env, "CLOUD_MAX_SEND_BALLS", 10000),
    maxBlocks: intVar(env, "CLOUD_MAX_BLOCKS", 300),
    maxSubsteps: intVar(env, "CLOUD_MAX_SUBSTEPS", 3),
    workBudget: intVar(env, "CLOUD_WORK_BUDGET", 60000),  // collision checks per tick
    energyMinutes: intVar(env, "CLOUD_ENERGY_MINUTES", 60),  // a full energy bar = this many minutes of mayhem
    maxCloudRooms: intVar(env, "CLOUD_MAX_ROOMS", 5),
  };
}

export class Room {
  constructor(state, env) {
    this.state = state;
    this.env = env;
    this.limits = limitsFrom(env);
    this.buckets = new Map();   // per-socket rate limiting
    this.sim = null;            // set while cloud physics is running
    this.timer = null;
    this.code = null;
  }

  players() {
    return this.state.getWebSockets()
      .map((ws) => ws.deserializeAttachment())
      .filter((a) => a && !a.left);
  }

  async fetch(request) {
    if (request.headers.get("Upgrade") !== "websocket") {
      return new Response("Expected a WebSocket", { status: 426 });
    }
    const url = new URL(request.url);
    this.code = url.pathname.split("/")[2] || "ROOM";
    const live = this.players();
    if (live.length >= this.limits.maxPlayers) {
      return new Response("Room is full", { status: 403 });
    }
    const name = (url.searchParams.get("name") || "Player").replace(/[^\w \-.!?']/g, "").slice(0, 20) || "Player";
    const pair = new WebSocketPair();
    const [client, server] = Object.values(pair);
    this.state.acceptWebSocket(server);
    const id = crypto.randomUUID().slice(0, 8);
    const host = !this.sim && !live.some((p) => p.host);
    const used = new Set(live.map((p) => p.color.join()));
    const color = COLORS.find((c) => !used.has(c.join())) || COLORS[live.length % COLORS.length];
    const me = { id, name, host, color, code: this.code };
    server.serializeAttachment(me);
    server.send(JSON.stringify({
      t: "welcome", id, host, color, code: this.code, cloud: !!this.sim,
      players: [...live, me], limits: this.limits,
    }));
    this.broadcast({ t: "join", id, name, color }, server);
    return new Response(null, { status: 101, webSocket: client });
  }

  broadcast(msg, except = null, to = null) {
    const out = typeof msg === "string" || msg instanceof ArrayBuffer ? msg : JSON.stringify(msg);
    for (const ws of this.state.getWebSockets()) {
      if (ws === except) continue;
      if (to) {
        const a = ws.deserializeAttachment();
        if (!a || a.id !== to) continue;
      }
      try { ws.send(out); } catch (e) { /* socket already closing */ }
    }
  }

  allow(ws, cost, kind) {
    // token bucket: refills `rate` per second, holds up to 2 seconds' worth
    const rate = kind === "spawn" ? this.limits.spawnRate : this.limits.msgRate;
    const key = ws.deserializeAttachment()?.id + kind;
    const now = Date.now();
    let b = this.buckets.get(key);
    if (!b) this.buckets.set(key, (b = { tokens: rate * 2, last: now }));
    b.tokens = Math.min(rate * 2, b.tokens + ((now - b.last) / 1000) * rate);
    b.last = now;
    if (b.tokens < cost) return false;
    b.tokens -= cost;
    return true;
  }

  async webSocketMessage(ws, raw) {
    if (typeof raw !== "string" || raw.length > this.limits.maxMsgBytes) return;
    if (!this.allow(ws, 1, "msg")) return;
    let data;
    try { data = JSON.parse(raw); } catch (e) { return; }
    if (!data || typeof data.t !== "string") return;
    const me = ws.deserializeAttachment();
    if (!me) return;
    this.code = this.code || me.code;

    switch (data.t) {
      case "ping":
        ws.send(JSON.stringify({ t: "pong", ts: data.ts }));
        return;
      case "cloud_start":
        await this.startCloud(ws, me, data);
        return;
      case "cloud_stop":
        if (this.sim) this.stopCloud("stopped by " + me.name);
        return;
      case "chat":
        data.m = String(data.m || "").slice(0, 200);
        break;
    }

    if (this.sim) {
      // the cloud is the host: keep its copy of the world up to date
      const sim = this.sim;
      switch (data.t) {
        case "blocks":
          for (const d of (data.up || []).slice(0, 500)) sim.upsertBlock(d);
          for (const uid of (data.del || []).slice(0, 500)) sim.removeBlock(uid);
          break;
        case "settings":
          sim.setSettings(data.d);
          break;
        case "spawn": {
          const list = Array.isArray(data.b) ? data.b : [];
          if (!this.allow(ws, list.length, "spawn")) {
            ws.send(JSON.stringify({ t: "warn", m: "Slow down! Too many balls per second." }));
            return;
          }
          for (const it of list) {
            if (!Array.isArray(it)) continue;
            sim.spawn(it[0], it[1], it[2], it[3], it[4], it[5]);
          }
          return; // balls arrive through snapshots
        }
        case "boom":
          sim.explode(+data.x || 0, +data.y || 0, +data.r || 170, +data.p || 15);
          return; // the sim announces explosions itself
        case "clear":
          sim.clearBalls();
          break;
        case "need_state":
          ws.send(JSON.stringify({ t: "state", d: this.cloudState() }));
          return;
        case "balls":
          return; // in cloud rooms only the server sends balls
      }
    }

    data.from = me.id;
    const to = typeof data.to === "string" ? data.to : null;
    this.broadcast(JSON.stringify(data), ws, to);
  }

  cloudState() {
    const s = this.sim;
    return {
      settings: { ...s.s, palette: s.palette },
      blocks: [...s.blocks.values()].map((b) => ({
        ...b.p, uid: b.uid, key: b.key, x: b.key === "mover" ? b.ox : b.x, y: b.key === "mover" ? b.oy : b.y,
        angle: b.rest, w: b.w, h: b.h, r: b.r,
      })),
    };
  }

  async startCloud(ws, me, data) {
    if (this.sim) {
      ws.send(JSON.stringify({ t: "cloud", on: true }));
      return;
    }
    this.lastBalance = 0;
    const lease = await this.limiter("acquire", 0);
    if (!lease.ok) {
      ws.send(JSON.stringify({
        t: "cloud", on: false,
        reason: lease.reason === "tired"
          ? "The cloud is resting until tomorrow (daily limit reached). Your PC is running the physics."
          : `The cloud is busy (${this.limits.maxCloudRooms} cloud rooms already running). Try again in a bit.`,
      }));
      return;
    }
    const sim = new Sim({ ...this.limits });
    const d = data.d || {};
    sim.setTypes(d.kinds, d.types);
    sim.setSettings(d.settings);
    for (const b of (d.blocks || []).slice(0, this.limits.maxBlocks)) sim.upsertBlock(b);
    for (const it of (d.balls || []).slice(-this.limits.maxBalls)) {
      if (Array.isArray(it)) sim.spawn(it[0], it[1], it[2], it[3], it[4], it[5]);
    }
    this.sim = sim;
    this.ticks = 0;
    this.load = undefined;
    this.energy = this.maxEnergy = this.limits.energyMinutes * 60;  // in "seconds at full load"
    this.drainMult = 1;
    this.started = Date.now();
    this.lastBalance = this.started;
    await this.balance("renew");
    if (!this.sim) return;
    // everyone stops simulating locally; the cloud is the host now
    for (const s of this.state.getWebSockets()) {
      const a = s.deserializeAttachment();
      if (a && a.host) s.serializeAttachment({ ...a, host: false });
    }
    this.broadcast({ t: "cloud", on: true, by: me.name, limits: this.limits });
    this.timer = setInterval(() => this.tick(), TICK_MS);
  }

  tick() {
    const sim = this.sim;
    if (!sim) return;
    if (!this.state.getWebSockets().length) { this.stopCloud("everyone left"); return; }
    if (this.energy <= 0) {
      this.stopCloud("this session's cloud energy ran out (start a new one any time)");
      return;
    }
    sim.step(TICK_MS / (1000 / 60));
    this.ticks++;
    // Energy drains with what the room is doing *right now*: going crazy burns it about 4x
    // faster than calm building, so you can go wild for a bit and then make something chill
    // without wasting the server. More cloud rooms or a busy day make it drain faster.
    const load = Math.min(1, sim.work / this.limits.workBudget);
    this.energy -= drainPerSecond(load) * this.drainMult * (TICK_MS / 1000);
    // smoothed load for display (roughly the last 10 seconds)
    this.load = this.load === undefined ? load : this.load + (load - this.load) * 0.003;
    for (const ev of sim.events.splice(0)) this.broadcast(ev);
    if (this.ticks % snapshotEvery(sim.balls.length) === 0) this.broadcast(sim.snapshot());
    if (this.ticks % STATS_EVERY === 0) {
      this.broadcast({
        t: "cloud_stats", balls: sim.balls.length, max: sim.maxBalls(), cap: sim.limits.maxBalls,
        top: this.limits.maxBalls, power: this.power, why: this.why, rooms: this.rooms,
        load: Math.round(100 * (this.load || 0)),
        energy: Math.max(0, Math.round((100 * this.energy) / this.maxEnergy)),
        calm: Math.round(Math.max(0, this.energy) / (drainPerSecond(0) * this.drainMult)),
        work: sim.work, budget: this.limits.workBudget, overloaded: sim.overloaded,
        escapes: sim.stats.escapes, shed: sim.stats.shed, kinds: sim.kinds,
        left: Math.round(Math.max(0, this.energy) / (drainPerSecond(this.load || 0) * this.drainMult)),
      });
    }
    if (this.ticks % BALANCE_EVERY === 0) this.balance("renew");
  }

  // Work out this room's share of the cloud: how many balls it may simulate and how long
  // its session lasts, based on how many cloud rooms are running, how many players are in
  // this room and how much cloud time has been used today.
  async balance(op) {
    const now = Date.now();
    const add = this.lastBalance ? (now - this.lastBalance) / 1000 : 0;
    this.lastBalance = now;
    const lease = await this.limiter(op, add);
    const sim = this.sim;
    if (!sim) return lease;
    if (!lease.ok) {
      if (lease.reason === "tired" || op === "renew") this.stopCloud("the cloud ran out of power for today");
      return lease;
    }
    const L = this.limits;
    const rooms = Math.max(1, lease.active);
    const players = Math.max(1, this.players().length);
    const day = lease.budget ? lease.used / lease.budget : 0;
    if (lease.budget && day >= 1) { this.stopCloud("the cloud is resting until tomorrow (daily limit reached)"); return lease; }
    // a busy day turns everyone down gently: full power until half the daily time is used
    const dayFactor = day < 0.5 ? 1 : Math.max(0.25, 1 - (day - 0.5) * 1.5);
    let cap = Math.min(L.maxBalls, L.poolBalls / rooms) * dayFactor;
    // every player has to be sent every ball, so more players means fewer balls each
    const hz = 30 / snapshotEvery(cap);
    cap = Math.min(cap, (L.roomKBps * 1024) / (players * 16 * hz));
    cap = Math.round(Math.max(L.minBalls, Math.min(L.maxBalls, cap)));
    sim.limits = { ...sim.limits, maxBalls: cap, maxSendBalls: Math.min(cap, L.maxSendBalls) };
    this.cap = cap;
    this.power = Math.round((100 * cap) / L.maxBalls);
    this.rooms = rooms;
    const why = [];
    if (rooms === 1) why.push("you're the only cloud room right now");
    else why.push(`${rooms} cloud rooms are sharing the power`);
    if (players > 1) why.push(`split between ${players} players`);
    if (dayFactor < 1) why.push("it's been a busy day, so power is turned down");
    this.why = why.join(", ");
    // sharing the cloud with other rooms, or a busy day, makes energy drain faster
    this.drainMult = (rooms <= 1 ? 1 : rooms <= 3 ? 2 : 3) * (dayFactor < 1 ? 2 : 1);
    return lease;
  }

  stopCloud(reason) {
    if (!this.sim) return;
    clearInterval(this.timer);
    this.timer = null;
    const state = this.cloudState();
    this.sim = null;
    this.limiter("release", this.lastBalance ? (Date.now() - this.lastBalance) / 1000 : 0);
    // hand hosting back to the first player
    const sockets = this.state.getWebSockets();
    let hostId = null;
    for (const [i, s] of sockets.entries()) {
      const a = s.deserializeAttachment();
      if (!a) continue;
      if (i === 0) hostId = a.id;
      s.serializeAttachment({ ...a, host: i === 0 });
    }
    this.broadcast({ t: "cloud", on: false, reason, state });
    if (hostId) this.broadcast({ t: "host", id: hostId });
  }

  async limiter(op, add = 0) {
    try {
      const stub = this.env.LIMITER.get(this.env.LIMITER.idFromName("global"));
      const q = new URLSearchParams({
        room: this.code, max: this.limits.maxCloudRooms, add: add.toFixed(1),
        budget: Math.round(this.limits.dailyHours * 3600),
      });
      const res = await stub.fetch(`https://limiter/${op}?${q}`);
      return await res.json();
    } catch (e) {
      return { ok: false, reason: "error" };
    }
  }

  async webSocketClose(ws, code) {
    this.leave(ws);
    try { ws.close(1000, "bye"); } catch (e) { /* already closed */ }
  }

  async webSocketError(ws) {
    this.leave(ws);
  }

  leave(ws) {
    const me = ws.deserializeAttachment();
    if (!me || me.left) return;
    ws.serializeAttachment({ ...me, left: true });
    this.broadcast({ t: "leave", id: me.id }, ws);
    const rest = this.state.getWebSockets().filter((o) => o !== ws && !o.deserializeAttachment()?.left);
    if (!rest.length) {
      if (this.sim) this.stopCloud("everyone left");
      return;
    }
    if (me.host && !this.sim) {
      const next = rest[0];
      next.serializeAttachment({ ...next.deserializeAttachment(), host: true });
      this.broadcast({ t: "host", id: next.deserializeAttachment().id });
    }
  }
}
