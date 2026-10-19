"""Double-click launcher: installs pygame if needed, then starts the game."""

import os
import subprocess
import sys

here = os.path.dirname(os.path.abspath(__file__))
os.chdir(here)
sys.path.insert(0, here)

try:
    import pygame  # noqa: F401
except ImportError:
    print("Pygame not found - installing it (one time only)...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--user", "pygame"])
    except (subprocess.CalledProcessError, OSError):
        print("\nCould not install pygame automatically. Run this yourself:\n\n"
              f"    {sys.executable} -m pip install pygame\n")
        input("Press Enter to close...")
        sys.exit(1)
    import site
    import importlib
    importlib.reload(site)

from fun_ball_game.game import main

main()
