// Cloud physics: a JavaScript port of the game's core simulation (fun_ball_game/world.py).
//
// It runs inside a Room Durable Object so players can offload big simulations to
// Cloudflare. Everything here is capped by `limits` so nobody can turn it into a
// lag machine: ball count, block count, physics substeps and a per-tick "work"
// budget (collision checks). When a tick goes over budget the sim sheds the oldest
// balls and refuses new spawns until it recovers.
//
// Workers freeze the clock during execution, so we can't measure CPU time; counting
// collision checks is a deterministic stand-in for it.

const TAU = Math.PI * 2;
const BLOCK_CELL = 128;
const BLOCK_PAD = 48;

const mod = (a, n) => ((a % n) + n) % n;
const clamp = (v, lo, hi) => (v < lo ? lo : v > hi ? hi : v);
const num = (v, d) => (typeof v === "number" && Number.isFinite(v) ? v : d);

// Settings the cloud understands, with [default, min, max]. Booleans: [default].
const SETTINGS = {
  ring_count: [1, 0, 6], ring_radius: [220, 30, 2000], ring_spacing: [70, 10, 500],
  rotation_speed: [0.035, -0.5, 0.5], alternate_spin: [true], gap_count: [1, 0, 12],
  gap_size: [0.65, 0, 6.3], ring_thickness: [8, 1, 60], world_walls: [true],
  world_width: [2400, 200, 12000], world_height: [1600, 200, 12000],
  balls_per_escape: [2, 0, 10], max_balls: [600, 1, 100000], escaped_lifetime: [20, 0, 600],
  ball_radius: [9, 1, 40], spawn_speed: [4.5, 0, 40], gravity: [0.12, -2, 2],
  gravity_angle: [90, -720, 720], time_speed: [1, 0.05, 4], substeps: [2, 1, 4],
  wall_bounce: [1, 0, 2], energy_boost: [1.03, 0.5, 1.2], wall_grip: [0.05, 0, 1],
  air_drag: [0, 0, 0.5], ball_collisions: [true], ball_bounce: [0.95, 0, 1.5],
  max_speed: [30, 1, 80],
};

function hsv(h, s, v) {
  const i = Math.floor(h * 6), f = h * 6 - i;
  const p = v * (1 - s), q = v * (1 - f * s), t = v * (1 - (1 - f) * s);
  const [r, g, b] = [[v, t, p], [q, v, p], [p, v, t], [p, q, v], [t, p, v], [v, p, q]][mod(i, 6)];
  return [Math.round(r * 255), Math.round(g * 255), Math.round(b * 255)];
}

function rot(x, y, a) {
  const c = Math.cos(a), s = Math.sin(a);
  return [x * c - y * s, x * s + y * c];
}

function pointSegDist(px, py, ax, ay, bx, by) {
  const abx = bx - ax, aby = by - ay, l2 = abx * abx + aby * aby;
  if (l2 === 0) return Math.hypot(px - ax, py - ay);
  const t = clamp(((px - ax) * abx + (py - ay) * aby) / l2, 0, 1);
  return Math.hypot(px - (ax + abx * t), py - (ay + aby * t));
}

export class Sim {
  constructor(limits) {
    this.limits = limits;
    this.s = {};
    for (const [k, v] of Object.entries(SETTINGS)) this.s[k] = v[0];
    this.s.spawn_type = "normal";
    this.s.limit_action = "Delete Oldest";
    this.balls = [];
    this.blocks = new Map();
    this.rings = [];
    this.nextId = 1;
    this.time = 0;
    this.kinds = ["normal"];
    this.types = { normal: { size: 1, density: 1, bounce: 1, color: null } };
    this.palette = [[0, 255, 204], [255, 0, 85], [255, 204, 0]];
    this.stats = { escapes: 0, spawned: 0, removed: 0, shed: 0 };
    this.work = 0;
    this.overloaded = false;
    this.events = [];      // things clients should hear about (explosions, removed blocks)
    this.buildRings();
  }

  // ------------------------------------------------------------------ setup
  setTypes(kinds, types) {
    if (!Array.isArray(kinds) || typeof types !== "object" || !types) return;
    const ks = kinds.filter((k) => typeof k === "string" && types[k]).slice(0, 64);
    if (!ks.length) return;
    this.kinds = ks;
    this.types = {};
    for (const k of ks) {
      const t = types[k];
      this.types[k] = {
        size: clamp(num(t.size, 1), 0.1, 5), density: clamp(num(t.density, 1), 0.01, 50),
        bounce: clamp(num(t.bounce, 1), 0, 3),
        color: Array.isArray(t.color) ? t.color.slice(0, 3).map((c) => clamp(c | 0, 0, 255)) : null,
      };
    }
  }

