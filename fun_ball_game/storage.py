"""Where save files live, plus tiny JSON helpers."""

import json
import os
from pathlib import Path

SAVE_DIR = Path(os.environ.get("FUN_BALL_SAVES", Path(__file__).resolve().parent.parent / "saves"))


def read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def write_json(path, data):
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1)
        os.replace(tmp, path)  # never leave a half-written save behind
        return True
    except OSError:
        return False
