"""Saved worlds: each one is a named sandbox with its own blocks, settings and stats."""

import re
import shutil
import time
import uuid

from .storage import SAVE_DIR, read_json, write_json

WORLDS_DIR = SAVE_DIR / "worlds"


def world_path(wid):
    return WORLDS_DIR / f"{wid}.json"


def thumb_path(wid):
    return WORLDS_DIR / f"{wid}.png"


def new_id(name):
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:24] or "world"
    return f"{slug}-{uuid.uuid4().hex[:6]}"


def list_worlds():
    """Every saved world's metadata, most recently played first."""
    out = []
    if not WORLDS_DIR.exists():
        return out
    for p in WORLDS_DIR.glob("*.json"):
        data = read_json(p)
        if not data or "meta" not in data:
            continue
        meta = dict(data["meta"])
        meta["id"] = p.stem
        meta["balls_saved"] = 0
        meta["blocks"] = len(data.get("blocks", []))
        meta["coins"] = data.get("coins", 0)
        meta["escapes"] = data.get("stats", {}).get("escapes", 0)
        out.append(meta)
    out.sort(key=lambda m: m.get("last_played", 0), reverse=True)
    return out


def make_meta(name, theme):
    now = time.time()
    return {"name": name, "theme": theme, "created": now, "last_played": now, "playtime": 0.0}


def save_world(wid, data):
    return write_json(world_path(wid), data)


def load_world(wid):
    return read_json(world_path(wid))


def delete_world(wid):
    for p in (world_path(wid), thumb_path(wid)):
        try:
            p.unlink()
        except OSError:
            pass


def rename_world(wid, name):
    data = load_world(wid)
    if data:
        data["meta"]["name"] = name
        save_world(wid, data)


def duplicate_world(wid):
    data = load_world(wid)
    if not data:
        return None
    name = data["meta"]["name"] + " (copy)"
    nid = new_id(name)
    data["meta"] = dict(data["meta"], name=name, created=time.time(), last_played=time.time())
    save_world(nid, data)
    if thumb_path(wid).exists():
        try:
            shutil.copy(thumb_path(wid), thumb_path(nid))
        except OSError:
            pass
    return nid


def migrate_autosave():
    """Turn the old single autosave (v4.0) into a world so nobody loses their stuff."""
    old = SAVE_DIR / "autosave.json"
    if not old.exists() or list_worlds():
        return
    data = read_json(old)
    if data:
        data["meta"] = make_meta("My Sandbox", data.get("settings", {}).get("theme", "Midnight"))
        save_world(new_id("My Sandbox"), data)
    try:
        old.rename(old.with_suffix(".json.old"))
    except OSError:
        pass


def fmt_time(t):
    return time.strftime("%b %d, %H:%M", time.localtime(t)) if t else "never"


def fmt_playtime(sec):
    m = int(sec // 60)
    if m < 1:
        return "under a minute"
    if m < 60:
        return f"{m} min"
    return f"{m // 60}h {m % 60:02d}m"
