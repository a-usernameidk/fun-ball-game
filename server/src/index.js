// Fun Ball Game server for Cloudflare Workers.
//
//   GET    /                      a small web page listing shared levels
//   GET    /api/health            server info + limits (the game's "Test connection")
//   GET    /api/levels            list levels   ?sort=new|top &q=search &offset=0
//   GET    /api/levels/:id        download one level (counts as a play)
//   POST   /api/levels            upload a level  {name, author, description, theme, data}
//   POST   /api/levels/:id/like   like a level (once per player)
//   DELETE /api/levels/:id        delete your level (needs the X-Delete-Token you got on upload)
//   GET    /room/:CODE            WebSocket for multiplayer / cloud physics rooms

import { Room, limitsFrom } from "./room.js";
import { Limiter } from "./limiter.js";

export { Room, Limiter };

const VERSION = 1;
const PAGE = 30;

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, X-Delete-Token",
};

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status, headers: { "Content-Type": "application/json", ...CORS },
  });
}

function err(message, status = 400) {
  return json({ error: message }, status);
}

function intVar(env, name, dflt) {
  const v = parseInt(env[name], 10);
  return Number.isFinite(v) && v > 0 ? v : dflt;
}

async function sha256(text) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function ipHash(request, env) {
  const ip = request.headers.get("CF-Connecting-IP") || "local";
  return (await sha256(ip + "|" + (env.SALT || "fun-ball-game"))).slice(0, 32);
}

function randomId(n = 8) {
  const abc = "abcdefghijkmnpqrstuvwxyz23456789";
  const bytes = crypto.getRandomValues(new Uint8Array(n));
  return [...bytes].map((b) => abc[b % abc.length]).join("");
}

