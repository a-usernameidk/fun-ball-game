import math
import random
import tkinter as tk
from physics import update_ball_physics
from ui import ControlPanel


class MainMenu:

  def __init__(self, root):
    self.root = root
    self.root.title("Fun Ball Game - Menu")
    self.root.geometry("600x600")

    self.canvas = tk.Canvas(root, bg="#111119", highlightthickness=0)
    self.canvas.pack(fill=tk.BOTH, expand=True)

    # Background decorative bouncing balls
    self.menu_balls = []
    for _ in range(30):
      self.menu_balls.append({
          "x": random.uniform(50, 550),
          "y": random.uniform(50, 550),
          "vx": random.uniform(-2.5, 2.5),
          "vy": random.uniform(-2.5, 2.5),
          "radius": random.randint(6, 14),
          "color": random.choice([
              "#00ffcc",
              "#ff0055",
              "#ffcc00",
              "#cc00ff",
              "#00ccff",
              "#33ff66",
          ]),
      })

    # Title at the top
    self.canvas.create_text(
        300,
        120,
        text="Fun Ball Game",
        fill="#00ffcc",
        font=("Arial", 36, "bold"),
    )

    # Menu Buttons Container
    btn_frame = tk.Frame(root, bg="#111119")
    btn_frame.place(relx=0.5, rely=0.55, anchor=tk.CENTER)

    play_btn = tk.Button(
        btn_frame,
        text="PLAY",
        command=self.start_game,
        bg="#00ffcc",
        fg="#111119",
        font=("Arial", 14, "bold"),
        width=16,
        relief=tk.FLAT,
        cursor="hand2",
    )
    play_btn.pack(pady=12)

    settings_btn = tk.Button(
        btn_frame,
        text="SETTINGS",
        command=self.open_settings,
        bg="#ff0055",
        fg="#ffffff",
        font=("Arial", 14, "bold"),
        width=16,
        relief=tk.FLAT,
        cursor="hand2",
    )
    settings_btn.pack(pady=12)

    self.animate_menu()

  def animate_menu(self):
    self.canvas.delete("menu_ball")
    for b in self.menu_balls:
      b["x"] += b["vx"]
      b["y"] += b["vy"]

      # Bounce off window edges
      if b["x"] - b["radius"] < 0 or b["x"] + b["radius"] > 600:
        b["vx"] *= -1
      if b["y"] - b["radius"] < 0 or b["y"] + b["radius"] > 600:
        b["vy"] *= -1

      r = b["radius"]
      self.canvas.create_oval(
          b["x"] - r,
          b["y"] - r,
          b["x"] + r,
          b["y"] + r,
          fill=b["color"],
          outline="",
          tags="menu_ball",
      )

    # Keep title visible above background balls
    self.canvas.tag_raise("all")
    self.root.after(20, self.animate_menu)

  def start_game(self):
    for widget in self.root.winfo_children():
      widget.destroy()
    SpinningCircleSimulator(self.root)

  def open_settings(self):
    settings_win = tk.Toplevel(self.root)
    settings_win.title("Settings Info")
    settings_win.geometry("320x220")
    settings_win.config(bg="#1a1a24")
    settings_win.resizable(False, False)

    tk.Label(
        settings_win,
        text="Game Settings",
        fg="#00ffcc",
        bg="#1a1a24",
        font=("Arial", 12, "bold"),
    ).pack(pady=(20, 10))

    tk.Label(
        settings_win,
        text=(
            "Detailed physics adjustments, color themes, and controls are"
            " available via the Control Panel window once you click PLAY!"
        ),
        fg="#ffffff",
        bg="#1a1a24",
        font=("Arial", 9),
        wraplength=270,
        justify=tk.CENTER,
    ).pack(pady=5)

    tk.Button(
        settings_win,
        text="Got it",
        command=settings_win.destroy,
        bg="#ff0055",
        fg="#ffffff",
        font=("Arial", 9, "bold"),
        relief=tk.FLAT,
        cursor="hand2",
        width=10,
    ).pack(pady=15)