  setSettings(d) {
    if (!d || typeof d !== "object") return;
    for (const [k, spec] of Object.entries(SETTINGS)) {
      if (!(k in d)) continue;
      if (spec.length === 1) this.s[k] = !!d[k];
      else this.s[k] = clamp(num(d[k], this.s[k]), spec[1], spec[2]);
    }
    for (const k of ["ring_count", "gap_count", "balls_per_escape", "max_balls", "substeps"]) {
      this.s[k] = Math.round(this.s[k]);
    }
    if (typeof d.spawn_type === "string" && this.types[d.spawn_type]) this.s.spawn_type = d.spawn_type;
    if (typeof d.limit_action === "string") this.s.limit_action = d.limit_action;
    if (Array.isArray(d.palette) && d.palette.length) {
      this.palette = d.palette.slice(0, 16).map((c) => (Array.isArray(c) ? c.slice(0, 3).map((x) => clamp(x | 0, 0, 255)) : [255, 255, 255]));
    }
    this.buildRings();
  }

  buildRings() {
    const s = this.s, old = this.rings.map((r) => r.angle);
    this.rings = [];
    for (let i = 0; i < s.ring_count; i++) {
      const dir = s.alternate_spin && i % 2 ? -1 : 1;
      this.rings.push({
        radius: s.ring_radius + i * s.ring_spacing,
        speed: s.rotation_speed * dir * (1 + 0.15 * i),
        gaps: s.gap_count, gapSize: s.gap_size, thickness: s.ring_thickness,
        angle: old[i] ?? i * 0.9,
      });
    }
    for (const b of this.balls) b.layer = this.layerFor(Math.hypot(b.x, b.y));
  }

  layerFor(d) {
    let n = 0;
    for (const r of this.rings) if (r.radius < d) n++;
    return n;
  }

  maxBalls() {
    return Math.min(this.s.max_balls, this.limits.maxBalls);
  }

  // ------------------------------------------------------------------ blocks
  upsertBlock(d) {
    if (!d || typeof d !== "object" || typeof d.uid !== "string" || typeof d.key !== "string") return;
    if (!this.blocks.has(d.uid) && this.blocks.size >= this.limits.maxBlocks) return;
    const old = this.blocks.get(d.uid) || {};
    const ph = d.phys || {};
    const b = {
      ...old,
      uid: d.uid.slice(0, 32), key: d.key.slice(0, 32),
      x: num(d.x, 0), y: num(d.y, 0), angle: num(d.angle, 0),
      w: clamp(num(d.w, 100), 1, 5000), h: clamp(num(d.h, 20), 1, 5000), r: clamp(num(d.r, 20), 1, 3000),
      shape: ph.shape === "circle" ? "circle" : "rect",
      solid: !!ph.solid, restitution: clamp(num(ph.restitution, 0.85), 0, 3),
      friction: clamp(num(ph.friction, 0), 0, 1), pad: clamp(num(ph.touch_pad, 0), 0, 2),
      p: {},
    };
    // copy the simple numeric/string properties (strength, spin, channel, ...)
    for (const [k, v] of Object.entries(d)) {
      if (k in b || k === "phys") continue;
      if (typeof v === "number" && Number.isFinite(v)) b.p[k] = v;
      else if (typeof v === "string" && v.length < 40) b.p[k] = v;
    }
    if (b.key === "mover") { b.ox = b.x; b.oy = b.y; b.phase = old.phase || 0; }
    b.t = old.t || 0;
    b.timer = old.timer || 0;
    b.rest = b.angle;
    this.blocks.set(b.uid, b);
  }

  removeBlock(uid) {
    this.blocks.delete(uid);
  }

  // ------------------------------------------------------------------ balls
  spawn(x, y, vx, vy, kind, color, radius) {
    if (this.balls.length >= this.maxBalls()) {
      if (this.s.limit_action !== "Delete Oldest") return null;
    }
    if (this.overloaded || this.balls.length >= this.limits.maxBalls) return null;
    const t = this.types[kind] ? kind : "normal";
    const def = this.types[t] || { size: 1, density: 1, bounce: 1 };
    const r = clamp(num(radius, this.s.ball_radius), 1, 40) * def.size;
    const c = def.color || (Array.isArray(color) ? color.slice(0, 3).map((v) => clamp(v | 0, 0, 255))
      : this.palette[(Math.random() * this.palette.length) | 0]);
    const d = Math.hypot(x, y);
    const b = {
      id: this.nextId, x: num(x, 0), y: num(y, 0), vx: clamp(num(vx, 0), -80, 80), vy: clamp(num(vy, 0), -80, 80),
      r, mass: r * r * def.density, bounce: def.bounce, kind: t, color: c,
      ghost: t === "ghost", layer: this.layerFor(d), rewarded: false, alive: true,
      cooldown: 0, frozen: 0, bounces: 0, age: 0, freeAge: 0,
    };
    if (b.layer >= this.rings.length && this.rings.length) b.rewarded = true;
    this.nextId = this.nextId >= 65535 ? 1 : this.nextId + 1;
    this.balls.push(b);
    this.stats.spawned++;
    return b;
  }