function clean(s, max) {
  return String(s ?? "").replace(/[\u0000-\u001f\u007f]/g, "").trim().slice(0, max);
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

const LIST_COLS = "id, name, author, description, theme, blocks, created, likes, plays";

async function listLevels(url, env) {
  const sort = url.searchParams.get("sort") === "top" ? "likes DESC, plays DESC, created DESC" : "created DESC";
  const offset = Math.max(0, parseInt(url.searchParams.get("offset"), 10) || 0);
  const q = clean(url.searchParams.get("q"), 40);
  const stmt = q
    ? env.DB.prepare(`SELECT ${LIST_COLS} FROM levels WHERE name LIKE ?1 OR author LIKE ?1 ORDER BY ${sort} LIMIT ?2 OFFSET ?3`)
      .bind(`%${q}%`, PAGE, offset)
    : env.DB.prepare(`SELECT ${LIST_COLS} FROM levels ORDER BY ${sort} LIMIT ?1 OFFSET ?2`).bind(PAGE, offset);
  const { results } = await stmt.all();
  return json({ levels: results, offset, page: PAGE });
}

async function getLevel(id, env) {
  const row = await env.DB.prepare(`SELECT ${LIST_COLS}, data FROM levels WHERE id = ?1`).bind(id).first();
  if (!row) return err("Level not found", 404);
  await env.DB.prepare("UPDATE levels SET plays = plays + 1 WHERE id = ?1").bind(id).run();
  const { data, ...meta } = row;
  return json({ ...meta, plays: meta.plays + 1, data: JSON.parse(data) });
}

async function uploadLevel(request, env) {
  const maxBytes = intVar(env, "MAX_LEVEL_KB", 400) * 1024;
  const text = await request.text();
  if (text.length > maxBytes + 4096) return err(`Level is too big (max ${maxBytes / 1024} KB)`, 413);
  let body;
  try { body = JSON.parse(text); } catch (e) { return err("Bad JSON"); }
  const name = clean(body.name, 40);
  const author = clean(body.author, 24) || "Anonymous";
  const description = clean(body.description, 200);
  const theme = clean(body.theme, 24) || "Midnight";
  const data = body.data;
  if (!name) return err("Give your level a name");
  if (!data || typeof data !== "object" || !Array.isArray(data.blocks)) return err("Missing level data");
  if (data.blocks.length > intVar(env, "MAX_LEVEL_BLOCKS", 2000)) return err("Too many blocks");
  delete data.balls; // levels are layouts, not ball saves
  const dataText = JSON.stringify(data);
  if (dataText.length > maxBytes) return err(`Level is too big (max ${maxBytes / 1024} KB)`, 413);

  const ip = await ipHash(request, env);
  const perHour = intVar(env, "UPLOADS_PER_HOUR", 10);
  const recent = await env.DB.prepare("SELECT COUNT(*) AS n FROM levels WHERE ip_hash = ?1 AND created > ?2")
    .bind(ip, Date.now() - 3600000).first();
  if (recent && recent.n >= perHour) return err(`Upload limit reached (${perHour} per hour). Try again later.`, 429);

  const id = randomId(8);
  const token = randomId(24);
  await env.DB.prepare(
    "INSERT INTO levels (id, name, author, description, theme, blocks, data, created, token_hash, ip_hash) " +
    "VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10)",
  ).bind(id, name, author, description, theme, data.blocks.length, dataText, Date.now(), await sha256(token), ip).run();
  return json({ id, token }, 201);
}

async function likeLevel(id, request, env) {
  const ip = await ipHash(request, env);
  const exists = await env.DB.prepare("SELECT 1 FROM levels WHERE id = ?1").bind(id).first();
  if (!exists) return err("Level not found", 404);
  const res = await env.DB.prepare("INSERT OR IGNORE INTO likes (level_id, ip_hash) VALUES (?1, ?2)").bind(id, ip).run();
  if (res.meta.changes) await env.DB.prepare("UPDATE levels SET likes = likes + 1 WHERE id = ?1").bind(id).run();
  const row = await env.DB.prepare("SELECT likes FROM levels WHERE id = ?1").bind(id).first();
  return json({ likes: row.likes, liked: true, already: !res.meta.changes });
}

async function deleteLevel(id, request, env) {
  const token = request.headers.get("X-Delete-Token") || "";
  const row = await env.DB.prepare("SELECT token_hash FROM levels WHERE id = ?1").bind(id).first();
  if (!row) return err("Level not found", 404);
  if (!token || (await sha256(token)) !== row.token_hash) return err("That isn't your level", 403);
  await env.DB.batch([
    env.DB.prepare("DELETE FROM levels WHERE id = ?1").bind(id),
    env.DB.prepare("DELETE FROM likes WHERE level_id = ?1").bind(id),
  ]);
  return json({ deleted: true });
}

async function homePage(env) {
  const { results } = await env.DB.prepare(`SELECT ${LIST_COLS} FROM levels ORDER BY created DESC LIMIT 50`).all();
  const rows = results.map((l) => `<li><b>${escapeHtml(l.name)}</b> by ${escapeHtml(l.author)}
    <span>${escapeHtml(l.theme)} · ${l.blocks} blocks · ♥ ${l.likes} · ▶ ${l.plays}</span>
    ${l.description ? `<p>${escapeHtml(l.description)}</p>` : ""}</li>`).join("");
  const html = `<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Fun Ball Game levels</title>
<style>body{font-family:system-ui,sans-serif;background:#0c0c14;color:#e6e8f5;max-width:760px;margin:0 auto;padding:24px 16px}
h1{color:#00ffcc}li{list-style:none;background:#1e1e30;border:1px solid #303048;border-radius:10px;padding:12px 14px;margin:10px 0}
span{color:#8c90aa;margin-left:8px;font-size:14px}p{margin:6px 0 0;color:#b8bbd0}</style></head>
<body><h1>Fun Ball Game</h1><p>Shared levels. Open the game, go to <b>Online</b> and paste this server's address
into Settings &rarr; Online to play them.</p><ul>${rows || "<li>No levels yet. Be the first to share one!</li>"}</ul></body></html>`;
  return new Response(html, { headers: { "Content-Type": "text/html; charset=utf-8" } });
}

// The server sets up its own database tables the first time it runs, so there's no
// separate "create the schema" step when deploying.
const SCHEMA = [
  `CREATE TABLE IF NOT EXISTS levels (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, author TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '', theme TEXT NOT NULL DEFAULT 'Midnight',
    blocks INTEGER NOT NULL DEFAULT 0, data TEXT NOT NULL, created INTEGER NOT NULL,
    likes INTEGER NOT NULL DEFAULT 0, plays INTEGER NOT NULL DEFAULT 0,
    token_hash TEXT NOT NULL, ip_hash TEXT NOT NULL)`,
  "CREATE INDEX IF NOT EXISTS levels_created ON levels (created DESC)",
  "CREATE INDEX IF NOT EXISTS levels_top ON levels (likes DESC, plays DESC)",
  "CREATE INDEX IF NOT EXISTS levels_ip ON levels (ip_hash, created)",
  `CREATE TABLE IF NOT EXISTS likes (
    level_id TEXT NOT NULL, ip_hash TEXT NOT NULL, PRIMARY KEY (level_id, ip_hash))`,
];
let schemaReady = null;

function ensureSchema(env) {
  if (!schemaReady) {
    schemaReady = env.DB.batch(SCHEMA.map((sql) => env.DB.prepare(sql))).catch((e) => {
      schemaReady = null; // try again on the next request
      throw e;
    });
  }
  return schemaReady;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, "") || "/";
    const method = request.method;
    if (method === "OPTIONS") return new Response(null, { status: 204, headers: CORS });

    try {
      const room = path.match(/^\/room\/([A-Za-z0-9]{4,8})$/);
      if (room) {
        const code = room[1].toUpperCase();
        const stub = env.ROOMS.get(env.ROOMS.idFromName(code));
        const u = new URL(request.url);
        u.pathname = `/room/${code}`;
        return stub.fetch(new Request(u.toString(), request));
      }
      await ensureSchema(env);
      if (path === "/" && method === "GET") return homePage(env);
      if (path === "/api/health") {
        const l = limitsFrom(env);
        return json({ ok: true, game: "fun-ball-game", version: VERSION, limits: l });
      }
      if (path === "/api/levels") {
        if (method === "GET") return listLevels(url, env);
        if (method === "POST") return uploadLevel(request, env);
      }
      const one = path.match(/^\/api\/levels\/([a-z0-9]{8})(\/like)?$/);
      if (one) {
        const [, id, like] = one;
        if (like && method === "POST") return likeLevel(id, request, env);
        if (!like && method === "GET") return getLevel(id, env);
        if (!like && method === "DELETE") return deleteLevel(id, request, env);
      }
      return err("Not found", 404);
    } catch (e) {
      console.error(e);
      return err("Server error", 500);
    }
  },
};
