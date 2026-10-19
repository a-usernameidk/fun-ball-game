"""Double-click launcher: installs pygame if needed, then starts the game."""

import os
import subprocess
import sys

here = os.path.dirname(os.path.abspath(__file__))
os.chdir(here)
sys.path.insert(0, here)


def install(package):
    print(f"Installing {package} (one time only)...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--user", package])
        return True
    except (subprocess.CalledProcessError, OSError):
        return False


try:
    import pygame  # noqa: F401
except ImportError:
    if not install("pygame"):
        print("\nCould not install pygame automatically. Run this yourself:\n\n"
              f"    {sys.executable} -m pip install pygame\n")
        input("Press Enter to close...")
        sys.exit(1)
    import site
    import importlib
    importlib.reload(site)

try:
    import websocket  # noqa: F401  (multiplayer / cloud physics)
except ImportError:
    if install("websocket-client"):
        import site
        import importlib
        importlib.reload(site)
    else:
        print("Couldn't install websocket-client, so multiplayer will be off. Everything else works.")

from fun_ball_game.game import main

main()