  spawnCenter(n) {
    for (let i = 0; i < n; i++) {
      const a = Math.random() * TAU, sp = this.s.spawn_speed * (0.66 + Math.random() * 0.67);
      if (!this.spawn(Math.random() * 6 - 3, Math.random() * 6 - 3, Math.cos(a) * sp, Math.sin(a) * sp, this.s.spawn_type)) break;
    }
  }

  clearBalls() {
    this.balls = [];
  }

  kill(b) {
    if (b.alive) {
      b.alive = false;
      this.stats.removed++;
    }
  }

  explode(x, y, radius, power) {
    radius = clamp(radius, 1, 600);
    power = clamp(power, 0, 40);
    for (const b of this.balls) {
      let dx = b.x - x, dy = b.y - y, d = Math.hypot(dx, dy);
      if (d < radius) {
        if (d < 1e-3) { dx = 0; dy = -1; d = 1; }
        const k = (1 - d / radius) * power;
        b.vx += (dx / d) * k;
        b.vy += (dy / d) * k;
      }
    }
    this.events.push({ t: "boom", x, y, r: radius, p: power });
  }

  gravity() {
    const a = (this.s.gravity_angle * Math.PI) / 180;
    return [Math.cos(a) * this.s.gravity, Math.sin(a) * this.s.gravity];
  }

  // ------------------------------------------------------------------ stepping
  step(frames) {
    const s = this.s;
    this.work = 0;
    const total = Math.min(frames * s.time_speed, 8);
    const steps = clamp(Math.max(s.substeps, Math.ceil(total / 1.2)), 1, this.limits.maxSubsteps);
    const dt = total / steps;
    const grid = this.blockGrid();
    for (let i = 0; i < steps; i++) this.substep(dt, grid, i === steps - 1 || this.balls.length <= 500);
    this.perFrame(total);
    this.time += total;
    // load shedding
    this.overloaded = this.work > this.limits.workBudget;
    if (this.overloaded && this.balls.length) {
      const n = Math.max(1, Math.floor(this.balls.length * 0.1));
      this.balls.splice(0, n);
      this.stats.shed += n;
    }
  }

  blockGrid() {
    const grid = new Map();
    for (const b of this.blocks.values()) {
      const e = this.extent(b);
      const cx = b.key === "mover" ? b.ox : b.x, cy = b.key === "mover" ? b.oy : b.y;
      const x0 = Math.floor((cx - e - BLOCK_PAD) / BLOCK_CELL), x1 = Math.floor((cx + e + BLOCK_PAD) / BLOCK_CELL);
      const y0 = Math.floor((cy - e - BLOCK_PAD) / BLOCK_CELL), y1 = Math.floor((cy + e + BLOCK_PAD) / BLOCK_CELL);
      if ((x1 - x0 + 1) * (y1 - y0 + 1) > 4000) continue; // absurdly huge block: skip
      for (let ix = x0; ix <= x1; ix++) {
        for (let iy = y0; iy <= y1; iy++) {
          const k = ix * 100003 + iy;
          let cell = grid.get(k);
          if (!cell) grid.set(k, (cell = []));
          cell.push(b);
        }
      }
    }
    return grid;
  }

  extent(b) {
    let e = b.shape === "circle" ? b.r : Math.hypot(b.w, b.h) / 2;
    if (b.key === "mover") e += num(b.p.travel, 150);
    if (b.key === "flipper") e = b.w;
    return e;
  }

