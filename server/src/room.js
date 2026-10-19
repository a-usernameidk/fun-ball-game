// A multiplayer room. One Durable Object per room code.
//
// Normal rooms are a relay: messages from one player are passed on to everyone
// else, and the first player is the "host" who keeps balls in sync.
//
// Cloud rooms also run the physics here (see sim.js) and stream binary ball
// snapshots to every player, so their computers only have to draw.

import { Sim } from "./sim.js";

const TICK_MS = 33;          // ~30 physics ticks per second
const SNAPSHOT_EVERY = 3;    // send balls every 3rd tick (~10 per second)
const STATS_EVERY = 30;      // send stats about once a second
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
    spawnRate: intVar(env, "SPAWN_RATE", 500),          // balls per second per player
    maxMsgBytes: intVar(env, "MAX_MSG_KB", 1024) * 1024,
    maxBalls: intVar(env, "CLOUD_MAX_BALLS", 2000),
    maxSendBalls: intVar(env, "CLOUD_MAX_SEND_BALLS", 2000),
    maxBlocks: intVar(env, "CLOUD_MAX_BLOCKS", 300),
    maxSubsteps: intVar(env, "CLOUD_MAX_SUBSTEPS", 3),
    workBudget: intVar(env, "CLOUD_WORK_BUDGET", 60000),  // collision checks per tick
    sessionMinutes: intVar(env, "CLOUD_SESSION_MINUTES", 20),
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
    const lease = await this.limiter("acquire");
    if (!lease.ok) {
      ws.send(JSON.stringify({
        t: "cloud", on: false,
        reason: `The cloud is busy (${this.limits.maxCloudRooms} cloud rooms already running). Try again in a bit.`,
      }));
      return;
    }
    const sim = new Sim(this.limits);
    const d = data.d || {};
    sim.setTypes(d.kinds, d.types);
    sim.setSettings(d.settings);
    for (const b of (d.blocks || []).slice(0, this.limits.maxBlocks)) sim.upsertBlock(b);
    for (const it of (d.balls || []).slice(-this.limits.maxBalls)) {
      if (Array.isArray(it)) sim.spawn(it[0], it[1], it[2], it[3], it[4], it[5]);
    }
    this.sim = sim;
    this.ticks = 0;
    this.started = Date.now();
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
    if (Date.now() - this.started > this.limits.sessionMinutes * 60000) {
      this.stopCloud(`the ${this.limits.sessionMinutes} minute cloud session limit was reached`);
      return;
    }
    sim.step(TICK_MS / (1000 / 60));
    this.ticks++;
    for (const ev of sim.events.splice(0)) this.broadcast(ev);
    if (this.ticks % SNAPSHOT_EVERY === 0) this.broadcast(sim.snapshot());
    if (this.ticks % STATS_EVERY === 0) {
      this.broadcast({
        t: "cloud_stats", balls: sim.balls.length, max: sim.maxBalls(), work: sim.work,
        budget: this.limits.workBudget, overloaded: sim.overloaded, escapes: sim.stats.escapes,
        shed: sim.stats.shed, kinds: sim.kinds,
        left: Math.max(0, Math.round((this.limits.sessionMinutes * 60000 - (Date.now() - this.started)) / 1000)),
      });
    }
    if (this.ticks % (30 * 60) === 0) this.limiter("renew");
  }

  stopCloud(reason) {
    if (!this.sim) return;
    clearInterval(this.timer);
    this.timer = null;
    const state = this.cloudState();
    this.sim = null;
    this.limiter("release");
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

  async limiter(op) {
    try {
      const stub = this.env.LIMITER.get(this.env.LIMITER.idFromName("global"));
      const res = await stub.fetch(`https://limiter/${op}?room=${encodeURIComponent(this.code)}&max=${this.limits.maxCloudRooms}`);
      return await res.json();
    } catch (e) {
      return { ok: false };
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
