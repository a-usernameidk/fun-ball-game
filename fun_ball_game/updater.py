"""Auto-update: checks GitHub for a newer version of the game and installs it.

How it works:
  1. Read __version__ from fun_ball_game/__init__.py on the main branch.
  2. If it's newer than ours, download the main branch as a zip.
  3. Unpack it to a temp folder, check it looks like the game, then copy it over this
     game folder (your saves/ folder is never touched). The old code is kept in
     .update_backup/ and put back if anything goes wrong.
  4. Restart the game to run the new version.

To publish an update: bump __version__ in fun_ball_game/__init__.py and merge to main.
"""

import io
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.request
import zipfile
from pathlib import Path

from . import __version__

REPO = "a-usernameidk/fun-ball-game"
BRANCH = "main"
VERSION_URL = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/fun_ball_game/__init__.py"
ZIP_URL = f"https://codeload.github.com/{REPO}/zip/refs/heads/{BRANCH}"
GAME_DIR = Path(__file__).resolve().parent.parent
SKIP = {"saves", ".git", ".update_backup", "__pycache__"}
MAX_ZIP_BYTES = 50 * 1024 * 1024


def parse_version(text):
    for line in text.splitlines():
        if line.startswith("__version__"):
            v = line.split("=", 1)[1].strip().strip("\"'")
            return tuple(int(p) for p in v.split(".") if p.isdigit())
    return ()


def version_str(v):
    return ".".join(str(p) for p in v)


def _get(url, limit=MAX_ZIP_BYTES):
    req = urllib.request.Request(url, headers={"User-Agent": f"FunBallGame/{__version__}"})
    with urllib.request.urlopen(req, timeout=20) as res:
        data = res.read(limit + 1)
    if len(data) > limit:
        raise ValueError("download too big")
    return data


class Updater:
    """state: idle, checking, up_to_date, available, installing, installed, dev, error"""

    def __init__(self):
        self.current = parse_version(f'__version__ = "{__version__}"')
        self.latest = None
        self.state = "idle"
        self.message = ""
        self._lock = threading.Lock()

    @property
    def is_dev_checkout(self):
        # Running from a git clone: let git handle updates instead of overwriting files.
        return (GAME_DIR / ".git").exists()

    def check(self, install=False):
        with self._lock:
            if self.state in ("checking", "installing", "installed"):
                return
            if self.is_dev_checkout:
                self.state, self.message = "dev", "Running from a git copy, so use git pull to update."
                return
            self.state, self.message = "checking", "Checking for updates..."
        threading.Thread(target=self._check, args=(install,), daemon=True).start()

    def _check(self, install):
        try:
            self.latest = parse_version(_get(VERSION_URL, 64 * 1024).decode("utf-8", "replace"))
        except Exception as e:
            self.state, self.message = "error", f"Couldn't check for updates ({type(e).__name__})"
            return
        if not self.latest or self.latest <= self.current:
            self.state, self.message = "up_to_date", f"You have the latest version (v{__version__})."
            return
        self.state = "available"
        self.message = f"Version {version_str(self.latest)} is out! (you have v{__version__})"
        if install:
            self._install()

    def install(self):
        with self._lock:
            if self.state != "available":
                return
            self.state = "installing"
        threading.Thread(target=self._install, daemon=True).start()

    def _install(self):
        self.state, self.message = "installing", f"Downloading v{version_str(self.latest)}..."
        backup = GAME_DIR / ".update_backup"
        copied = []
        try:
            data = _get(ZIP_URL)
            with tempfile.TemporaryDirectory() as tmp:
                with zipfile.ZipFile(io.BytesIO(data)) as zf:
                    for name in zf.namelist():  # refuse anything that escapes the folder
                        if name.startswith("/") or ".." in Path(name).parts:
                            raise ValueError("bad file in update")
                    zf.extractall(tmp)
                roots = [p for p in Path(tmp).iterdir() if p.is_dir()]
                if len(roots) != 1 or not (roots[0] / "fun_ball_game" / "__init__.py").exists():
                    raise ValueError("the download doesn't look like the game")
                new = roots[0]
                if parse_version((new / "fun_ball_game" / "__init__.py").read_text("utf-8")) <= self.current:
                    raise ValueError("the download isn't newer")
                # back up the current code, then copy the new files over it
                if backup.exists():
                    shutil.rmtree(backup)
                backup.mkdir()
                for item in new.iterdir():
                    if item.name in SKIP:
                        continue
                    dest = GAME_DIR / item.name
                    if dest.exists():
                        shutil.move(str(dest), str(backup / item.name))
                    copied.append(item.name)
                    if item.is_dir():
                        shutil.copytree(item, dest, ignore=shutil.ignore_patterns("__pycache__"))
                    else:
                        shutil.copy2(item, dest)
        except Exception as e:
            # put the old files back
            for name in copied:
                dest = GAME_DIR / name
                if dest.is_dir():
                    shutil.rmtree(dest, ignore_errors=True)
                elif dest.exists():
                    dest.unlink()
                if (backup / name).exists():
                    shutil.move(str(backup / name), str(dest))
            self.state, self.message = "error", f"Update failed, nothing was changed ({e})"
            return
        self.state = "installed"
        self.message = f"Updated to v{version_str(self.latest)}! Restart the game to use it."


def restart():
    """Start a fresh copy of the game and let the caller quit this one."""
    script = GAME_DIR / "main.py"
    subprocess.Popen([sys.executable, str(script)], cwd=str(GAME_DIR),
                     close_fds=True, env=dict(os.environ))