  substep(dt, grid, collide) {
    const s = this.s;
    for (const r of this.rings) r.angle = mod(r.angle + r.speed * dt, TAU);
    for (const blk of this.blocks.values()) this.updateBlock(blk, dt);

    const [gx, gy] = this.gravity();
    const drag = Math.max(0, 1 - s.air_drag * dt);
    const maxv = s.max_speed, n = this.rings.length;
    const hw = s.world_width / 2, hh = s.world_height / 2;
    for (const b of this.balls) {
      if (!b.alive) continue;
      if (b.frozen > 0) { b.frozen -= dt; if (b.cooldown > 0) b.cooldown -= dt; continue; }
      b.vx = (b.vx + gx * dt) * drag;
      b.vy = (b.vy + gy * dt) * drag;
      const sp2 = b.vx * b.vx + b.vy * b.vy;
      if (sp2 > maxv * maxv) { const k = maxv / Math.sqrt(sp2); b.vx *= k; b.vy *= k; }
      b.x += b.vx * dt;
      b.y += b.vy * dt;
      if (b.cooldown > 0) b.cooldown -= dt;
      if (n) this.ringCollide(b, n);
      if (s.world_walls) {
        const e = s.wall_bounce * b.bounce;
        if (b.x - b.r < -hw) { b.x = -hw + b.r; b.vx = Math.abs(b.vx) * e; b.bounces++; }
        else if (b.x + b.r > hw) { b.x = hw - b.r; b.vx = -Math.abs(b.vx) * e; b.bounces++; }
        if (b.y - b.r < -hh) { b.y = -hh + b.r; b.vy = Math.abs(b.vy) * e; b.bounces++; }
        else if (b.y + b.r > hh) { b.y = hh - b.r; b.vy = -Math.abs(b.vy) * e; b.bounces++; }
      } else if (Math.abs(b.x) > hw + 300 || Math.abs(b.y) > hh + 300) {
        b.alive = false;
      }
    }
    this.work += this.balls.length;

    if (grid.size) {
      for (const b of this.balls) {
        if (!b.alive) continue;
        const cell = grid.get(Math.floor(b.x / BLOCK_CELL) * 100003 + Math.floor(b.y / BLOCK_CELL));
        if (!cell) continue;
        this.work += cell.length;
        for (const blk of cell) {
          if (!this.blocks.has(blk.uid)) continue;
          if (blk.solid) { if (!b.ghost) this.collideBlock(blk, b); }
          else if (this.overlaps(blk, b)) this.touch(blk, b, dt);
          if (!b.alive) break;
        }
      }
    }
    if (s.ball_collisions && collide) this.ballCollisions();
    if (this.balls.some((b) => !b.alive)) this.balls = this.balls.filter((b) => b.alive);
  }

  // --- rings (same logic as World._ring_collide in Python)
  inGap(ring, theta) {
    if (ring.gaps <= 0) return false;
    const step = TAU / ring.gaps;
    for (let i = 0; i < ring.gaps; i++) {
      const start = mod(ring.angle + i * step, TAU);
      if (mod(theta - start, TAU) <= ring.gapSize) return true;
    }
    return false;
  }

  ringHit(b, ring, nx, ny, px, py) {
    const s = this.s, w = ring.speed;
    const imp = this.contact(b, nx, ny, -w * py, w * px, s.wall_bounce * b.bounce, s.wall_grip);
    if (imp > 0) { b.vx *= s.energy_boost; b.vy *= s.energy_boost; }
  }

  gapEdges(b, ring, half) {
    if (ring.gaps <= 0) return;
    const step = TAU / ring.gaps;
    for (let i = 0; i < ring.gaps; i++) {
      const st = ring.angle + i * step;
      for (const a of [st, st + ring.gapSize]) {
        const ex = Math.cos(a) * ring.radius, ey = Math.sin(a) * ring.radius;
        const dx = b.x - ex, dy = b.y - ey, d = Math.hypot(dx, dy), rr = b.r + half;
        if (d > 1e-6 && d < rr) {
          const nx = dx / d, ny = dy / d;
          b.x += nx * (rr - d);
          b.y += ny * (rr - d);
          this.ringHit(b, ring, nx, ny, ex, ey);
        }
      }
    }
  }

  ringCollide(b, n) {
    const d = Math.hypot(b.x, b.y);
    if (d < 1e-6) return;
    const L = b.layer;
    if (L < n) {
      const ring = this.rings[L], R = ring.radius, half = ring.thickness / 2;
      if (d + b.r > R - half) {
        const theta = Math.atan2(b.y, b.x);
        if (this.inGap(ring, theta)) {
          if (d > R) { b.layer++; if (b.layer >= n) this.escaped(b); }
          else this.gapEdges(b, ring, half);
        } else if (d < R) {
          const nx = -b.x / d, ny = -b.y / d, target = R - half - b.r;
          b.x = -nx * target;
          b.y = -ny * target;
          this.ringHit(b, ring, nx, ny, -nx * R, -ny * R);
        } else {
          b.layer++;
          if (b.layer >= n) this.escaped(b);
        }
        return;
      }
    }
    if (L > 0) {
      const ring = this.rings[L - 1], R = ring.radius, half = ring.thickness / 2;
      if (d - b.r < R + half) {
        const theta = Math.atan2(b.y, b.x);
        if (this.inGap(ring, theta)) {
          if (d < R) b.layer--;
          else this.gapEdges(b, ring, half);
        } else if (d > R) {
          const nx = b.x / d, ny = b.y / d, target = R + half + b.r;
          b.x = nx * target;
          b.y = ny * target;
          this.ringHit(b, ring, nx, ny, nx * R, ny * R);
        } else {
          b.layer--;
        }
      }
    }
  }

  escaped(b) {
    if (b.rewarded) return;
    b.rewarded = true;
    this.stats.escapes++;
    this.spawnCenter(this.s.balls_per_escape);
  }

