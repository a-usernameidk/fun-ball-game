"""Online features: shared levels (HTTP) and multiplayer / cloud-physics rooms (WebSocket).

Everything network-related runs on background threads. Results are handed back to
the game loop through queues and processed by `poll()` once per frame, so the game
never freezes while waiting for the server.
"""

import json
import math
import os
import queue
import random
import struct
import threading
import urllib.error
import urllib.parse
import urllib.request

from . import blocks as B
from .balls import BALL_ORDER, BALL_TYPES, Ball
from .settings import COLOR_SCHEMES, PREF_FIELDS

try:
    import websocket  # pip install websocket-client
except ImportError:  # multiplayer is optional
    websocket = None

USER_AGENT = "FunBallGame/4.3"
# The game's online server (your Cloudflare Worker). Everyone who plays this copy of the
# game uses it automatically: players just host a room and share the code.
# Put your Worker's address here, e.g. "https://fun-ball-game.yourname.workers.dev"
GAME_SERVER = "https://fun-ball-game.berf.workers.dev"


def server_url(settings):
    """The server to use: a custom one from Settings (advanced), else the built-in one."""
    return (settings.server_url or os.environ.get("FUN_BALL_SERVER", "") or GAME_SERVER).strip()
_results = queue.Queue()


def poll():
    """Run finished HTTP callbacks on the main thread. Call once per frame."""
    while True:
        try:
            cb, ok, data = _results.get_nowait()
        except queue.Empty:
            return
        try:
            cb(ok, data)
        except Exception as e:  # a broken callback must not kill the game
            print("network callback failed:", e)


def multiplayer_available():
    return websocket is not None


def new_room_code():
    return "".join(random.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(5))


