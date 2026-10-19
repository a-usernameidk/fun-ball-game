import math
import random
import tkinter as tk


class ControlPanel:

  def __init__(self, root, app_controller):
    self.control_win = tk.Toplevel(root)
    self.control_win.title("Control Panel")
    self.control_win.geometry("360x520")
    self.control_win.config(bg="#1a1a24")
    self.control_win.resizable(True, True)
    self.app = app_controller
    self.create_widgets()

  def show_info(self, title, message):
    info_win = tk.Toplevel(self.control_win)
    info_win.title(f"Info: {title}")
    info_win.geometry("300x150")
    info_win.config(bg="#1a1a24")
    info_win.resizable(False, False)
    tk.Label(
        info_win,
        text=title,
        fg="#00ffcc",
        bg="#1a1a24",
        font=("Arial", 10, "bold"),
    ).pack(pady=(15, 5))
    tk.Label(
        info_win,
        text=message,
        fg="#ffffff",
        bg="#1a1a24",
        font=("Arial", 9),
        wraplength=260,
        justify=tk.CENTER,
    ).pack(padx=15, pady=5)
    tk.Button(
        info_win,
        text="Got it",
        command=info_win.destroy,
        bg="#ff0055",
        fg="#ffffff",
        font=("Arial", 8, "bold"),
        relief=tk.FLAT,
        cursor="hand2",
        width=8,
    ).pack(pady=10)

  def create_widgets(self):
    main_container = tk.Frame(self.control_win, bg="#1a1a24")
    main_container.pack(fill=tk.BOTH, expand=True)
    self.canvas = tk.Canvas(
        main_container, bg="#1a1a24", highlightthickness=0
    )
    self.scrollbar = tk.Scrollbar(
        main_container, orient="vertical", command=self.canvas.yview
    )
    self.scrollable_frame = tk.Frame(self.canvas, bg="#1a1a24")
    self.scrollable_frame.bind(
        "<Configure>",
        lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
    )
    self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
    self.canvas.configure(yscrollcommand=self.scrollbar.set)
    self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    self.canvas.bind_all(
        "<MouseWheel>",
        lambda e: self.canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"),
    )

    top_frame = tk.Frame(self.scrollable_frame, bg="#1a1a24")
    top_frame.pack(fill=tk.X, padx=20, pady=(15, 5))
    self.pause_btn = tk.Button(
        top_frame,
        text="PAUSE",
        command=self.app.toggle_pause,
        bg="#ffcc00",
        fg="#111119",
        font=("Arial", 9, "bold"),
        relief=tk.FLAT,
        cursor="hand2",
        width=12,
    )
    self.pause_btn.pack(side=tk.LEFT)
    self.adv_var = tk.BooleanVar(value=True)
    self.adv_check = tk.Checkbutton(
        top_frame,
        text="Advanced",
        variable=self.adv_var,
        command=self.toggle_advanced_view,
        bg="#1a1a24",
        fg="#ffffff",
        selectcolor="#2e2e42",
        activebackground="#1a1a24",
        activeforeground="#ffffff",
        font=("Arial", 9, "bold"),
    )
    self.adv_check.pack(side=tk.RIGHT)

    self.simple_frame = tk.Frame(self.scrollable_frame, bg="#1a1a24")
    self.simple_frame.pack(fill=tk.X, padx=20, pady=5)

    self.add_labeled_slider(
        self.simple_frame,
        "Circle Rotation Speed",
        0.0,
        0.12,
        0.005,
        "#00ffcc",
        "rotation_speed",
        "Controls how fast the boundary circle spins in place.",
    )
    self.add_labeled_slider(
        self.simple_frame,
        "Opening Hole Size",
        0.2,
        1.5,
        0.05,
        "#ff0055",
        "gap_width",
        "Adjusts the physical width of the exit gaps on the circle.",
    )

    summon_frame = tk.Frame(self.simple_frame, bg="#1a1a24")
    summon_frame.pack(fill=tk.X, pady=(10, 0))
    lbl_f = tk.Frame(summon_frame, bg="#1a1a24")
    lbl_f.pack(anchor="w")
    tk.Label(
        lbl_f,
        text="Spawn Count:",
        fg="#ffffff",
        bg="#1a1a24",
        font=("Arial", 9, "bold"),
    ).pack(side=tk.LEFT)
    self.create_info_btn(
        lbl_f,
        "Spawn Count",
        "Number of balls injected into the circle when you click Summon.",
    )

    spin_action_f = tk.Frame(self.simple_frame, bg="#1a1a24")
    spin_action_f.pack(fill=tk.X, pady=2)
    self.summon_spin = tk.Spinbox(
        spin_action_f,
        from_=1,
        to=1000,
        width=5,
        bg="#2e2e42",
        fg="#ffffff",
        buttonbackground="#2e2e42",
        font=("Arial", 9, "bold"),
    )
    self.summon_spin.delete(0, tk.END)
    self.summon_spin.insert(0, "25")
    self.summon_spin.pack(side=tk.LEFT)
    summon_btn = tk.Button(
        spin_action_f,
        text="Summon",
        command=self.app.manual_summon,
        bg="#ff0055",
        fg="#ffffff",
        font=("Arial", 9, "bold"),
        activebackground="#ff3388",
        activeforeground="#ffffff",
        relief=tk.FLAT,
        cursor="hand2",
    )
    summon_btn.pack(side=tk.RIGHT, padx=5)

    action_frame = tk.Frame(self.simple_frame, bg="#1a1a24")
    action_frame.pack(fill=tk.X, pady=(8, 0))
    kill_btn = tk.Button(
        action_frame,
        text="KILL ALL BALLS",
        command=self.app.kill_all_balls,
        bg="#ff3333",
        fg="#ffffff",
        font=("Arial", 9, "bold"),
        activebackground="#ff6666",
        activeforeground="#ffffff",
        relief=tk.FLAT,
        cursor="hand2",
    )
    kill_btn.pack(fill=tk.X)

    self.adv_frame = tk.Frame(self.scrollable_frame, bg="#1a1a24")
    self.adv_frame.pack(fill=tk.X, padx=20, pady=5)

    self.add_labeled_slider(
        self.adv_frame,
        "Time Speed (Slow / Fast)",
        0.1,
        3.0,
        0.1,
        "#ffcc00",
        "time_speed",
        "Speeds up or slows down the entire simulation physics engine.",
    )
    self.add_labeled_slider(
        self.adv_frame,
        "Number of Exits (Gaps)",
        1,
        5,
        1,
        "#33ff66",
        "num_gaps",
        "Changes how many opening exit gaps are symmetrically placed around the"
        " ring.",
        is_int=True,
    )
    self.add_labeled_slider(
        self.adv_frame,
        "Ball Size",
        3,
        25,
        1,
        "#cc00ff",
        "ball_radius",
        "Adjusts the physical radius and footprint of all simulation balls.",
        is_int=True,
    )
    self.add_labeled_slider(
        self.adv_frame,
        "Bounciness",
        0.5,
        1.2,
        0.05,
        "#00ccff",
        "bounciness",
        "Sets elasticity. Values above 1.0 add energy on impact; values below"
        " 1.0 absorb energy.",
    )

    col_lbl_f = tk.Frame(self.adv_frame, bg="#1a1a24")
    col_lbl_f.pack(anchor="w", pady=(5, 0))
    tk.Label(
        col_lbl_f,
        text="Color Scheme",
        fg="#ffffff",
        bg="#1a1a24",
        font=("Arial", 9, "bold"),
    ).pack(side=tk.LEFT)
    self.create_info_btn(
        col_lbl_f,
        "Color Scheme",
        "Selects the color palette assigned to newly spawned balls.",
    )

    self.color_mode_var = tk.StringVar(value=self.app.color_mode)
    color_menu = tk.OptionMenu(
        self.adv_frame,
        self.color_mode_var,
        "Neon Mix",
        "Fire",
        "Matrix",
        "Pastel",
        "Random",
        command=lambda v: setattr(self.app, "color_mode", v),
    )
    color_menu.config(
        bg="#2e2e42",
        fg="#ffffff",
        activebackground="#3e3e52",
        activeforeground="#ffffff",
        highlightthickness=0,
    )
    color_menu["menu"].config(bg="#2e2e42", fg="#ffffff", activebackground="#ff0055")
    color_menu.pack(fill=tk.X, pady=2)

    toggles_frame = tk.Frame(self.adv_frame, bg="#1a1a24")
    toggles_frame.pack(fill=tk.X, pady=(8, 0))
    self.collision_var = tk.BooleanVar(value=self.app.ball_collision_enabled)
    collision_check = tk.Checkbutton(
        toggles_frame,
        text="Ball Collision",
        variable=self.collision_var,
        command=lambda: setattr(
            self.app, "ball_collision_enabled", self.collision_var.get()
        ),
        bg="#1a1a24",
        fg="#ffffff",
        selectcolor="#2e2e42",
        font=("Arial", 9, "bold"),
    )
    collision_check.pack(anchor="w")

    self.trails_var = tk.BooleanVar(value=self.app.trails_enabled)
    trails_check = tk.Checkbutton(
        toggles_frame,
        text="Motion Trails",
        variable=self.trails_var,
        command=lambda: setattr(
            self.app, "trails_enabled", self.trails_var.get()
        ),
        bg="#1a1a24",
        fg="#ffffff",
        selectcolor="#2e2e42",
        font=("Arial", 9, "bold"),
    )
    trails_check.pack(anchor="w", pady=(2, 0))

    self.hitbox_var = tk.BooleanVar(value=self.app.show_hitboxes)
    hitbox_check = tk.Checkbutton(
        toggles_frame,
        text="Show Hitboxes (Dev)",
        variable=self.hitbox_var,
        command=lambda: setattr(
            self.app, "show_hitboxes", self.hitbox_var.get()
        ),
        bg="#1a1a24",
        fg="#ffff00",
        selectcolor="#2e2e42",
        font=("Arial", 9, "bold"),
    )
    hitbox_check.pack(anchor="w", pady=(2, 0))

    limit_frame = tk.Frame(self.adv_frame, bg="#1a1a24")
    limit_frame.pack(fill=tk.X, pady=(10, 5))
    lim_lbl_f = tk.Frame(limit_frame, bg="#1a1a24")
    lim_lbl_f.pack(anchor="w")
    tk.Label(
        lim_lbl_f,
        text="Max Ball Limit:",
        fg="#ffffff",
        bg="#1a1a24",
        font=("Arial", 9, "bold"),
    ).pack(side=tk.LEFT)
    self.create_info_btn(
        lim_lbl_f,
        "Max Ball Limit",
        "Sets the maximum allowed ball count before the selected limit action"
        " triggers.",
    )

    self.limit_spin = tk.Spinbox(
        limit_frame,
        from_=10,
        to=5000,
        width=6,
        bg="#2e2e42",
        fg="#ffffff",
        buttonbackground="#2e2e42",
        font=("Arial", 9, "bold"),
    )
    self.limit_spin.delete(0, tk.END)
    self.limit_spin.insert(0, str(self.app.max_ball_limit))
    self.limit_spin.pack(anchor="w", pady=2)

    act_lbl_f = tk.Frame(limit_frame, bg="#1a1a24")
    act_lbl_f.pack(anchor="w", pady=(5, 0))
    tk.Label(
        act_lbl_f,
        text="When Limit Reached:",
        fg="#ffffff",
        bg="#1a1a24",
        font=("Arial", 9, "bold"),
    ).pack(side=tk.LEFT)
    self.create_info_btn(
        act_lbl_f,
        "Limit Action",
        "Choose what the simulator does when the maximum ball limit is"
        " reached:\n- Pause Simulation: Auto-pauses.\n- Delete Oldest: Trims"
        " excess old balls.\n- Stop Spawning: Blocks new entries.",
    )

    self.limit_action_var = tk.StringVar(value=self.app.limit_action)
    action_menu = tk.OptionMenu(
        limit_frame,
        self.limit_action_var,
        "Pause Simulation",
        "Delete Oldest",
        "Stop Spawning",
        command=lambda v: setattr(self.app, "limit_action", v),
    )
    action_menu.config(
        bg="#2e2e42",
        fg="#ffffff",
        activebackground="#3e3e52",
        activeforeground="#ffffff",
        highlightthickness=0,
    )
    action_menu["menu"].config(
        bg="#2e2e42", fg="#ffffff", activebackground="#ff0055"
    )
    action_menu.pack(fill=tk.X, pady=2)

  def add_labeled_slider(
      self,
      parent,
      text,
      f_val,
      t_val,
      res,
      fg_color,
      attr_name,
      info_text,
      is_int=False,
  ):
    f = tk.Frame(parent, bg="#1a1a24")
    f.pack(fill=tk.X, pady=(5, 0))
    header_f = tk.Frame(f, bg="#1a1a24")
    header_f.pack(fill=tk.X)
    tk.Label(
        header_f,
        text=text,
        fg="#ffffff",
        bg="#1a1a24",
        font=("Arial", 9, "bold"),
    ).pack(side=tk.LEFT)
    self.create_info_btn(header_f, text, info_text)
    slider = tk.Scale(
        f,
        from_=f_val,
        to=t_val,
        resolution=res,
        orient=tk.HORIZONTAL,
        bg="#1a1a24",
        fg=fg_color,
        highlightbackground="#1a1a24",
        troughcolor="#2e2e42",
        command=lambda v: setattr(
            self.app, attr_name, int(v) if is_int else float(v)
        ),
    )
    slider.set(getattr(self.app, attr_name))
    slider.pack(fill=tk.X, pady=2)

  def create_info_btn(self, parent, title, desc):
    btn = tk.Button(
        parent,
        text="i",
        command=lambda: self.show_info(title, desc),
        bg="#2e2e42",
        fg="#00ffcc",
        font=("Arial", 7, "bold"),
        relief=tk.FLAT,
        cursor="hand2",
        width=2,
    )
    btn.pack(side=tk.LEFT, padx=6)

  def toggle_advanced_view(self):
    if self.adv_var.get():
      self.adv_frame.pack(fill=tk.X, padx=20, pady=5)
    else:
      self.adv_frame.pack_forget()