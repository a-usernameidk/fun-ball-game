import os
import subprocess
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(current_dir)

if sys.platform == "win32":
  # Opens a persistent Windows Command Prompt window in the correct directory
  subprocess.Popen(
      f'start cmd.exe /k "cd /d "{current_dir}" && python main.py"', shell=True
  )
elif sys.platform == "darwin":
  # Opens macOS Terminal
  subprocess.Popen([
      "osascript",
      "-e",
      f'tell application "Terminal" to do script "cd {current_dir} && python3 main.py"',
  ])
else:
  # Opens Linux terminal (gnome-terminal or xterm fallback)
  try:
    subprocess.Popen([
        "gnome-terminal",
        "--",
        "bash",
        "-c",
        f"cd {current_dir} && python3 main.py; exec bash",
    ])
  except FileNotFoundError:
    subprocess.Popen([
        "xterm",
        "-hold",
        "-e",
        f"cd {current_dir} && python3 main.py",
    ])