# --------------------------------------------------------------------------
# HTTP: shared levels
# --------------------------------------------------------------------------
class Api:
    def __init__(self, base):
        self.base = (base or "").strip().rstrip("/")

    @property
    def configured(self):
        return self.base.startswith(("http://", "https://"))

    def _call(self, method, path, body=None, headers=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("User-Agent", USER_AGENT)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=12) as res:
                return True, json.loads(res.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            try:
                msg = json.loads(e.read().decode()).get("error") or f"HTTP {e.code}"
            except Exception:
                msg = f"HTTP {e.code}"
            return False, msg
        except Exception as e:
            return False, f"Can't reach the server ({type(e).__name__})"

    def request(self, method, path, cb, body=None, headers=None):
        if not self.configured:
            _results.put((cb, False, "Online isn't switched on in this copy of the game yet."))
            return

        def run():
            ok, data = self._call(method, path, body, headers)
            _results.put((cb, ok, data))
        threading.Thread(target=run, daemon=True).start()

    # convenience wrappers
    def health(self, cb):
        self.request("GET", "/api/health", cb)

    def list_levels(self, cb, sort="new", q="", offset=0):
        qs = urllib.parse.urlencode({"sort": sort, "q": q, "offset": offset})
        self.request("GET", "/api/levels?" + qs, cb)

    def get_level(self, lid, cb):
        self.request("GET", f"/api/levels/{urllib.parse.quote(lid)}", cb)

    def upload(self, name, author, description, theme, data, cb):
        self.request("POST", "/api/levels", cb, {"name": name, "author": author, "description": description,
                                                "theme": theme, "data": data})

    def like(self, lid, cb):
        self.request("POST", f"/api/levels/{urllib.parse.quote(lid)}/like", cb)

    def delete(self, lid, token, cb):
        self.request("DELETE", f"/api/levels/{urllib.parse.quote(lid)}", cb, headers={"X-Delete-Token": token})


# --------------------------------------------------------------------------
# WebSocket room connection
# --------------------------------------------------------------------------
class RoomClient:
    def __init__(self, server, code, name):
        base = server.strip().rstrip("/")
        base = base.replace("https://", "wss://", 1).replace("http://", "ws://", 1)
        self.url = f"{base}/room/{code}?name={urllib.parse.quote(name)}"
        self.inbox = queue.Queue()
        self.ws = None
        self.error = None
        self.open = False
        self.closed = False
        self._lock = threading.Lock()
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            self.ws = websocket.create_connection(self.url, timeout=10, header=[f"User-Agent: {USER_AGENT}"])
            self.ws.settimeout(None)
            self.open = True
            while not self.closed:
                op, data = self.ws.recv_data()
                if op == websocket.ABNF.OPCODE_TEXT:
                    self.inbox.put(json.loads(data.decode()))
                elif op == websocket.ABNF.OPCODE_BINARY:
                    self.inbox.put(bytes(data))
                elif op == websocket.ABNF.OPCODE_CLOSE:
                    break
        except Exception as e:
            if not self.closed:
                self.error = str(e) or type(e).__name__
        finally:
            self.open = False
            if not self.closed and not self.error:
                self.error = "Disconnected from the room"

    def send(self, msg):
        if not self.open:
            return
        try:
            with self._lock:
                self.ws.send(json.dumps(msg, separators=(",", ":")))
        except Exception as e:
            self.error = str(e) or "send failed"

    def poll(self, limit=400):
        out = []
        for _ in range(limit):
            try:
                out.append(self.inbox.get_nowait())
            except queue.Empty:
                break
        return out

    def close(self):
        self.closed = True
        try:
            if self.ws:
                self.ws.close()
        except Exception:
            pass


# --------------------------------------------------------------------------
# A multiplayer / cloud session attached to a SandboxScene
# --------------------------------------------------------------------------
DYNAMIC_ANGLE = {"spinner", "saw"}
BALL_SNAPSHOT_EVERY = 0.25
MAX_SNAPSHOT_BALLS = 600


def block_payload(blk):
    d = blk.to_dict()
    d["uid"] = blk.uid
    d["phys"] = {"shape": blk.shape, "solid": blk.solid, "restitution": blk.restitution,
                 "friction": blk.friction, "touch_pad": blk.touch_pad}
    return d


def block_sig(blk):
    d = blk.to_dict()
    if blk.key in DYNAMIC_ANGLE or (blk.key == "laser" and getattr(blk, "spin", 0)):
        d.pop("angle", None)
    return json.dumps(d, sort_keys=True, default=str)


def _hex(c):
    return "%02x%02x%02x" % tuple(int(v) for v in c[:3])


def _unhex(h):
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except (ValueError, TypeError):
        return (255, 255, 255)


class Session:
    def __init__(self, scene, server, code, name, creator=False, cloud=False):
        self.scene = scene
        self.world = scene.world
        self.s = scene.s
        self.code = code
        self.name = name
        self.creator = creator          # we brought the world; don't ask for it
        self.want_cloud = cloud
        self.room = RoomClient(server, code, name)
        self.my_id = None
        self.host = False
        self.players = {}               # id -> {"name", "color"}
        self.cloud = False              # the server is running the physics
        self.cloud_stats = None
        self.limits = {}
        self.synced = {}                # block uid -> signature we last agreed on
        self.last_settings = None
        self.cursors = {}               # id -> [x, y, tool, age]
        self.chat = []                  # [name, text, color, age]
        self.timers = {"blocks": 0.0, "settings": 0.0, "cursor": 0.0, "balls": 0.0}
        self.next_nid = 1
        self.status = "Connecting..."
        self.ended = None

    # --- state --------------------------------------------------------
    @property
    def connected(self):
        return self.room.open and self.my_id is not None

    def send(self, msg):
        self.room.send(msg)

    def close(self):
        self.room.close()
        self.world.remote = False
        self.world.spawn_lock = False

    def toast(self, text, color=(0, 255, 204)):
        self.scene.toast(text, color)

    def say(self, text):
        text = text.strip()[:200]
        if text and self.connected:
            self.send({"t": "chat", "m": text})
            me = self.players.get(self.my_id, {})
            self.chat.append([self.name, text, tuple(me.get("color", (255, 255, 255))), 0.0])

    # --- outgoing ------------------------------------------------------
    def send_spawns(self, items):
        pal = COLOR_SCHEMES.get(self.s.color_scheme) or [(255, 255, 255)]
        out = []
        for x, y, vx, vy, kind in items:
            c = BALL_TYPES.get(kind, {}).get("color") or random.choice(pal)
            out.append([round(x, 1), round(y, 1), round(vx, 2), round(vy, 2), kind, list(c)])
        for i in range(0, len(out), 200):
            self.send({"t": "spawn", "b": out[i:i + 200]})

    def send_boom(self, x, y, r, p):
        self.send({"t": "boom", "x": round(x, 1), "y": round(y, 1), "r": r, "p": p})

    def send_clear(self):
        self.send({"t": "clear"})

    def start_cloud(self):
        w = self.world
        types = {k: {"size": d["size"], "density": d["density"], "bounce": d["bounce"], "color": d["color"]}
                 for k, d in BALL_TYPES.items()}
        balls = []
        for b in w.balls[-2000:]:
            size = BALL_TYPES[b.kind]["size"]
            balls.append([round(b.x, 1), round(b.y, 1), round(b.vx, 2), round(b.vy, 2), b.kind, list(b.color),
                          round(b.r / size, 2)])
        self.send({"t": "cloud_start", "d": {
            "kinds": BALL_ORDER, "types": types, "settings": self._settings_payload(),
            "blocks": [block_payload(blk) for blk in w.blocks if blk.alive], "balls": balls}})
        self.status = "Starting cloud physics..."

    def stop_cloud(self):
        self.send({"t": "cloud_stop"})

    def _settings_payload(self):
        d = {k: v for k, v in self.s.to_dict().items() if k not in PREF_FIELDS}
        d["max_balls"] = self.s.max_balls if not self.s.unlimited_balls else 100000
        d["palette"] = [list(c) for c in (COLOR_SCHEMES.get(self.s.color_scheme) or [(255, 255, 255)])]
        return d

    # --- per frame -------------------------------------------------------
    def tick(self, dt):
        for msg in self.room.poll():
            try:
                if isinstance(msg, bytes):
                    self._cloud_snapshot(msg)
                else:
                    self._handle(msg)
            except Exception as e:  # never let a bad packet crash the game
                print("bad network message:", e)
        if self.room.error and not self.ended:
            self.ended = self.room.error
            self.status = "Disconnected"
            self.world.remote = False
            self.world.spawn_lock = False
            self.cloud = False
            self.toast(f"Room closed: {self.room.error}"[:80], (255, 60, 80))
            return
        for c in self.cursors.values():
            c[3] += dt
        for m in self.chat:
            m[3] += dt
        self.chat = self.chat[-30:]
        if not self.connected:
            return
        t = self.timers
        for k in t:
            t[k] += dt
        if t["blocks"] >= 0.2:
            t["blocks"] = 0.0
            self._sync_blocks()
        if t["settings"] >= 0.5:
            t["settings"] = 0.0
            self._sync_settings()
        if t["cursor"] >= 0.1:
            t["cursor"] = 0.0
            x, y = self.scene.mouse_w
            self.send({"t": "cur", "x": round(x), "y": round(y), "tool": self.scene.tool[1]})
        if self.host and not self.cloud and t["balls"] >= BALL_SNAPSHOT_EVERY:
            t["balls"] = 0.0
            self._send_balls()

    # --- block & settings sync -------------------------------------------
    def _sync_blocks(self):
        up, cur = [], set()
        for blk in self.world.blocks:
            if not blk.alive:
                continue
            cur.add(blk.uid)
            sig = block_sig(blk)
            if self.synced.get(blk.uid) != sig:
                self.synced[blk.uid] = sig
                up.append(block_payload(blk))
        dele = [uid for uid in self.synced if uid not in cur]
        for uid in dele:
            del self.synced[uid]
        for i in range(0, max(len(up), 1), 150):
            chunk = up[i:i + 150]
            if chunk or (dele and i == 0):
                self.send({"t": "blocks", "up": chunk, "del": dele if i == 0 else []})

    def _apply_blocks(self, msg):
        by_uid = {b.uid: b for b in self.world.blocks if b.alive}
        for d in msg.get("up", []):
            uid = d.get("uid")
            blk = by_uid.get(uid)
            if blk is not None and blk.key == d.get("key"):
                for k, v in d.items():
                    if k not in ("key", "phys", "uid") and hasattr(blk, k) and not callable(getattr(blk, k)):
                        try:
                            setattr(blk, k, v)
                        except AttributeError:
                            pass
                blk.after_load()
            else:
                if blk is not None:
                    blk.alive = False
                blk = B.from_dict(d)
                if blk is None:
                    continue
                self.world.blocks.append(blk)
            self.synced[uid] = block_sig(blk)
        dele = set(msg.get("del", []))
        if dele:
            for blk in self.world.blocks:
                if blk.uid in dele:
                    blk.alive = False
                    if blk is self.scene.selected:
                        self.scene.select(None)
            for uid in dele:
                self.synced.pop(uid, None)
        self.world.blocks = [b for b in self.world.blocks if b.alive]

    def _sync_settings(self):
        d = self._settings_payload()
        if d != self.last_settings:
            self.last_settings = d
            self.send({"t": "settings", "d": d})

    def _apply_settings(self, d):
        rings_before = [(r.radius, r.gaps, r.gap_size, r.speed) for r in self.world.rings]
        self.s.load_dict(d, skip=PREF_FIELDS + ("max_balls",))
        self.world.rebuild_rings()
        if rings_before != [(r.radius, r.gaps, r.gap_size, r.speed) for r in self.world.rings]:
            self.scene._build_right()
        self.last_settings = self._settings_payload()

    def _mark_all_synced(self):
        self.synced = {b.uid: block_sig(b) for b in self.world.blocks if b.alive}
        self.last_settings = self._settings_payload()

    # --- balls (normal rooms: the host keeps everyone in step) -------------
    def _send_balls(self):
        rows = []
        for b in self.world.balls[-MAX_SNAPSHOT_BALLS:]:
            if not getattr(b, "nid", 0):
                b.nid = self.next_nid
                self.next_nid = self.next_nid % 1000000 + 1
            size = BALL_TYPES[b.kind]["size"]
            rows.append([b.nid, round(b.x, 1), round(b.y, 1), round(b.vx, 2), round(b.vy, 2),
                         round(b.r / size, 2), b.kind, _hex(b.color), b.layer, int(b.rewarded)])
        self.send({"t": "balls", "b": rows, "rings": [round(r.angle, 4) for r in self.world.rings]})

    def _apply_balls(self, msg):
        w = self.world
        old = {getattr(b, "nid", 0): b for b in w.balls}
        new = []
        for row in msg.get("b", []):
            nid, x, y, vx, vy, r, kind, col, layer, rewarded = row
            b = old.get(nid)
            if b is None:
                b = Ball(x, y, vx, vy, r, _unhex(col), kind if kind in BALL_TYPES else "normal", self.s.trail_length)
                b.nid = nid
            else:
                if abs(b.x - x) + abs(b.y - y) > 80:
                    b.history.clear()
                b.x, b.y, b.vx, b.vy = x, y, vx, vy
                b.color = _unhex(col)
            b.layer = self.world.layer_for(math.hypot(b.x, b.y))
            b.rewarded = bool(rewarded)
            new.append(b)
        w.balls = new
        for r, a in zip(w.rings, msg.get("rings", [])):
            r.angle = a

    # --- balls (cloud rooms: binary snapshots from the server) -------------
    def _cloud_snapshot(self, data):
        if len(data) < 8 or data[0] != 83:
            return
        nr, count = data[2], struct.unpack_from("<H", data, 4)[0]
        o = 8
        angles = struct.unpack_from(f"<{nr}f", data, o) if nr else ()
        o += 4 * nr
        for r, a in zip(self.world.rings, angles):
            r.angle = a
        kinds = (self.cloud_stats or {}).get("kinds") or BALL_ORDER
        old = {getattr(b, "nid", 0): b for b in self.world.balls}
        new = []
        trail = self.s.trail_length
        for x, y, vx, vy, nid, r4, ki, cr, cg, cb, fl in struct.iter_unpack("<hhhhHBBBBBB", data[o:o + count * 16]):
            vx, vy = vx / 100.0, vy / 100.0
            kind = kinds[ki] if ki < len(kinds) else "normal"
            b = old.get(nid)
            if b is None or b.kind != kind:
                b = Ball(x, y, vx, vy, 1, (cr, cg, cb), kind if kind in BALL_TYPES else "normal", trail)
                b.nid = nid
            elif abs(b.x - x) + abs(b.y - y) > 80:
                b.history.clear()
            b.x, b.y, b.vx, b.vy = float(x), float(y), vx, vy
            b.r = r4 / 4.0
            b.color = (cr, cg, cb)
            b.ghost = bool(fl & 1)
            b.frozen = 1.0 if fl & 2 else 0.0
            new.append(b)
        self.world.balls = new
        self.world.paused = False

    # --- incoming messages ---------------------------------------------------
    def _player_name(self, pid):
        return self.players.get(pid, {}).get("name", "Someone")

    def _handle(self, m):
        t = m.get("t")
        w = self.world
        if t == "welcome":
            self.my_id, self.host, self.limits = m["id"], m["host"], m.get("limits", {})
            self.players = {p["id"]: {"name": p["name"], "color": tuple(p.get("color", (255, 255, 255)))}
                            for p in m.get("players", [])}
            self.cloud = bool(m.get("cloud"))
            w.remote = self.cloud
            w.spawn_lock = not self.host
            if self.creator and not self.cloud:
                self.synced = {}  # we brought the world: push all of it to the room
            else:
                self.send({"t": "need_state"})
            self.status = "Connected"
            self.toast(f"Joined room {self.code}" + (" (host)" if self.host else ""))
            if self.want_cloud and self.creator:
                self.start_cloud()
        elif t == "join":
            self.players[m["id"]] = {"name": m["name"], "color": tuple(m.get("color", (255, 255, 255)))}
            self.toast(f"{m['name']} joined")
        elif t == "leave":
            name = self._player_name(m["id"])
            self.players.pop(m["id"], None)
            self.cursors.pop(m["id"], None)
            self.toast(f"{name} left", (140, 144, 170))
        elif t == "host":
            self.host = m["id"] == self.my_id
            w.spawn_lock = not self.host and not self.cloud
            if self.host:
                self.toast("You are now the host")
        elif t == "need_state":
            if self.host and not self.cloud:
                d = w.to_dict(balls=True)
                d["blocks"] = [block_payload(b) for b in w.blocks if b.alive]
                self.send({"t": "state", "to": m["from"], "d": d})
        elif t == "state":
            if self.creator:
                return
            w.load_dict(m["d"])
            self._mark_all_synced()
            self.scene.select(None)
            self.scene.fit_camera()
            self.scene.resize()
        elif t == "blocks":
            self._apply_blocks(m)
        elif t == "settings":
            self._apply_settings(m.get("d", {}))
        elif t == "spawn":
            if self.host and not self.cloud:
                for row in m.get("b", [])[:500]:
                    x, y, vx, vy, kind = row[:5]
                    color = tuple(row[5]) if len(row) > 5 and isinstance(row[5], list) else None
                    if not w.spawn_ball(x, y, vx, vy, kind=kind if kind in BALL_TYPES else "normal", color=color):
                        break
        elif t == "balls":
            if not self.host and not self.cloud:
                self._apply_balls(m)
        elif t == "boom":
            if self.cloud:
                w.boom_fx(m["x"], m["y"], m.get("p", 12))
            else:
                w.explode(m["x"], m["y"], m.get("r", 170), m.get("p", 15))
        elif t == "clear":
            w.clear_balls()
        elif t == "cur":
            self.cursors[m["from"]] = [m["x"], m["y"], m.get("tool", ""), 0.0]
        elif t == "chat":
            p = self.players.get(m.get("from"), {})
            self.chat.append([p.get("name", "?"), m.get("m", ""), tuple(p.get("color", (255, 255, 255))), 0.0])
        elif t == "cloud":
            if m.get("on"):
                self.cloud = True
                w.remote = True
                w.spawn_lock = False
                self.status = "Cloud physics running"
                self.toast("Cloud physics on: the server is simulating this world")
            else:
                was = self.cloud
                self.cloud = False
                w.remote = False
                w.rebuild_rings()  # recompute which ring each ball is inside
                w.spawn_lock = not self.host
                self.status = "Connected"
                if m.get("reason"):
                    self.toast(("Cloud stopped: " if was else "") + m["reason"][:70], (255, 204, 0))
        elif t == "cloud_stats":
            self.cloud_stats = m
        elif t == "warn":
            self.toast(m.get("m", "Slow down!")[:80], (255, 204, 0))
        elif t == "pong":
            pass