class SpinningCircleSimulator:

  def __init__(self, root):
    self.root = root
    self.root.title("Ball in a Spinning Circle")
    self.root.geometry("600x600")
    self.canvas = tk.Canvas(root, bg="#111119", highlightthickness=0)
    self.canvas.pack(fill=tk.BOTH, expand=True)
    self.cx, self.cy = 300, 300
    self.radius = 180
    self.gap_angle = 0.0
    self.rotation_speed = 0.035
    self.time_speed = 1.0
    self.gap_width = 0.65
    self.num_gaps = 1
    self.ball_radius = 9
    self.bounciness = 1.03
    self.friction = 1.0
    self.ball_collision_enabled = True
    self.trails_enabled = True
    self.show_hitboxes = False
    self.color_mode = "Neon Mix"
    self.max_ball_limit = 500
    self.limit_action = "Pause Simulation"
    self.is_paused = False
    self.balls = []
    self.gravity_wells = []

    # Left-click = Repulsive, Right-click = Attractive
    self.canvas.bind("<Button-1>", self.spawn_repulsive_well)
    self.canvas.bind("<Button-3>", self.spawn_attractive_well)

    self.spawn_ball(self.cx, self.cy)
    self.control_panel = ControlPanel(root, self)
    self.update_physics()

  def toggle_pause(self):
    self.is_paused = not self.is_paused
    new_text = "RESUME" if self.is_paused else "PAUSE"
    new_bg = "#00ffcc" if self.is_paused else "#ffcc00"
    self.control_panel.pause_btn.config(text=new_text, bg=new_bg)

  def spawn_repulsive_well(self, event):
    self.gravity_wells.append(
        {"x": event.x, "y": event.y, "strength": 0.8, "type": "repulsive"}
    )
    if len(self.gravity_wells) > 3:
      self.gravity_wells.pop(0)

  def spawn_attractive_well(self, event):
    self.gravity_wells.append(
        {"x": event.x, "y": event.y, "strength": 0.8, "type": "attractive"}
    )
    if len(self.gravity_wells) > 3:
      self.gravity_wells.pop(0)

  def manual_summon(self):
    try:
      count = int(self.control_panel.summon_spin.get())
    except ValueError:
      count = 10
    if self.limit_action == "Stop Spawning":
      space_left = self.max_ball_limit - len(self.balls)
      if space_left <= 0:
        return
      count = min(count, space_left)
    for _ in range(count):
      self.spawn_ball(self.cx, self.cy)

  def kill_all_balls(self):
    self.balls.clear()
    self.gravity_wells.clear()

  def spawn_ball(self, x, y):
    if (
        len(self.balls) >= self.max_ball_limit
        and self.limit_action == "Stop Spawning"
    ):
      return
    angle = random.uniform(0, 2 * math.pi)
    speed = random.uniform(3, 6)
    colors = {
        "Fire": ["#ff0000", "#ff6600", "#ffcc00", "#ffff00"],
        "Matrix": ["#00ff00", "#00cc66", "#33ff99", "#006622"],
        "Pastel": ["#ff9999", "#99ff99", "#9999ff", "#ffff99"],
    }
    if self.color_mode in colors:
      color = random.choice(colors[self.color_mode])
    elif self.color_mode == "Random":
      color = (
          f"#{random.randint(50, 255):02x}{random.randint(50, 255):02x}"
          f"{random.randint(50, 255):02x}"
      )
    else:
      color = random.choice([
          "#00ffcc",
          "#ff0055",
          "#ffcc00",
          "#cc00ff",
          "#00ccff",
          "#33ff66",
      ])
    self.balls.append({
        "x": x,
        "y": y,
        "vx": math.cos(angle) * speed,
        "vy": math.sin(angle) * speed,
        "radius": self.ball_radius,
        "color": color,
        "escaped": False,
        "history": [],
    })

  def update_physics(self):
    if not self.is_paused:
      dt = self.time_speed
      self.gap_angle = (self.gap_angle + self.rotation_speed * dt) % (
          2 * math.pi
      )
      for b in self.balls:
        b["radius"] = self.ball_radius
      try:
        self.max_ball_limit = int(self.control_panel.limit_spin.get())
      except ValueError:
        pass
      if len(self.balls) >= self.max_ball_limit:
        if self.limit_action == "Pause Simulation":
          self.is_paused = True
          self.control_panel.pause_btn.config(text="RESUME", bg="#00ffcc")
        elif self.limit_action == "Delete Oldest":
          self.balls = self.balls[-self.max_ball_limit :]
      self.balls, new_balls_to_add = update_ball_physics(
          self.balls,
          self.cx,
          self.cy,
          self.radius,
          self.gap_angle,
          self.gap_width,
          self.num_gaps,
          dt,
          self.gravity_wells,
          self.friction,
          self.bounciness,
          self.ball_collision_enabled,
          self.trails_enabled,
      )
      if self.limit_action == "Stop Spawning":
        space_left = self.max_ball_limit - len(self.balls)
        new_balls_to_add = max(0, min(new_balls_to_add, space_left))
      for _ in range(new_balls_to_add):
        self.spawn_ball(self.cx, self.cy)
    self.draw()
    self.root.after(16, self.update_physics)

  def draw(self):
    self.canvas.delete("all")
    for gw in self.gravity_wells:
      outline_color = (
          "#ff3355" if gw.get("type") == "repulsive" else "#00ffcc"
      )
      self.canvas.create_oval(
          gw["x"] - 15,
          gw["y"] - 15,
          gw["x"] + 15,
          gw["y"] + 15,
          outline=outline_color,
          width=2,
          dash=(4, 4),
      )
    if self.trails_enabled:
      for b in self.balls:
        if len(b["history"]) > 1:
          coords = [pt for sublist in b["history"] for pt in sublist]
          if len(coords) >= 4:
            self.canvas.create_line(
                coords, fill=b["color"], width=max(1, b["radius"] // 2)
            )
    self.canvas.create_oval(
        self.cx - self.radius,
        self.cy - self.radius,
        self.cx + self.radius,
        self.cy + self.radius,
        outline="#ff3388",
        width=4,
    )
    for g in range(self.num_gaps):
      g_offset = (self.gap_angle + g * (2 * math.pi / self.num_gaps)) % (
          2 * math.pi
      )
      start_deg = math.degrees(-g_offset - self.gap_width)
      extent_deg = math.degrees(self.gap_width)
      self.canvas.create_arc(
          self.cx - self.radius - 3,
          self.cy - self.radius - 3,
          self.cx + self.radius + 3,
          self.cy + self.radius + 3,
          start=start_deg,
          extent=extent_deg,
          style=tk.PIESLICE,
          fill="#111119",
          outline="#111119",
      )
    for b in self.balls:
      r = b["radius"]
      self.canvas.create_oval(
          b["x"] - r,
          b["y"] - r,
          b["x"] + r,
          b["y"] + r,
          fill=b["color"],
          outline="#ffffff" if not b["escaped"] else "",
      )
    if self.show_hitboxes:
      for b in self.balls:
        r = b["radius"]
        self.canvas.create_oval(
            b["x"] - r, b["y"] - r, b["x"] + r, b["y"] + r, outline="#ffff00"
        )
        self.canvas.create_rectangle(
            b["x"] - 1, b["y"] - 1, b["x"] + 1, b["y"] + 1, fill="#ffff00"
        )
      for g in range(self.num_gaps):
        g_offset = (self.gap_angle + g * (2 * math.pi / self.num_gaps)) % (
            2 * math.pi
        )
        hx = self.cx + self.radius * math.cos(g_offset)
        hy = self.cy + self.radius * math.sin(g_offset)
        self.canvas.create_line(
            self.cx, self.cy, hx, hy, fill="#ffff00", dash=(2, 2)
        )


if __name__ == "__main__":
  root = tk.Tk()
  app = MainMenu(root)
  root.mainloop()