  contact(b, nx, ny, svx, svy, e, grip) {
    const rvx = b.vx - svx, rvy = b.vy - svy, vn = rvx * nx + rvy * ny;
    if (vn >= 0) return 0;
    const tx = -ny, ty = nx, vt = rvx * tx + rvy * ty;
    const vn2 = -vn * e, vt2 = vt * (1 - grip);
    b.vx = svx + nx * vn2 + tx * vt2;
    b.vy = svy + ny * vn2 + ty * vt2;
    b.bounces++;
    return -vn;
  }

  // --- ball vs ball
  ballCollisions() {
    const balls = this.balls.filter((b) => b.alive && !b.ghost);
    if (balls.length < 2) return;
    let maxr = 0;
    for (const b of balls) if (b.r > maxr) maxr = b.r;
    const cs = clamp(maxr * 2, 16, 100);
    const grid = new Map();
    const KEY = (cx, cy) => cx * 1048576 + cy;
    for (const b of balls) {
      const cx = Math.floor(b.x / cs), cy = Math.floor(b.y / cs), k = KEY(cx, cy);
      let cell = grid.get(k);
      if (!cell) grid.set(k, (cell = { cx, cy, list: [] }));
      cell.list.push(b);
    }
    const e1 = 1 + this.s.ball_bounce;
    let work = 0;
    const budget = this.limits.workBudget * 2;
    for (const c of grid.values()) {
      const cell = c.list;
      const others = [cell];
      for (const [ox, oy] of [[1, 0], [0, 1], [1, 1], [1, -1]]) {
        const o = grid.get(KEY(c.cx + ox, c.cy + oy));
        if (o) others.push(o.list);
      }
      for (let i = 0; i < cell.length; i++) {
        const b1 = cell[i];
        const m1 = b1.frozen > 0 ? 1e9 : b1.mass;
        for (let oi = 0; oi < others.length; oi++) {
          const other = others[oi];
          for (let j = oi === 0 ? i + 1 : 0; j < other.length; j++) {
            const b2 = other[j];
            work++;
            const dx = b2.x - b1.x, dy = b2.y - b1.y, rr = b1.r + b2.r, d2 = dx * dx + dy * dy;
            if (d2 >= rr * rr || d2 < 1e-9) continue;
            const d = Math.sqrt(d2), nx = dx / d, ny = dy / d;
            const m2 = b2.frozen > 0 ? 1e9 : b2.mass, tot = m1 + m2, ov = rr - d;
            b1.x -= (nx * ov * m2) / tot; b1.y -= (ny * ov * m2) / tot;
            b2.x += (nx * ov * m1) / tot; b2.y += (ny * ov * m1) / tot;
            const rv = (b2.vx - b1.vx) * nx + (b2.vy - b1.vy) * ny;
            if (rv < 0) {
              const j2 = (-e1 * rv) / (1 / m1 + 1 / m2);
              b1.vx -= (j2 / m1) * nx; b1.vy -= (j2 / m1) * ny;
              b2.vx += (j2 / m2) * nx; b2.vy += (j2 / m2) * ny;
            }
          }
        }
        if (work > budget) { this.work += work; return; } // hard stop for pathological piles
      }
    }
    this.work += work;
  }

  // --- blocks
  toLocal(blk, px, py) {
    return rot(px - blk.x, py - blk.y, -blk.angle);
  }

  contains(blk, px, py, pad) {
    if (blk.shape === "circle") return Math.hypot(px - blk.x, py - blk.y) <= blk.r + pad;
    const [lx, ly] = this.toLocal(blk, px, py);
    return Math.abs(lx) <= blk.w / 2 + pad && Math.abs(ly) <= blk.h / 2 + pad;
  }

  overlaps(blk, b) {
    return this.contains(blk, b.x, b.y, b.r * blk.pad);
  }

  velAt(blk, px, py) {
    const p = blk.p;
    switch (blk.key) {
      case "spinner": return [-num(p.spin, 0.05) * (py - blk.y), num(p.spin, 0.05) * (px - blk.x)];
      case "conveyor": { const sp = num(p.speed, 4); return [Math.cos(blk.angle) * sp, Math.sin(blk.angle) * sp]; }
      case "mover": return [blk.vx || 0, blk.vy || 0];
      default: return [0, 0];
    }
  }

