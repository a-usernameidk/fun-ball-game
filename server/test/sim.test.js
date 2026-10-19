// Quick sanity test for the cloud physics: run with `node test/sim.test.js`
import { Sim } from "../src/sim.js";

const limits = { maxBalls: 2000, maxSendBalls: 2000, maxBlocks: 300, maxSubsteps: 3, workBudget: 60000 };
let failed = 0;
const check = (ok, msg) => { console.log((ok ? "ok   " : "FAIL ") + msg); if (!ok) failed++; };

// 1. classic ring: balls escape and multiply, nobody leaks through the wall
let sim = new Sim(limits);
sim.spawnCenter(1);
let leaks = 0;
for (let i = 0; i < 1800; i++) {
  sim.step(2);
  for (const b of sim.balls) {
    const d = Math.hypot(b.x, b.y);
    if (b.layer !== sim.layerFor(d) && Math.abs(d - sim.rings[0].radius) > b.r + 6) leaks++;
  }
}
check(sim.stats.escapes > 5, `escapes happen (${sim.stats.escapes})`);
check(sim.balls.length > 10, `balls multiply (${sim.balls.length})`);
check(leaks === 0, `no balls leak through rings (${leaks})`);

// 2. hard ball cap even when asking for way more
sim = new Sim(limits);
sim.setSettings({ max_balls: 100000, ring_count: 0, world_width: 4000, world_height: 4000 });
sim.spawnCenter(50000);
check(sim.balls.length <= limits.maxBalls, `cloud ball cap holds (${sim.balls.length} <= ${limits.maxBalls})`);

// 3. a crazy pile triggers the work budget and sheds balls instead of melting
sim = new Sim({ ...limits, workBudget: 20000 });
sim.setSettings({ ring_count: 0, world_width: 300, world_height: 300, gravity: 0.5 });
sim.spawnCenter(2000);
let overloaded = false;
for (let i = 0; i < 60; i++) { sim.step(2); overloaded = overloaded || sim.overloaded; }
check(overloaded, "overload detected for a packed box");
check(sim.balls.length < 2000, `load shedding removed balls (${sim.balls.length} left, ${sim.stats.shed} shed)`);
check(sim.spawn(0, 0, 0, 0, "normal") === null || !sim.overloaded, "no spawns while overloaded");

// 4. blocks: a wall stops balls, a black hole eats them
sim = new Sim(limits);
sim.setSettings({ ring_count: 0, gravity: 0.3 });
sim.upsertBlock({ uid: "floor", key: "wall", x: 0, y: 200, w: 800, h: 30, angle: 0, phys: { solid: true, shape: "rect", restitution: 0.5 } });
sim.spawn(0, 0, 0, 0, "normal");
for (let i = 0; i < 300; i++) sim.step(2);
check(sim.balls[0] && sim.balls[0].y < 200, `wall holds the ball (y=${sim.balls[0]?.y.toFixed(1)})`);
sim.upsertBlock({ uid: "bh", key: "blackhole", x: 0, y: 100, r: 400, strength: 3, core: 40, phys: { solid: false, shape: "circle" } });
for (let i = 0; i < 600; i++) sim.step(2);
check(sim.balls.length === 0, "black hole eats the ball");

// 5. snapshot encodes every ball
sim = new Sim(limits);
sim.spawnCenter(100);
const buf = sim.snapshot();
const v = new DataView(buf);
check(v.getUint8(0) === 83 && v.getUint16(4, true) === 100, "snapshot header");
check(buf.byteLength === 8 + 4 * sim.rings.length + 100 * 16, `snapshot size ${buf.byteLength}`);

// 6. speed: 2000 free balls
sim = new Sim(limits);
sim.setSettings({ ring_count: 0, world_width: 5000, world_height: 3000, gravity: 0.1 });
sim.spawnCenter(2000);
const t0 = Date.now();
for (let i = 0; i < 100; i++) sim.step(2);
const ms = (Date.now() - t0) / 100;
check(ms < 30, `2000 balls step in ${ms.toFixed(2)} ms`);

process.exit(failed ? 1 : 0);
