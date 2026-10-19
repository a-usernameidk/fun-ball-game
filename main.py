"""Start the game:  python main.py"""

import sys

try:
    import pygame  # noqa: F401
except ImportError:
    print("Pygame is not installed. Install it with:\n\n    pip install pygame\n\n"
          "(or just double-click run.py, which installs it for you)")
    sys.exit(1)

from fun_ball_game.game import main

if __name__ == "__main__":
    main()