  updateBlock(blk, dt) {
    const p = blk.p;
    blk.t += dt;
    switch (blk.key) {
      case "spinner": blk.angle = mod(blk.angle + num(p.spin, 0.05) * dt, TAU); break;
      case "saw": blk.angle = mod(blk.angle + num(p.spin, 0.2) * dt, TAU); break;
      case "laser": {
        blk.angle = mod(blk.angle + num(p.spin, 0) * dt, TAU);
        const ca = Math.cos(blk.angle), sa = Math.sin(blk.angle);
        const ax = blk.x + (ca * blk.w) / 2, ay = blk.y + (sa * blk.w) / 2;
        const len = clamp(num(p.length, 500), 0, 3000), bx = ax + ca * len, by = ay + sa * len;
        for (const b of this.balls) if (pointSegDist(b.x, b.y, ax, ay, bx, by) < b.r + 2) this.kill(b);
        this.work += this.balls.length;
        break;
      }
      case "mover": {
        const travel = num(p.travel, 150), speed = num(p.speed, 0.03);
        blk.phase += speed * dt;
        const off = Math.sin(blk.phase) * travel, dv = Math.cos(blk.phase) * travel * speed;
        const ca = Math.cos(blk.angle), sa = Math.sin(blk.angle);
        blk.x = blk.ox + ca * off; blk.y = blk.oy + sa * off;
        blk.vx = ca * dv; blk.vy = sa * dv;
        break;
      }
      case "cannon": {
        blk.timer += dt;
        if (blk.timer >= clamp(num(p.interval, 40), 3, 1000)) {
          blk.timer = 0;
          const ca = Math.cos(blk.angle), sa = Math.sin(blk.angle), pw = clamp(num(p.power, 10), 0, 40);
          this.spawn(blk.x + ca * blk.w * 0.6, blk.y + sa * blk.w * 0.6, ca * pw, sa * pw, p.ball_kind || "normal");
        }
        break;
      }
      case "whitehole": {
        blk.timer += dt;
        if (blk.timer >= clamp(num(p.interval, 20), 2, 1000)) {
          blk.timer = 0;
          const a = Math.random() * TAU;
          this.spawn(blk.x + Math.cos(a) * 20, blk.y + Math.sin(a) * 20, Math.cos(a) * 4, Math.sin(a) * 4, p.ball_kind || "normal");
        }
        break;
      }
      case "tesla": {
        blk.timer += dt;
        if (blk.timer >= clamp(num(p.interval, 30), 3, 1000)) {
          const range = clamp(num(p.range, 220), 0, 2000);
          let best = null, bd = range * range;
          for (const b of this.balls) {
            const d2 = (b.x - blk.x) ** 2 + (b.y - blk.y) ** 2;
            if (d2 < bd) { best = b; bd = d2; }
          }
          this.work += this.balls.length;
          if (best) { blk.timer = 0; this.kill(best); }
        }
        break;
      }
    }
  }

  collideBlock(blk, b) {
    const key = blk.key, p = blk.p;
    if (key === "door") {
      const open = num(p.open_time, 90), closed = num(p.closed_time, 120);
      if (mod(blk.t, open + closed) >= closed) return;
    }
    if (key === "spike" || key === "saw") {
      if (this.contains(blk, b.x, b.y, key === "saw" ? b.r - 2 : b.r)) this.kill(b);
      return;
    }
    let nx, ny, pen;
    if (blk.shape === "circle") {
      const dx = b.x - blk.x, dy = b.y - blk.y, d = Math.hypot(dx, dy), rr = blk.r + b.r;
      if (d >= rr) return;
      [nx, ny] = d < 1e-6 ? [0, -1] : [dx / d, dy / d];
      pen = rr - d;
    } else {
      const [lx, ly] = this.toLocal(blk, b.x, b.y);
      if (key === "oneway" && ly > 0) return;
      const hw = blk.w / 2, hh = blk.h / 2;
      const cx = clamp(lx, -hw, hw), cy = clamp(ly, -hh, hh);
      const dx = lx - cx, dy = ly - cy, d2 = dx * dx + dy * dy;
      if (d2 > b.r * b.r) return;
      let lnx, lny;
      if (d2 > 1e-9) {
        const d = Math.sqrt(d2);
        lnx = dx / d; lny = dy / d; pen = b.r - d;
      } else {
        const ox = hw - Math.abs(lx), oy = hh - Math.abs(ly);
        if (ox < oy) { lnx = lx > 0 ? 1 : -1; lny = 0; pen = ox + b.r; }
        else { lnx = 0; lny = ly > 0 ? 1 : -1; pen = oy + b.r; }
      }
      [nx, ny] = rot(lnx, lny, blk.angle);
    }
    b.x += nx * pen;
    b.y += ny * pen;
    const [svx, svy] = this.velAt(blk, b.x, b.y);
    const restitution = num(p.restitution, blk.restitution);
    this.contact(b, nx, ny, svx, svy, restitution * b.bounce, blk.friction);
    if (key === "bumper") {
      const power = num(p.power, 9), vn = b.vx * nx + b.vy * ny;
      if (vn < power) { b.vx += nx * (power - vn); b.vy += ny * (power - vn); }
    }
  }

  touch(blk, b, dt) {
    const p = blk.p, key = blk.key;
    const dx = blk.x - b.x, dy = blk.y - b.y, d = Math.hypot(dx, dy);
    switch (key) {
      case "attractor": case "repulsor": case "whitehole": {
        if (d < 6) return;
        const sign = key === "attractor" ? 1 : -1;
        const a = sign * num(p.strength, 0.6) * 0.6 * Math.sqrt(Math.max(0, 1 - d / blk.r)) * dt;
        b.vx += (dx / d) * a; b.vy += (dy / d) * a;
        return;
      }
      case "blackhole": {
        if (d < num(p.core, 22)) { this.kill(b); return; }
        const a = ((num(p.strength, 1.2) * 45) / (d + 30)) * (1 - d / blk.r) * dt;
        b.vx += (dx / d) * a; b.vy += (dy / d) * a;
        return;
      }
      case "vortex": {
        if (d < 5) return;
        const st = num(p.strength, 0.5), k = (1 - d / blk.r) * dt, t = st * 0.6 * k;
        const ex = -dx / d, ey = -dy / d; // from centre to ball
        b.vx += -ey * t - ex * Math.abs(st) * 0.12 * k;
        b.vy += ex * t - ey * Math.abs(st) * 0.12 * k;
        return;
      }
      case "wind": case "booster": {
        const st = num(p.strength, key === "wind" ? 0.3 : 1);
        b.vx += Math.cos(blk.angle) * st * dt; b.vy += Math.sin(blk.angle) * st * dt;
        return;
      }
      case "slow": { const k = Math.max(0, 1 - num(p.strength, 0.08) * dt); b.vx *= k; b.vy *= k; return; }
      case "water": {
        const k = Math.max(0, 1 - num(p.drag, 0.03) * dt), [gx, gy] = this.gravity(), by = num(p.buoyancy, 1.6);
        b.vx = b.vx * k - gx * by * dt; b.vy = b.vy * k - gy * by * dt;
        return;
      }
      case "antigrav": {
        const [gx, gy] = this.gravity(), st = num(p.strength, 1);
        b.vx -= gx * (1 + st) * dt; b.vy -= gy * (1 + st) * dt;
        return;
      }
      case "freeze": {
        if (b.cooldown <= 0 && b.frozen <= 0) { const du = num(p.duration, 120); b.frozen = du; b.cooldown = du + 45; }
        return;
      }
      case "portal": {
        if (b.cooldown > 0) return;
        const ch = num(p.channel, 0);
        for (const o of this.blocks.values()) {
          if (o !== blk && o.key === "portal" && num(o.p.channel, 0) === ch) {
            const sp = Math.hypot(b.vx, b.vy) || 1, off = o.r + b.r + 2;
            b.x = o.x + (b.vx / sp) * off; b.y = o.y + (b.vy / sp) * off;
            b.cooldown = 20;
            b.layer = this.layerFor(Math.hypot(b.x, b.y));
            return;
          }
        }
        return;
      }
      case "teleporter": {
        if (b.cooldown > 0) return;
        const a = Math.random() * TAU, range = clamp(num(p.range, 600), 0, 5000);
        const dist = blk.r + 40 + Math.random() * Math.max(1, range - blk.r - 40);
        const hw = this.s.world_width / 2 - b.r, hh = this.s.world_height / 2 - b.r;
        b.x = clamp(blk.x + Math.cos(a) * dist, -hw, hw); b.y = clamp(blk.y + Math.sin(a) * dist, -hh, hh);
        b.layer = this.layerFor(Math.hypot(b.x, b.y));
        b.cooldown = 30;
        return;
      }
      case "splitter": {
        if (b.cooldown > 0 || (b.split || 0) > 6) return;
        b.cooldown = 30; b.split = (b.split || 0) + 1;
        const sp = Math.hypot(b.vx, b.vy), base = Math.atan2(b.vy, b.vx), count = clamp(num(p.count, 2), 2, 6);
        for (let i = 1; i < count; i++) {
          const a = base + (i - (count - 1) / 2) * 0.35;
          const nb = this.spawn(b.x, b.y, Math.cos(a) * sp, Math.sin(a) * sp, b.kind, b.color,
            b.r / ((this.types[b.kind] || {}).size || 1));
          if (nb) { nb.cooldown = 30; nb.split = b.split; nb.layer = b.layer; nb.rewarded = b.rewarded; }
        }
        return;
      }
      case "turbo": {
        if (b.cooldown > 0) return;
        const f = clamp(num(p.factor, 1.6), 0.1, 4);
        b.cooldown = 20; b.vx *= f; b.vy *= f;
        return;
      }
      case "hoop": if (d < blk.r - b.r * 0.3) this.kill(b); return;
      case "paint": b.color = hsv(num(p.hue, 0.55), 0.85, 1); return;
      case "grow": case "shrink": {
        if (b.cooldown > 0) return;
        b.cooldown = 25;
        const f = num(p.factor, key === "grow" ? 1.35 : 0.7);
        b.r = clamp(b.r * f, 2.5, 45);
        b.mass = b.r * b.r * ((this.types[b.kind] || {}).density || 1);
        return;
      }
      case "mine": {
        if (this.blocks.has(blk.uid)) {
          this.blocks.delete(blk.uid);
          this.events.push({ t: "blocks", up: [], del: [blk.uid] });
          this.explode(blk.x, blk.y, num(p.blast, 130), num(p.power, 12));
        }
        return;
      }
      case "transmuter": {
        const k = p.ball_kind;
        if (b.kind !== k && this.types[k] && b.cooldown <= 0) {
          const old = this.types[b.kind] || { size: 1 }, nt = this.types[k];
          b.r = (b.r / old.size) * nt.size;
          b.mass = b.r * b.r * nt.density;
          b.bounce = nt.bounce;
          b.kind = k;
          b.ghost = k === "ghost";
          if (nt.color) b.color = nt.color;
          b.cooldown = 10;
        }
        return;
      }
    }
  }

  perFrame(frames) {
    const s = this.s, n = this.rings.length, life = s.escaped_lifetime * 60;
    const [gx, gy] = this.gravity();
    for (const b of this.balls) {
      b.age += frames;
      if (n && b.layer >= n) {
        b.freeAge += frames;
        if (life > 0 && b.freeAge > life) { this.kill(b); continue; }
      }
      switch (b.kind) {
        case "rocket": {
          const sp = Math.hypot(b.vx, b.vy);
          if (sp > 0.1) { b.vx += (b.vx / sp) * 0.15 * frames; b.vy += (b.vy / sp) * 0.15 * frames; }
          break;
        }
        case "balloon":
          b.vx -= gx * 1.6 * frames; b.vy -= gy * 1.6 * frames;
          if (b.bounces >= 3) this.kill(b);
          break;
        case "phantom": b.ghost = Math.floor(b.age / 60) % 2 === 1; break;
        case "hyper":
          if (Math.floor(b.age / 30) !== Math.floor((b.age - frames) / 30)) {
            const sp = Math.max(4, Math.hypot(b.vx, b.vy)), a = Math.random() * TAU;
            b.vx = Math.cos(a) * sp; b.vy = Math.sin(a) * sp;
          }
          break;
        case "rainbow": b.color = hsv(mod(b.age * 0.008 + b.id * 0.1, 1), 1, 1); break;
      }
    }
    if (this.balls.some((b) => !b.alive)) this.balls = this.balls.filter((b) => b.alive);
    if (s.limit_action === "Delete Oldest" && this.balls.length > this.maxBalls()) {
      this.balls.splice(0, this.balls.length - this.maxBalls());
    }
  }

  // ------------------------------------------------------------------ network
  // Binary snapshot. Layout (little endian):
  //   u8 'S', u8 version, u8 ring count, u8 flags, u16 ball count, u16 reserved
  //   f32 ring angle * ring count
  //   per ball: i16 x, i16 y, i16 vx*100, i16 vy*100, u16 id, u8 r*4, u8 kind, u8 r, u8 g, u8 b, u8 flags
  snapshot() {
    const nb = Math.min(this.balls.length, this.limits.maxSendBalls, 65535);
    const nr = this.rings.length;
    const start = this.balls.length - nb;
    const buf = new ArrayBuffer(8 + nr * 4 + nb * 16);
    const v = new DataView(buf);
    v.setUint8(0, 83);
    v.setUint8(1, 1);
    v.setUint8(2, nr);
    v.setUint8(3, this.overloaded ? 1 : 0);
    v.setUint16(4, nb, true);
    let o = 8;
    for (const r of this.rings) { v.setFloat32(o, r.angle, true); o += 4; }
    const kindIdx = new Map(this.kinds.map((k, i) => [k, i]));
    for (let i = start; i < this.balls.length; i++) {
      const b = this.balls[i];
      v.setInt16(o, clamp(Math.round(b.x), -32767, 32767), true);
      v.setInt16(o + 2, clamp(Math.round(b.y), -32767, 32767), true);
      v.setInt16(o + 4, clamp(Math.round(b.vx * 100), -32767, 32767), true);
      v.setInt16(o + 6, clamp(Math.round(b.vy * 100), -32767, 32767), true);
      v.setUint16(o + 8, b.id, true);
      v.setUint8(o + 10, clamp(Math.round(b.r * 4), 1, 255));
      v.setUint8(o + 11, kindIdx.get(b.kind) ?? 0);
      v.setUint8(o + 12, b.color[0]);
      v.setUint8(o + 13, b.color[1]);
      v.setUint8(o + 14, b.color[2]);
      v.setUint8(o + 15, (b.ghost ? 1 : 0) | (b.frozen > 0 ? 2 : 0));
      o += 16;
    }
    return buf;
  }
}
