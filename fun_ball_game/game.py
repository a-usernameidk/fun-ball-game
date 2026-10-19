"""The application: main menu, sandbox scene, editor tools and UI panels."""

import math
import random
import time
from pathlib import Path

import pygame

from . import blocks as B
from .achievements import ACHIEVEMENTS, Achievements
from .audio import Audio
from .balls import BALL_ORDER, BALL_TYPES
from .presets import PRESETS
from .render import Renderer
from . import net as N
from . import __version__
from . import updater as U
from . import worlds as W
from .settings import (ACCENT, ACCENT2, BG, BORDER, COLOR_SCHEMES, DANGER, FPS_OPTIONS,
                       LIMIT_ACTIONS, PANEL, PANEL_LIGHT, TEXT, TEXT_DIM, THEME_ORDER, THEMES, WARN,
                       Settings, theme)
from .ui import (UI, Button, Choice, Grid, Header, Label, NumberInput, Row, ScrollList, Slider,
                 Spacer, Tabs, TextInput, Tile, Toggle, panel, wrap)
from .util import Camera, TAU, clamp, mix, rotate
from .storage import SAVE_DIR, read_json as _read_json, write_json as _write_json
from .world import World

TOP_H = 54
LEFT_W = 248
RIGHT_W = 296
SPEEDS = [0.1, 0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0]


class _Mute:
    def play(self, *a, **k):
        pass

    def tick(self, *a):
        pass


# --------------------------------------------------------------------------
# tool icons
# --------------------------------------------------------------------------
def _icon_select(surf, r):
    x, y, s = r.x + r.w * 0.3, r.y + r.h * 0.15, min(r.w, r.h) * 0.7
    pts = [(0, 0), (0, 1), (0.28, 0.75), (0.45, 1.05), (0.58, 0.98), (0.42, 0.7), (0.75, 0.7)]
    pygame.draw.polygon(surf, (240, 240, 255), [(x + px * s, y + py * s) for px, py in pts])


def _icon_eraser(surf, r):
    c = r.center
    s = min(r.w, r.h) * 0.32
    pts = [rotate(px, py, -0.6) for px, py in ((-s, -s * 0.6), (s, -s * 0.6), (s, s * 0.6), (-s, s * 0.6))]
    pygame.draw.polygon(surf, (255, 110, 150), [(c[0] + px, c[1] + py) for px, py in pts])
    pts2 = [rotate(px, py, -0.6) for px, py in ((-s, -s * 0.6), (-s * 0.2, -s * 0.6), (-s * 0.2, s * 0.6), (-s, s * 0.6))]
    pygame.draw.polygon(surf, (240, 240, 250), [(c[0] + px, c[1] + py) for px, py in pts2])


def _icon_spawn(surf, r):
    c = r.center
    s = min(r.w, r.h) * 0.3
    pygame.draw.circle(surf, ACCENT, c, s)
    pygame.draw.line(surf, BG, (c[0] - s * 0.5, c[1]), (c[0] + s * 0.5, c[1]), 3)
    pygame.draw.line(surf, BG, (c[0], c[1] - s * 0.5), (c[0], c[1] + s * 0.5), 3)


def _icon_grab(surf, r):
    c = r.center
    s = min(r.w, r.h) * 0.3
    pygame.draw.circle(surf, (255, 204, 0), (c[0] - s * 0.3, c[1] + s * 0.2), s * 0.7)
    for i in range(4):
        a = -2.4 + i * 0.45
        pygame.draw.line(surf, (240, 240, 255), (c[0] + math.cos(a) * s * 0.5, c[1] + math.sin(a) * s * 0.5),
                         (c[0] + math.cos(a) * s * 1.3, c[1] + math.sin(a) * s * 1.3), 3)


def _icon_explode(surf, r):
    c = r.center
    s = min(r.w, r.h) * 0.4
    pts = []
    for i in range(16):
        k = s if i % 2 == 0 else s * 0.45
        a = i * TAU / 16
        pts.append((c[0] + math.cos(a) * k, c[1] + math.sin(a) * k))
    pygame.draw.polygon(surf, (255, 140, 30), pts)
    pygame.draw.circle(surf, (255, 240, 160), c, s * 0.3)


def _icon_rings(color, inward):
    def f(surf, r):
        c = r.center
        s = min(r.w, r.h) * 0.42
        for i in range(3):
            pygame.draw.circle(surf, mix(BG, color, 1 - i * 0.28), c, s * (0.35 + i * 0.3), 2)
        pygame.draw.circle(surf, color, c, 4)
    return f


TOOLS = [
    ("select", "Select / Move", "Click a block to select it, drag to move it. Edit it in the Inspect tab. "
     "Drag empty space to pan.", _icon_select),
    ("spawn", "Spawn Balls", "Click or hold to spray balls of the chosen type (Balls tab).", _icon_spawn),
    ("grab", "Grab & Throw", "Grab balls with the mouse and fling them.", _icon_grab),
    ("eraser", "Eraser", "Drag over blocks and balls to delete them.", _icon_eraser),
    ("explode", "Explosion", "Click to blow everything up. Breaks glass, bricks and sets off TNT.", _icon_explode),
    ("attract", "Attract", "Hold to pull balls towards the mouse.", _icon_rings((0, 255, 204), True)),
    ("repel", "Repel", "Hold to push balls away from the mouse.", _icon_rings((255, 51, 85), False)),
]
TOOL_INFO = {k: (n, d) for k, n, d, _ in TOOLS}

ICON_OVERRIDES = {
    "laser": dict(length=34, angle=-0.6), "mover": dict(travel=18), "cannon": dict(angle=-0.6),
    "spinner": dict(angle=-0.5), "booster": dict(angle=-0.5), "wind": dict(angle=0.0),
    "conveyor": dict(w=150), "spike": dict(w=110),
}

HELP_LINES = [
    ("MOUSE", None),
    ("Left click", "Use the selected tool / place the selected block"),
    ("Left drag (blocks)", "Draw walls at any length & angle, drag fields to size them"),
    ("Right click", "Delete the block under the mouse, or hold to attract balls"),
    ("Middle drag / WASD", "Pan the camera (arrow keys work too)"),
    ("Mouse wheel", "Zoom   (Shift+wheel rotates the block being placed)"),
    ("KEYBOARD", None),
    ("Space  /  N", "Pause or resume  /  step one frame"),
    ("Q  /  E", "Rotate the selected or ghost block by 15 degrees"),
    ("Delete  /  Ctrl+D", "Delete  /  duplicate the selected block"),
    ("Ctrl+Z", "Undo"),
    ("Ctrl+S  /  Ctrl+L", "Save the world  /  quick load (slot 1)"),
    ("B  /  C", "Spawn a burst of balls in the centre  /  clear all balls"),
    ("Shift+click  /  R", "Burst of balls at the mouse  /  ball rain on/off"),
    ("1 - 9", "Pick a tile in the current toolbox tab"),
    ("+  /  -", "Simulation speed"),
    ("G", "Snap to grid"),
    ("Tab  /  Home", "Hide the UI  /  reset the camera"),
    ("F11  /  H", "Fullscreen  /  this help"),
    ("O", "Settings (FPS limit, ball limit, graphics, sound)"),
    ("Esc", "Deselect, or go back to the menu"),
]


# ==========================================================================
# App
# ==========================================================================
class App:
    def __init__(self, size=(1440, 880)):
        pygame.init()
        pygame.display.set_caption("Fun Ball Game")
        self.screen = pygame.display.set_mode(size, pygame.RESIZABLE)
        self.fullscreen = False
        self.windowed_size = size
        self.clock = pygame.time.Clock()
        self.settings = Settings()
        self.profile = _read_json(SAVE_DIR / "profile.json") or {}
        self.settings.load_dict(self.profile.get("prefs", {}))
        if not self.settings.player_name:
            self.settings.player_name = f"Player{random.randint(100, 999)}"
        self.overlay = None
        self.audio = Audio(self.settings)
        self.ui = UI()
        self.ui.sound = self.audio.play
        self.achievements = Achievements(self.profile.get("achievements"))
        W.migrate_autosave()
        self.updater = U.Updater()
        self._update_told = False
        self.updater.check(install=self.settings.auto_update)
        self.running = True
        self.scene = MenuScene(self)

    def save_profile(self):
        self.profile.update(prefs=self.settings.prefs(),
                            achievements=sorted(self.achievements.unlocked))
        _write_json(SAVE_DIR / "profile.json", self.profile)

    def toggle_fullscreen(self):
        try:
            if self.fullscreen:
                self.screen = pygame.display.set_mode(self.windowed_size, pygame.RESIZABLE)
            else:
                self.windowed_size = self.screen.get_size()
                self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
            self.fullscreen = not self.fullscreen
        except pygame.error:
            pass
        self.scene.resize()
        if self.overlay:
            self.overlay.build()

    def set_scene(self, scene):
        self.scene = scene

    def open_settings(self):
        self.overlay = SettingsOverlay(self)

    def close_settings(self):
        if self.ui.focus:
            self.ui.focus.commit(self.ui)
        self.overlay = None
        self.save_profile()
        if isinstance(self.scene, SandboxScene):
            self.scene.resize()

    def api(self):
        return N.Api(N.server_url(self.settings))

    def quit(self):
        net = getattr(self.scene, "net", None)
        if net:
            net.close()
        if isinstance(self.scene, SandboxScene):
            self.scene.autosave()
        self.save_profile()
        self.running = False

    def restart_for_update(self):
        self.quit()
        U.restart()

    def frame(self, events=None):
        dt = self.clock.tick(self.settings.fps_limit) / 1000.0  # fps_limit 0 = uncapped
        frames = min(dt * 60.0, 3.0)
        for e in (pygame.event.get() if events is None else events):
            if e.type == pygame.QUIT:
                self.quit()
                return
            if e.type == pygame.VIDEORESIZE and not self.fullscreen:
                self.screen = pygame.display.set_mode((max(900, e.w), max(600, e.h)), pygame.RESIZABLE)
                self.scene.resize()
                continue
            if e.type == pygame.KEYDOWN and e.key == pygame.K_F11:
                self.toggle_fullscreen()
                continue
            if e.type == pygame.MOUSEMOTION:
                self.ui.mouse = e.pos
            if e.type == pygame.MOUSEBUTTONUP and self.ui.active:
                self.ui.active = None
                continue
            if e.type == pygame.MOUSEMOTION and self.ui.active:
                self.ui.active.drag(e.pos, self.ui)
                continue
            focus = self.ui.focus
            if focus is not None:
                if e.type == pygame.KEYDOWN:
                    focus.key(e, self.ui)
                    continue
                if e.type == pygame.MOUSEBUTTONDOWN and not focus.rect.collidepoint(e.pos):
                    focus.commit(self.ui)
            if self.overlay:
                self.overlay.event(e)
                continue
            self.scene.event(e)
        self.ui.mouse = pygame.mouse.get_pos()
        self.ui.tip = None
        N.poll()
        if self.updater.state == "installed" and not self._update_told:
            self._update_told = True
            if isinstance(self.scene, SandboxScene):
                self.scene.toast("Update installed! Restart from the main menu to use it.", WARN)
        self.scene.update(frames, dt)
        self.scene.draw(self.screen)
        if self.overlay:
            self.overlay.draw(self.screen)
        self.ui.draw_tip(self.screen, dt)
        pygame.display.flip()

    def run(self):
        while self.running:
            self.frame()
        pygame.quit()


# ==========================================================================
# Main menu
# ==========================================================================
class PresetCard(Button):
    def __init__(self, name, desc, on_click, selected=None):
        super().__init__(name, on_click, height=74)
        self.desc = desc
        self.selected = selected

    def draw(self, surf, ui):
        hov = self.rect.collidepoint(ui.mouse)
        sel = bool(self.selected and self.selected())
        pygame.draw.rect(surf, (36, 36, 58) if hov or sel else PANEL_LIGHT, self.rect, border_radius=10)
        pygame.draw.rect(surf, ACCENT if hov or sel else BORDER, self.rect, 1 + (hov or sel), border_radius=10)
        ui.text(surf, self.text, (self.rect.x + 12, self.rect.y + 8), 16, ACCENT if hov or sel else TEXT, True)
        for i, line in enumerate(wrap(ui.font(13), self.desc, self.rect.w - 24)[:3]):
            ui.text(surf, line, (self.rect.x + 12, self.rect.y + 32 + i * 16), 13, TEXT_DIM)


def theme_swatch(surf, rect, name, t=0.0):
    """A little preview of a world theme."""
    th = theme(name)
    prev = surf.get_clip()
    surf.set_clip(rect.clip(prev) if prev else rect)
    surf.fill(th["bg"], rect)
    for gx in range(rect.x + 6, rect.right, 14):
        for gy in range(rect.y + 6, rect.bottom, 14):
            surf.fill(th["grid2"], (gx, gy, 2, 2))
    rnd = random.Random(name)
    fx = th["fx"]
    for i in range(14):
        x = rect.x + rnd.random() * rect.w
        y = rect.y + rnd.random() * rect.h
        if fx == "stars":
            surf.fill((220, 225, 255), (x, y, 1 + (i % 4 == 0), 1 + (i % 4 == 0)))
        elif fx == "bubbles":
            pygame.draw.circle(surf, mix(th["bg"], (160, 215, 255), 0.6), (x, y), 2 + i % 3, 1)
        elif fx == "embers":
            surf.fill((255, 150, 50), (x, y, 2, 2))
        elif fx == "fireflies":
            pygame.draw.circle(surf, (210, 255, 130), (x, y), 2)
        elif fx == "snow":
            pygame.draw.circle(surf, (235, 245, 255), (x, y), 1 + i % 2)
        elif fx == "rain":
            pygame.draw.line(surf, (255, 60, 200) if i % 2 else (0, 220, 255), (x, y), (x - 2, y - 8))
    pal = COLOR_SCHEMES.get(th["physics"].get("color_scheme", "Neon Mix")) or COLOR_SCHEMES["Neon Mix"]
    c = rect.center
    R = min(rect.w, rect.h) * 0.32
    pygame.draw.circle(surf, th["border"], c, R, 3)
    for i in range(3):
        a = t * 0.02 + i * 2.1
        pygame.draw.circle(surf, pal[i % len(pal)], (c[0] + math.cos(a) * R * 0.5, c[1] + math.sin(a) * R * 0.5),
                           max(2, R * 0.16))
    surf.set_clip(prev)


class WorldCard(Button):
    def __init__(self, meta, thumb, on_click, selected):
        super().__init__(meta["name"], on_click, height=86)
        self.meta, self.thumb, self.selected = meta, thumb, selected

    def draw(self, surf, ui):
        hov = self.rect.collidepoint(ui.mouse)
        sel = self.selected()
        pygame.draw.rect(surf, (38, 38, 62) if sel else ((30, 30, 50) if hov else PANEL_LIGHT), self.rect,
                         border_radius=10)
        pygame.draw.rect(surf, ACCENT if sel else (mix(BORDER, ACCENT, 0.4) if hov else BORDER), self.rect,
                         2 if sel else 1, border_radius=10)
        tr = pygame.Rect(self.rect.x + 8, self.rect.y + 8, 112, 70)
        if self.thumb:
            surf.blit(pygame.transform.smoothscale(self.thumb, tr.size), tr)
        else:
            theme_swatch(surf, tr, self.meta.get("theme", "Midnight"))
        pygame.draw.rect(surf, BORDER, tr, 1)
        x = tr.right + 14
        ui.text(surf, self.meta["name"], (x, self.rect.y + 10), 17, ACCENT if sel else TEXT, True)
        ui.text(surf, f"{self.meta.get('theme', 'Midnight')}  -  played {W.fmt_time(self.meta.get('last_played'))}",
                (x, self.rect.y + 36), 13, TEXT_DIM)
        ui.text(surf, f"{self.meta['blocks']} blocks   {self.meta['coins']} coins   "
                f"{W.fmt_playtime(self.meta.get('playtime', 0))}", (x, self.rect.y + 56), 13, TEXT_DIM)


class MenuScene:
    def __init__(self, app, mode="main"):
        self.app = app
        self.ui = app.ui
        self.mode = mode
        s = Settings(ring_count=3, ring_radius=110, ring_spacing=55, gap_count=2, gap_size=0.55,
                     max_balls=350, escaped_lifetime=5, world_walls=False, balls_per_escape=2,
                     color_scheme="Neon Mix")
        self.demo = World(s, _Mute())
        self.demo.spawn_center(6)
        self.cam = Camera(app.screen.get_rect(), 0, 0, 1.0)
        self.renderer = Renderer()
        self.t = 0.0
        self.worlds = []
        self.thumbs = {}
        self.sel = None
        self.confirm_delete = 0.0
        self.new_name = ""
        self.new_theme = "Midnight"
        self.new_level = "Classic"
        self.world_list = ScrollList(pad=4, gap=8)
        self.online_list = ScrollList(pad=4, gap=8)
        self.online_tab = "Newest"
        self.online_levels = []
        self.online_sel = None
        self.online_status = ""
        self.online_query = ""
        self.join_code = ""
        self.refresh_worlds()
        self.resize()

    def resize(self):
        W_, H = self.app.screen.get_size()
        self.cam.viewport = pygame.Rect(0, 0, W_, H)
        self.cam.zoom = H / 700
        self.build()

    # --- worlds ----------------------------------------------------------
    def refresh_worlds(self):
        self.worlds = W.list_worlds()
        self.thumbs = {}
        for m in self.worlds:
            p = W.thumb_path(m["id"])
            if p.exists():
                try:
                    self.thumbs[m["id"]] = pygame.image.load(str(p)).convert()
                except (pygame.error, OSError):
                    pass
        ids = [m["id"] for m in self.worlds]
        if self.sel not in ids:
            self.sel = ids[0] if ids else None

    def _meta(self):
        return next((m for m in self.worlds if m["id"] == self.sel), None)

    def _select(self, wid):
        now = pygame.time.get_ticks()
        if self.sel == wid and now - getattr(self, "_last_click", 0) < 400:
            self._open(wid)  # double-click plays
            return
        self._last_click = now
        self.sel = wid
        self.confirm_delete = 0.0
        self.build()

    def _open(self, wid):
        scene = SandboxScene(self.app)
        if scene.open_world(wid):
            self.app.set_scene(scene)

    def _quick_play(self, preset):
        scene = SandboxScene(self.app)
        preset(scene.world)
        scene.fit_camera()
        self.app.set_scene(scene)

    def _create(self):
        name = (self.new_name or "").strip() or f"World {len(self.worlds) + 1}"
        fn = next(p[2] for p in PRESETS if p[0] == self.new_level)
        scene = SandboxScene(self.app)
        scene.create_world(name, self.new_theme, fn)
        self.app.set_scene(scene)

    def _delete(self):
        if self.sel is None:
            return
        if self.confirm_delete <= 0:
            self.confirm_delete = 3.0
            return
        W.delete_world(self.sel)
        self.confirm_delete = 0.0
        self.sel = None
        self.refresh_worlds()
        self.build()

    def _duplicate(self):
        if self.sel:
            self.sel = W.duplicate_world(self.sel) or self.sel
            self.refresh_worlds()
            self.build()

    def _rename(self, name):
        if self.sel:
            W.rename_world(self.sel, name)
            self.refresh_worlds()
            self.build()

    def _start_create(self):
        self.new_name = f"World {len(self.worlds) + 1}"
        self.new_theme = "Midnight"
        self.new_level = "Classic"
        self._mode("create")

    def _panel_rect(self):
        W_, H = self.app.screen.get_size()
        w = min(1120, W_ - 60)
        top = int(H * 0.17)
        return pygame.Rect(W_ // 2 - w // 2, top, w, H - top - 30)

    def build(self):
        W_, H = self.app.screen.get_size()
        self.widgets = []
        if self.mode == "main":
            bw = 300
            x = W_ // 2 - bw // 2
            y = int(H * 0.44)
            items = [Button("PLAY", lambda: self._mode("worlds") if self.worlds else self._start_create(),
                            color=ACCENT, height=48, size=18, tip="Pick one of your worlds or make a new one")]
            if self.worlds:
                last = self.worlds[0]
                items.append(Button(f"CONTINUE: {last['name'][:18].upper()}", lambda: self._open(last["id"]),
                                    color=(60, 200, 255), height=42, size=15,
                                    tip="Jump straight back into your last world"))
            items += [
                Button("QUICK PLAY", lambda: self._mode("levels"), color=ACCENT2, height=42, size=16,
                       tip="Try a level without making a world (not saved)"),
                Button("ONLINE", lambda: self._mode("online"), color=(150, 90, 255), height=42, size=16,
                       tip="Play levels other people shared, or join a friend's room"),
                Button("SETTINGS", self.app.open_settings, height=42, size=16),
                Button("HOW TO PLAY", lambda: self._mode("help"), height=42, size=16),
                Button("QUIT", self.app.quit, height=38, color=(70, 30, 45), text_color=TEXT),
            ]
            for it in items:
                y += it.layout(x, y, bw) + 12
                self.widgets.append(it)
            up = self.app.updater
            if up.state == "available":
                b = Button(f"UPDATE TO v{U.version_str(up.latest)}", up.install, color=ACCENT, height=36, size=14)
                b.layout(W_ - 16 - 240, 44, 240)
                self.widgets.append(b)
            elif up.state == "installed":
                b = Button("RESTART TO UPDATE", self.app.restart_for_update, color=WARN, height=36, size=14)
                b.layout(W_ - 16 - 240, 44, 240)
                self.widgets.append(b)
        elif self.mode == "worlds":
            r = self._panel_rect()
            lw = int(r.w * 0.56)
            cards = [WorldCard(m, self.thumbs.get(m["id"]), lambda wid=m["id"]: self._select(wid),
                               lambda wid=m["id"]: self.sel == wid) for m in self.worlds]
            self.world_list.set(cards, keep_scroll=True)
            self.world_list.layout(pygame.Rect(r.x + 16, r.y + 60, lw, r.h - 130))
            new = Button("+  CREATE NEW WORLD", self._start_create, color=ACCENT, height=44, size=15)
            new.layout(r.x + 16, r.bottom - 60, lw // 2 - 6)
            back = Button("BACK", lambda: self._mode("main"), height=44)
            back.layout(r.x + 16 + lw // 2 + 6, r.bottom - 60, lw // 2 - 6)
            self.widgets += [self.world_list, new, back]
            meta = self._meta()
            if meta:
                dx = r.x + lw + 36
                dw = r.right - dx - 18
                self.detail_x, self.detail_w = dx, dw
                th_h = int(dw * 0.6)
                name = TextInput(lambda: meta["name"], self._rename, "World name", 28,
                                 tip="Click to rename, press Enter to save")
                name.layout(dx, r.y + 60 + th_h + 14, dw)
                play = Button("PLAY", lambda: self._open(meta["id"]), color=ACCENT, height=48, size=18)
                play.layout(dx, r.bottom - 116, dw)
                dup = Button("DUPLICATE", self._duplicate, height=40)
                dup.layout(dx, r.bottom - 60, dw // 2 - 6)
                dele = Button(lambda: "CLICK AGAIN TO DELETE" if self.confirm_delete > 0 else "DELETE",
                              self._delete, color=lambda: DANGER if self.confirm_delete > 0 else (90, 30, 45),
                              text_color=TEXT, height=40, size=lambda: 12 if self.confirm_delete > 0 else 14)
                dele.layout(dx + dw // 2 + 6, r.bottom - 60, dw - dw // 2 - 6)
                self.widgets += [name, play, dup, dele]
        elif self.mode == "create":
            r = self._panel_rect()
            x, w = r.x + 24, r.w - 48
            name = TextInput(lambda: self.new_name, lambda v: setattr(self, "new_name", v), "World name", 28,
                             live=True)
            name.layout(x, r.y + 84, min(460, w))
            self.widgets.append(name)
            cols = 4
            gap = 12
            cw = (w - gap * (cols - 1)) // cols
            y0 = r.y + 160
            for i, tname in enumerate(THEME_ORDER):
                card = ThemeCard(tname, lambda t=tname: setattr(self, "new_theme", t),
                                 lambda t=tname: self.new_theme == t, lambda: self.t)
                card.layout(x + (i % cols) * (cw + gap), y0 + (i // cols) * (card.height + gap), cw)
                self.widgets.append(card)
            rows = (len(THEME_ORDER) + cols - 1) // cols
            y = y0 + rows * (ThemeCard.height + gap) + 34
            lvl = Choice("Starting level", [p[0] for p in PRESETS], lambda: self.new_level,
                         lambda v: setattr(self, "new_level", v),
                         tip="What the world starts with. You can change everything later.")
            lvl.layout(x, y, min(560, w))
            self.widgets.append(lvl)
            self.level_desc_y = y + 40
            create = Button("CREATE WORLD", self._create, color=ACCENT, height=46, size=16)
            create.layout(r.right - 24 - 220, r.bottom - 66, 220)
            cancel = Button("CANCEL", lambda: self._mode("worlds" if self.worlds else "main"), height=46)
            cancel.layout(r.right - 24 - 220 - 12 - 160, r.bottom - 66, 160)
            self.widgets += [create, cancel]
            if self.ui.focus is None:
                name.focus(self.ui)
        elif self.mode == "online":
            self._build_online()
        elif self.mode == "levels":
            cols = 4 if W_ >= 1200 else 3
            cw, gap = min(300, (W_ - 120) // cols), 14
            total_w = cols * cw + (cols - 1) * gap
            x0 = W_ // 2 - total_w // 2
            y0 = int(H * 0.2)
            for i, (name, desc, fn) in enumerate(PRESETS):
                card = PresetCard(name, desc, lambda fn=fn: self._quick_play(fn))
                card.layout(x0 + (i % cols) * (cw + gap), y0 + (i // cols) * (74 + gap), cw)
                self.widgets.append(card)
            back = Button("BACK", lambda: self._mode("main"), height=40)
            rows = (len(PRESETS) + cols - 1) // cols
            back.layout(W_ // 2 - 100, y0 + rows * (74 + gap) + 20, 200)
            self.widgets.append(back)
        else:
            back = Button("BACK", lambda: self._mode("main"), height=40)
            back.layout(W_ // 2 - 100, H - 80, 200)
            self.widgets.append(back)

    def _mode(self, m):
        if self.ui.focus:
            self.ui.focus = None
        self.mode = m
        if m in ("worlds", "main"):
            self.refresh_worlds()
        if m == "online":
            self._fetch_levels()
        self.build()

    # --- online levels ----------------------------------------------------
    def _fetch_levels(self):
        api = self.app.api()
        self.online_sel = None
        if self.online_tab == "My uploads":
            ups = self.app.profile.get("uploads", {})
            self.online_levels = [{"id": k, "name": v.get("name", k), "author": self.app.settings.player_name,
                                   "theme": "", "likes": "?", "plays": "?", "blocks": "?", "description": "",
                                   "mine": True} for k, v in ups.items()]
            self.online_status = "" if ups else "You haven't shared any levels yet (Online tab in a world)."
            self.build()
            return
        if not api.configured:
            self.online_levels = []
            self.online_status = "Online isn't switched on in this copy of the game yet."
            return
        self.online_status = "Loading levels..."

        def done(ok, data):
            if self.mode != "online":
                return
            if ok:
                ups = self.app.profile.get("uploads", {})
                self.online_levels = [dict(lv, mine=lv["id"] in ups) for lv in data.get("levels", [])]
                self.online_status = "" if self.online_levels else "No levels here yet. Share one from a world!"
            else:
                self.online_levels = []
                self.online_status = str(data)
            self.build()
        api.list_levels(done, "top" if self.online_tab == "Top" else "new", self.online_query)

    def _online_meta(self):
        return next((lv for lv in self.online_levels if lv["id"] == self.online_sel), None)

    def _download(self, then):
        lv = self._online_meta()
        if not lv:
            return
        self.online_status = f"Downloading {lv['name']}..."

        def done(ok, data):
            if not ok:
                self.online_status = str(data)
                return
            then(data)
        self.app.api().get_level(lv["id"], done)

    def _play_online(self):
        def go(data):
            scene = SandboxScene(self.app)
            scene.world.load_dict(data["data"])
            if data.get("theme") in THEMES:
                scene.s.theme = data["theme"]
            if scene.world.rings:
                scene.world.spawn_center(1)
            scene.fit_camera()
            scene.resize()
            scene.toast(f"Playing {data['name']} by {data['author']} (not saved)")
            self.app.set_scene(scene)
        self._download(go)

    def _save_online(self):
        def go(data):
            scene = SandboxScene(self.app)
            scene.world.load_dict(data["data"])
            theme_name = data.get("theme") if data.get("theme") in THEMES else scene.s.theme
            scene.s.theme = theme_name
            scene.world_id = W.new_id(data["name"])
            scene.meta = W.make_meta(data["name"], theme_name)
            if scene.world.rings:
                scene.world.spawn_center(1)
            scene.fit_camera()
            scene.resize()
            scene.save_world(thumb=False)
            scene.toast(f"Saved {data['name']} as a world")
            self.app.set_scene(scene)
        self._download(go)

    def _like_online(self):
        lv = self._online_meta()
        if not lv:
            return

        def done(ok, data):
            if ok:
                lv["likes"] = data.get("likes", lv["likes"])
                self.online_status = "You already liked this one" if data.get("already") else "Liked!"
            else:
                self.online_status = str(data)
        self.app.api().like(lv["id"], done)

    def _delete_online(self):
        lv = self._online_meta()
        ups = self.app.profile.get("uploads", {})
        if not lv or lv["id"] not in ups:
            return
        if self.confirm_delete <= 0:
            self.confirm_delete = 3.0
            return
        self.confirm_delete = 0.0

        def done(ok, data):
            if ok or data == "Level not found":
                ups.pop(lv["id"], None)
                self.app.save_profile()
                self.online_status = "Deleted"
                self._fetch_levels()
            else:
                self.online_status = str(data)
        self.app.api().delete(lv["id"], ups[lv["id"]]["token"], done)

    def _join_from_menu(self):
        scene = SandboxScene(self.app)
        PRESETS[-1][2](scene.world)
        scene.fit_camera()
        self.app.set_scene(scene)
        scene.join_room(self.join_code)

    def _build_online(self):
        r = self._panel_rect()
        lw = int(r.w * 0.56)
        x = r.x + 16
        tabs = Tabs(["Newest", "Top", "My uploads"], lambda: self.online_tab,
                    lambda t: (setattr(self, "online_tab", t), self._fetch_levels()), 13)
        tabs.layout(x, r.y + 56, lw)
        search = TextInput(lambda: self.online_query, lambda v: setattr(self, "online_query", v), "Search levels", 40,
                           live=True)
        search.layout(x, r.y + 98, lw - 110)
        go = Button("SEARCH", self._fetch_levels, height=38)
        go.layout(x + lw - 100, r.y + 98, 100)
        cards = [OnlineCard(lv, lambda lid=lv["id"]: self._select_online(lid), lambda lid=lv["id"]: self.online_sel == lid)
                 for lv in self.online_levels]
        self.online_list.set(cards, keep_scroll=True)
        self.online_list.layout(pygame.Rect(x, r.y + 146, lw, r.h - 216))
        back = Button("BACK", lambda: self._mode("main"), height=44)
        back.layout(x, r.bottom - 60, 160)
        settings = Button("SETTINGS", self.app.open_settings, height=44, tip="Set your server address here")
        settings.layout(x + 172, r.bottom - 60, 160)
        self.widgets += [tabs, search, go, self.online_list, back, settings]
        dx = r.x + lw + 36
        dw = r.right - dx - 18
        self.detail_x, self.detail_w = dx, dw
        lv = self._online_meta()
        if lv:
            play = Button("PLAY", self._play_online, color=ACCENT, height=46, size=17)
            play.layout(dx, r.y + 250, dw)
            save = Button("SAVE AS WORLD", self._save_online, height=38)
            save.layout(dx, r.y + 304, dw // 2 - 6)
            like = Button("LIKE", self._like_online, color=ACCENT2, height=38)
            like.layout(dx + dw // 2 + 6, r.y + 304, dw - dw // 2 - 6)
            self.widgets += [play, save, like]
            if lv.get("mine"):
                dele = Button(lambda: "CLICK AGAIN TO DELETE" if self.confirm_delete > 0 else "DELETE MY LEVEL",
                              self._delete_online, color=(90, 30, 45), text_color=TEXT, height=34, size=12)
                dele.layout(dx, r.y + 352, dw)
                self.widgets.append(dele)
        code = TextInput(lambda: self.join_code, lambda v: setattr(self, "join_code", v.upper()[:8]), "ROOM CODE", 8,
                         live=True)
        code.layout(dx, r.bottom - 110, dw - 112)
        join = Button("JOIN", self._join_from_menu, color=ACCENT, height=38)
        join.layout(dx + dw - 100, r.bottom - 110, 100)
        self.widgets += [code, join]

    def _select_online(self, lid):
        self.online_sel = lid
        self.confirm_delete = 0.0
        self.build()

    def event(self, e):
        if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            if self.mode == "create":
                self._mode("worlds" if self.worlds else "main")
            elif self.mode != "main":
                self._mode("main")
            else:
                self.app.quit()
            return
        if e.type == pygame.KEYDOWN and e.key == pygame.K_RETURN:
            if self.mode == "online" and self.join_code:
                self._join_from_menu()
                return
            if self.mode == "create":
                self._create()
                return
            if self.mode == "worlds" and self.sel:
                self._open(self.sel)
                return
            if self.mode == "main":
                self.widgets[0].on_click()
                return
        if e.type == pygame.KEYDOWN and e.key == pygame.K_DELETE and self.mode == "worlds":
            self._delete()
            return
        for w in self.widgets:
            if w.event(e, self.ui):
                return

    def update(self, frames, dt):
        self.t += frames
        if self.confirm_delete > 0:
            self.confirm_delete = max(0.0, self.confirm_delete - dt)
        self.demo.update(frames)
        if len(self.demo.balls) < 3:
            self.demo.spawn_center(3)
        if self.mode == "worlds":
            self.world_list.layout(self.world_list.rect)
        if self.mode == "online":
            self.online_list.layout(self.online_list.rect)

    def draw(self, surf):
        W_, H = surf.get_size()
        ui = self.ui
        self.cam.y = 40 / self.cam.zoom
        self.renderer.draw(surf, self.demo, self.cam)
        shade = pygame.Surface((W_, H), pygame.SRCALPHA)
        shade.fill((8, 8, 14, 150 if self.mode == "main" else 215))
        surf.blit(shade, (0, 0))
        small = self.mode in ("worlds", "create", "online")
        title_y = int(H * (0.25 if self.mode == "main" else (0.08 if small else 0.1)))
        size = 64 if not small else 44
        bob = math.sin(self.t * 0.04) * 4
        for i, col in enumerate(((0, 90, 75), (0, 160, 130))):
            ui.text(surf, "FUN BALL GAME", (W_ // 2 + 3 - i * 2, title_y + bob + 3 - i * 2), size, col, True, "center")
        ui.text(surf, "FUN BALL GAME", (W_ // 2, title_y + bob), size, ACCENT, True, "center")
        if self.mode == "main":
            ui.text(surf, f"v{__version__}  -  Pygame Sandbox Edition", (W_ // 2, title_y + 52), 18, ACCENT2, True,
                    "center")
            n_blocks = sum(len(v) for v in B.CATEGORIES.values())
            ui.text(surf, f"{n_blocks} blocks & items  -  {len(BALL_TYPES)} ball types  -  "
                    f"{len(THEMES)} world themes  -  {len(PRESETS)} levels",
                    (W_ // 2, title_y + 80), 14, TEXT_DIM, False, "center")
            got = len(self.app.achievements.unlocked)
            ui.text(surf, f"Achievements: {got}/{len(ACHIEVEMENTS)}", (W_ // 2, H - 30), 14,
                    WARN, False, "center")
            ui.text(surf, f"v{__version__}", (14, H - 26), 13, TEXT_DIM)
            up = self.app.updater
            if up.state in ("available", "installing", "installed", "error") and up.message:
                ui.text(surf, up.message, (W_ - 16, 18), 14, ACCENT if up.state != "error" else TEXT_DIM, True,
                        "topright")
        elif self.mode == "worlds":
            r = self._panel_rect()
            panel(surf, r, (16, 16, 26))
            ui.text(surf, "YOUR WORLDS", (r.x + 18, r.y + 18), 22, ACCENT, True)
            ui.text(surf, f"{len(self.worlds)} saved", (r.x + 200, r.y + 25), 13, TEXT_DIM)
            if not self.worlds:
                ui.text(surf, "No worlds yet. Make one!", self.world_list.rect.center, 18, TEXT_DIM, True, "center")
            meta = self._meta()
            if meta:
                dx, dw = self.detail_x, self.detail_w
                tr = pygame.Rect(dx, r.y + 60, dw, int(dw * 0.6))
                thumb = self.thumbs.get(meta["id"])
                if thumb:
                    surf.blit(pygame.transform.smoothscale(thumb, tr.size), tr)
                else:
                    theme_swatch(surf, tr, meta.get("theme", "Midnight"), self.t)
                pygame.draw.rect(surf, BORDER, tr, 1)
                y = tr.bottom + 66
                th = theme(meta.get("theme", "Midnight"))
                rows = [("Theme", f"{meta.get('theme', 'Midnight')} - {th['desc']}"),
                        ("Created", W.fmt_time(meta.get("created"))),
                        ("Last played", W.fmt_time(meta.get("last_played"))),
                        ("Play time", W.fmt_playtime(meta.get("playtime", 0))),
                        ("Stuff", f"{meta['blocks']} blocks, {meta['coins']} coins, {meta['escapes']} escapes")]
                for k, v in rows:
                    ui.text(surf, k, (dx, y), 13, TEXT_DIM, True)
                    for i, line in enumerate(wrap(ui.font(13), v, dw - 100)[:2]):
                        ui.text(surf, line, (dx + 100, y + i * 16), 13, TEXT)
                    y += 22 if len(wrap(ui.font(13), v, dw - 100)) < 2 else 36
        elif self.mode == "create":
            r = self._panel_rect()
            panel(surf, r, (16, 16, 26))
            ui.text(surf, "CREATE A NEW WORLD", (r.x + 24, r.y + 20), 22, ACCENT, True)
            ui.text(surf, "Name", (r.x + 24, r.y + 62), 13, TEXT_DIM, True)
            ui.text(surf, "Theme", (r.x + 24, r.y + 138), 13, TEXT_DIM, True)
            desc = next(p[1] for p in PRESETS if p[0] == self.new_level)
            ui.text(surf, desc, (r.x + 24, self.level_desc_y), 13, TEXT_DIM)
        elif self.mode == "online":
            r = self._panel_rect()
            panel(surf, r, (16, 16, 26))
            ui.text(surf, "ONLINE", (r.x + 18, r.y + 18), 22, ACCENT, True)
            if self.online_status:
                for i, line in enumerate(wrap(ui.font(14), self.online_status, self.online_list.rect.w - 20)[:3]):
                    ui.text(surf, line, (self.online_list.rect.x + 10, self.online_list.rect.y + 10 + i * 20), 14, WARN)
            dx, dw = self.detail_x, self.detail_w
            lv = self._online_meta()
            if lv:
                ui.text(surf, lv["name"], (dx, r.y + 60), 22, TEXT, True)
                ui.text(surf, f"by {lv['author']}", (dx, r.y + 92), 14, ACCENT2, True)
                ui.text(surf, f"{lv.get('theme') or '?'} theme   {lv['blocks']} blocks   {lv['likes']} likes   "
                        f"{lv['plays']} plays", (dx, r.y + 116), 13, TEXT_DIM)
                for i, line in enumerate(wrap(ui.font(14), lv.get("description") or "No description.", dw)[:4]):
                    ui.text(surf, line, (dx, r.y + 146 + i * 20), 14, TEXT)
            else:
                ui.text(surf, "Pick a level on the left.", (dx, r.y + 60), 15, TEXT_DIM)
            ui.text(surf, "MULTIPLAYER", (dx, r.bottom - 176), 14, ACCENT, True)
            ui.text(surf, "Type a friend's room code to join them. To host, open a world", (dx, r.bottom - 154), 13, TEXT_DIM)
            ui.text(surf, "and use the Online tab on the right.", (dx, r.bottom - 136), 13, TEXT_DIM)
        elif self.mode == "levels":
            ui.text(surf, "Quick play  -  pick a level (not saved as a world)", (W_ // 2, title_y + 60),
                    20, TEXT, True, "center")
        else:
            r = pygame.Rect(W_ // 2 - 380, int(H * 0.18), 760, int(H * 0.68))
            panel(surf, r, (16, 16, 26))
            y = r.y + 18
            intro = ("Balls bounce inside spinning rings. When one escapes through a gap, more balls "
                     "spawn in the middle. Make a world, then build machines out of walls, bumpers, portals, "
                     "black holes, cannons, TNT and more using the toolbox on the left. Your worlds save "
                     "automatically.")
            for line in wrap(ui.font(15), intro, r.w - 40):
                ui.text(surf, line, (r.x + 20, y), 15, TEXT)
                y += 20
            y += 10
            for key, desc in HELP_LINES:
                if desc is None:
                    y += 6
                    ui.text(surf, key, (r.x + 20, y), 14, ACCENT, True)
                else:
                    ui.text(surf, key, (r.x + 20, y), 14, WARN, True)
                    ui.text(surf, desc, (r.x + 230, y), 14, TEXT)
                y += 20
        for w in self.widgets:
            w.hover(ui)
            w.draw(surf, ui)


class OnlineCard(Button):
    def __init__(self, lv, on_click, selected):
        super().__init__(lv["name"], on_click, height=64)
        self.lv, self.selected = lv, selected

    def draw(self, surf, ui):
        hov = self.rect.collidepoint(ui.mouse)
        sel = self.selected()
        pygame.draw.rect(surf, (38, 38, 62) if sel else ((30, 30, 50) if hov else PANEL_LIGHT), self.rect,
                         border_radius=10)
        pygame.draw.rect(surf, ACCENT if sel else (mix(BORDER, ACCENT, 0.4) if hov else BORDER), self.rect,
                         2 if sel else 1, border_radius=10)
        th = self.lv.get("theme")
        sw = pygame.Rect(self.rect.x + 8, self.rect.y + 8, 48, 48)
        theme_swatch(surf, sw, th if th in THEMES else "Midnight")
        x = sw.right + 12
        ui.text(surf, self.lv["name"], (x, self.rect.y + 10), 16, ACCENT if sel else TEXT, True)
        mine = "  (yours)" if self.lv.get("mine") else ""
        ui.text(surf, f"by {self.lv['author']}{mine}   {self.lv['likes']} likes   {self.lv['plays']} plays",
                (x, self.rect.y + 36), 13, TEXT_DIM)


class ThemeCard(Button):
    height = 118

    def __init__(self, name, on_click, selected, clock):
        super().__init__(name, on_click, height=ThemeCard.height, tip=theme(name)["desc"])
        self.selected, self.clock = selected, clock

    def draw(self, surf, ui):
        sel = self.selected()
        hov = self.rect.collidepoint(ui.mouse)
        sw = pygame.Rect(self.rect.x + 6, self.rect.y + 6, self.rect.w - 12, self.rect.h - 36)
        pygame.draw.rect(surf, (38, 38, 62) if sel else PANEL_LIGHT, self.rect, border_radius=10)
        theme_swatch(surf, sw, self.text, self.clock())
        pygame.draw.rect(surf, ACCENT if sel else (mix(BORDER, ACCENT, 0.5) if hov else BORDER), self.rect,
                         3 if sel else 1, border_radius=10)
        ui.text(surf, self.text, (self.rect.centerx, self.rect.bottom - 16), 14, ACCENT if sel else TEXT,
                True, "center")


# ==========================================================================
# Sandbox
# ==========================================================================
class SandboxScene:
    def __init__(self, app):
        self.app = app
        self.ui = app.ui
        self.s = app.settings
        self.world = World(self.s, app.audio)
        self.renderer = Renderer()
        self.cam = Camera(pygame.Rect(0, 0, 100, 100))
        self.show_ui = True
        self.show_help = False
        self.tool = ("tool", "select")
        self.ball_kind = "normal"
        self.place_angle = 0.0
        self.selected = None
        self.undo_stack = []
        self.toasts = []
        self.left_tab = "Blocks"
        self.right_tab = "World"
        self.mouse_w = (0.0, 0.0)
        self.prev_mouse_w = (0.0, 0.0)
        self.mouse_vel = (0.0, 0.0)
        self.lmb = False
        self.rmb = False
        self.place_start = None
        self.drag = None          # ("move", blk, ox, oy, snapshot) or ("pan", sx, sy, camx, camy)
        self.grabbed = []
        self.erase_batch = None
        self.spray_t = 0.0
        self.rain = False
        self.rain_t = 0.0
        self.net = None   # online room (multiplayer / cloud physics), see net.py
        self.solo_cloud = False   # we opened a private room just to use cloud physics
        self._solo_was_cloud = False
        self.join_code = ""
        self.share_name = ""
        self.share_desc = ""
        self.share_status = ""
        self._online_refresh = 1.0
        self.chat_input = TextInput(lambda: "", lambda v: self.net and self.net.say(v), "Say something...", 120)
        self.fps = 60.0
        self._icon_cache = {}
        self._inspected = None
        self.left_list = ScrollList()
        self.right_list = ScrollList()
        self.world_id = None   # None = quick play (not saved as a world)
        self.meta = None
        self.autosave_timer = 0.0
        self.resize()

    # ------------------------------------------------------------------
    # layout & panels
    # ------------------------------------------------------------------
    def resize(self):
        W, H = self.app.screen.get_size()
        if self.show_ui:
            self.cam.viewport = pygame.Rect(LEFT_W, TOP_H, W - LEFT_W - RIGHT_W, H - TOP_H)
        else:
            self.cam.viewport = pygame.Rect(0, 0, W, H)
        self.left_rect = pygame.Rect(0, TOP_H, LEFT_W, H - TOP_H)
        self.right_rect = pygame.Rect(W - RIGHT_W, TOP_H, RIGHT_W, H - TOP_H)
        self.top_rect = pygame.Rect(0, 0, W, TOP_H)
        self.left_tabs = Tabs(["Tools", "Blocks", "Fields", "Items", "Balls"],
                              lambda: self.left_tab, self._set_left_tab, 12)
        self.left_tabs.layout(self.left_rect.x + 8, self.left_rect.y + 8, LEFT_W - 16)
        self.right_tabs = Tabs(["World", "Physics", "Visual", "Inspect", "Online"],
                               lambda: self.right_tab, self._set_right_tab, 12)
        self.right_tabs.layout(self.right_rect.x + 8, self.right_rect.y + 8, RIGHT_W - 16)
        self._build_top()
        self._build_left()
        self._build_right()

    def fit_camera(self):
        """Zoom and centre the camera so the rings and every block are visible."""
        rings = self.world.rings
        R = rings[-1].radius + 60 if rings else 0
        x0, y0, x1, y1 = -R, -R, R, R
        for blk in self.world.blocks:
            e = min(blk.extent(), 300) + 30
            x0, y0 = min(x0, blk.x - e), min(y0, blk.y - e)
            x1, y1 = max(x1, blk.x + e), max(y1, blk.y + e)
        if x1 - x0 < 200:
            x0, y0, x1, y1 = -500, -500, 500, 500
        self.cam.x, self.cam.y = (x0 + x1) / 2, (y0 + y1) / 2
        vp = self.cam.viewport
        self.cam.zoom = clamp(min(vp.w / (x1 - x0), vp.h / (y1 - y0)), 0.2, 2.0)

    def _set_left_tab(self, t):
        self.left_tab = t
        self._build_left()

    def _set_right_tab(self, t):
        self.right_tab = t
        self._build_right()

    def _build_top(self):
        def sp(delta):
            i = min(range(len(SPEEDS)), key=lambda k: abs(SPEEDS[k] - self.s.time_speed))
            self.s.time_speed = SPEEDS[clamp(i + delta, 0, len(SPEEDS) - 1)]

        w = self.world
        btns = [
            (Button(lambda: "PLAY" if w.paused else "PAUSE", self.toggle_pause,
                    color=lambda: ACCENT if w.paused else WARN, tip="Pause / resume (Space)"), 84),
            (Button("STEP", lambda: setattr(w, "step_once", True), tip="Advance one frame (N)"), 58),
            (Button("-", lambda: sp(-1), tip="Slower (-)"), 30),
            (Button(lambda: f"{self.s.time_speed:g}x", lambda: setattr(self.s, "time_speed", 1.0),
                    tip="Simulation speed. Click to reset to 1x."), 54),
            (Button("+", lambda: sp(1), tip="Faster (+)"), 30),
            (Button(lambda: f"+{self.s.burst_size}", lambda: self.spawn_center(self.s.burst_size),
                    tip="Spawn a burst of balls in the centre (B). Set the size in the Balls tab."), 56),
            (Button("CLEAR BALLS", self.clear_balls, tip="Delete every ball (C)"), 108),
            (Button("CLEAR MAP", self.clear_blocks, color=(90, 30, 45), text_color=TEXT,
                    tip="Delete every block (can be undone)"), 96),
            (Button("UNDO", self.undo, tip="Undo (Ctrl+Z)"), 62),
            (Button(self._cloud_label, self.toggle_cloud, color=self._cloud_color,
                    tip="Who runs the physics: PC = your computer (offline), CLOUD = the game's server. "
                        "The % is how much cloud power you get: 100% when you're the only one using it. "
                        "Click to switch."), 96),
            (Button("SETTINGS", self.app.open_settings, tip="FPS, ball limit, graphics, sound (O)"), 92),
            (Button("HELP", lambda: setattr(self, "show_help", not self.show_help), tip="Controls (H)"), 58),
            (Button("MENU", self.to_menu, tip="Back to the main menu (progress is auto-saved)"), 62),
        ]
        W = self.top_rect.w
        x = W - 10 - sum(bw for _, bw in btns) - 6 * (len(btns) - 1)
        self.top_widgets = []
        for b, bw in btns:
            b.layout(x, 11, bw)
            x += bw + 6
            self.top_widgets.append(b)
        self.top_stats_right = self.top_widgets[0].rect.x - 10

    def _icon_for_block(self, key):
        inst = self._icon_cache.get(key)
        if inst is None:
            inst = B.create(key, 0, 0, **ICON_OVERRIDES.get(key, {}))
            self._icon_cache[key] = inst

        def draw(surf, rect):
            inst.t += 0.5
            ext = inst.r if inst.shape == "circle" else max(inst.w, inst.h) / 2
            if key == "mover":
                ext = inst.w / 2 + inst.travel
            if key == "laser":
                ext = inst.length * 0.6
            cam = Camera(rect, 0, 0, min(rect.w, rect.h) * 0.46 / max(1, ext))
            if key == "laser":
                cam.x, cam.y = inst.length * 0.35 * math.cos(inst.angle), inst.length * 0.35 * math.sin(inst.angle)
            inst.draw(surf, cam)
        return draw

    def _icon_for_ball(self, kind):
        d = BALL_TYPES[kind]

        def draw(surf, rect):
            c = rect.center
            r = min(rect.w, rect.h) * 0.22 * (0.7 + 0.3 * min(1.5, d["size"]))
            col = d["color"] or (ACCENT if kind != "rainbow" else
                                 tuple(int(127 + 127 * math.sin(pygame.time.get_ticks() / 300 + k * 2))
                                       for k in range(3)))
            if kind == "ghost":
                pygame.draw.circle(surf, mix(BG, col, 0.35), c, r)
                pygame.draw.circle(surf, col, c, r, 1)
                return
            pygame.draw.circle(surf, col, c, r)
            pygame.draw.circle(surf, mix(col, (255, 255, 255), 0.6), (c[0] - r * 0.3, c[1] - r * 0.3), r * 0.3)
            if kind == "fire":
                for i in range(3):
                    pygame.draw.circle(surf, (255, 200, 40), (c[0] - r * 1.2 - i * 5, c[1] + i * 3), 3 - i * 0.6)
            if kind == "bomb":
                pygame.draw.circle(surf, (255, 120, 40), (c[0], c[1] - r), 3)
        return draw

    def _build_left(self):
        tiles = []
        tab = self.left_tab
        if tab == "Tools":
            for i, (key, name, desc, icon) in enumerate(TOOLS):
                tiles.append(Tile(name, icon, lambda k=key: self.set_tool(("tool", k)),
                                  lambda k=key: self.tool == ("tool", k), desc, str(i + 1)))
        elif tab == "Balls":
            for i, kind in enumerate(BALL_ORDER):
                d = BALL_TYPES[kind]
                tiles.append(Tile(d["name"], self._icon_for_ball(kind),
                                  lambda k=kind: self.set_tool(("ball", k)),
                                  lambda k=kind: self.tool == ("ball", k), d["desc"],
                                  str(i + 1) if i < 9 else None))
        else:
            for i, key in enumerate(B.CATEGORIES[tab]):
                cls = B.REGISTRY[key]
                tiles.append(Tile(cls.name, self._icon_for_block(key),
                                  lambda k=key: self.set_tool(("block", k)),
                                  lambda k=key: self.tool == ("block", k), cls.desc,
                                  str(i + 1) if i < 9 else None))
        widgets = [Grid(tiles, 3, 80)]
        if tab == "Balls":
            s = self.s
            widgets = [
                NumberInput("Spawn amount", lambda: s.burst_size, lambda v: setattr(s, "burst_size", v), 1, 100000,
                            "Type how many balls you want and press Enter. Shift+click, B and the +N button "
                            "use this amount too."),
                Button(lambda: f"Spawn {s.burst_size:,} balls", lambda: self.spawn_center(s.burst_size),
                       color=ACCENT, height=32, tip="Spawns them in the centre. Shift+click spawns them at the mouse."),
                Spacer(2),
            ] + widgets
            widgets += [
                Spacer(4),
                Toggle("Escapes spawn this type", lambda: s.spawn_type == self.ball_kind,
                       lambda v: setattr(s, "spawn_type", self.ball_kind if v else "normal"),
                       tip="When on, balls spawned by escapes are this type too."),
                Header("Fast spawning"),
                self._slider("Spray rate /sec", "spray_rate", 1, 1000, 1,
                             "How many balls per second you spray while holding the mouse."),
                self._slider("Spray brush size", "spray_size", 0, 400, 5,
                             "Spread the spray over a circle this big."),
                Toggle("Ball rain (R)", lambda: self.rain, lambda v: setattr(self, "rain", v),
                       tip="Balls fall from the top of the screen nonstop."),
                self._slider("Rain rate /sec", "rain_rate", 1, 500, 1),
            ]
        self.left_list.set(widgets)
        r = self.left_rect
        self.left_list.layout(pygame.Rect(r.x, r.y + 46, r.w, r.h - 46 - 130))

    def _sb(self, attr, rebuild=False, cast=None):
        s = self.s

        def get():
            return getattr(s, attr)

        def set_(v):
            setattr(s, attr, cast(v) if cast else v)
            if rebuild:
                self.world.rebuild_rings()
        return get, set_

    def _slider(self, label, attr, lo, hi, step, tip=None, rebuild=False, fmt=None):
        g, st = self._sb(attr, rebuild, int if step >= 1 and isinstance(getattr(self.s, attr), int) else None)
        return Slider(label, g, st, lo, hi, step, fmt, tip)

    def _toggle(self, label, attr, tip=None, rebuild=False):
        g, st = self._sb(attr, rebuild)
        return Toggle(label, g, st, tip)

    def _build_right(self):
        tab = self.right_tab
        s = self.s
        wd = []
        if tab == "World":
            if self.world_id:
                wd += [Header("This world", ACCENT2),
                       TextInput(lambda: self.meta["name"], self.rename_world, "World name", 28,
                                 tip="Click to rename this world, Enter to save"),
                       Choice("Theme", THEME_ORDER, lambda: s.theme, lambda v: setattr(s, "theme", v),
                              tip="Changes how the world looks."),
                       Button("Save world now (Ctrl+S)", lambda: self.save_world(quiet=False), height=28)]
            wd += [
                Header("Arena"),
                self._slider("Rings", "ring_count", 0, 6, 1, "How many spinning rings. 0 = free sandbox.", True),
                self._slider("Ring radius", "ring_radius", 60, 600, 5, "Size of the innermost ring.", True),
                self._slider("Ring spacing", "ring_spacing", 25, 250, 5, "Gap between nested rings.", True),
                self._slider("Rotation speed", "rotation_speed", -0.15, 0.15, 0.002,
                             "How fast the rings spin. Negative spins the other way.", True),
                self._toggle("Alternate spin direction", "alternate_spin",
                             "Every other ring spins the opposite way.", True),
                self._slider("Gaps per ring", "gap_count", 0, 8, 1, "Number of exits on each ring.", True),
                self._slider("Gap size", "gap_size", 0.05, 3.0, 0.05, "Width of each exit (radians).", True),
                self._slider("Ring thickness", "ring_thickness", 2, 40, 1, None, True),
                Header("Spawning"),
                self._slider("Balls per escape", "balls_per_escape", 0, 10, 1,
                             "How many new balls appear when one escapes the outer ring."),
                Choice("Escape ball type", BALL_ORDER, lambda: s.spawn_type,
                       lambda v: setattr(s, "spawn_type", v), names=lambda k: BALL_TYPES[k]["name"]),
                self._slider("Max balls", "max_balls", 10, 5000, 10, "Ball limit before the limit action kicks in."),
                NumberInput("Custom limit", lambda: s.max_balls, lambda v: setattr(s, "max_balls", v),
                            1, 1_000_000, "Type any ball limit you want and press Enter."),
                self._toggle("Unlimited balls", "unlimited_balls",
                             "No ball limit at all. Your computer is the limit!"),
                Choice("At the limit", LIMIT_ACTIONS, lambda: s.limit_action,
                       lambda v: setattr(s, "limit_action", v)),
                self._slider("Free ball lifetime (s)", "escaped_lifetime", 0, 120, 1,
                             "Escaped balls disappear after this many seconds. 0 = never."),
                self._slider("Ball size", "ball_radius", 2, 30, 0.5, "Radius of newly spawned balls."),
                self._slider("Spawn speed", "spawn_speed", 0, 20, 0.5),
                Row(Button("+1", lambda: self.spawn_center(1)),
                    Button("+10", lambda: self.spawn_center(10)),
                    Button("+100", lambda: self.spawn_center(100))),
                Row(NumberInput("Custom", lambda: s.burst_size, lambda v: setattr(s, "burst_size", v), 1, 100000,
                                "Type any amount, press Enter"),
                    Button("Spawn", lambda: self.spawn_center(s.burst_size), color=ACCENT, height=32)),
                Header("World"),
                self._toggle("World walls", "world_walls", "Bounce balls off the edge of the world."),
                self._slider("World width", "world_width", 600, 8000, 100),
                self._slider("World height", "world_height", 400, 6000, 100),
                Header("Levels"),
                Label("Loading a level replaces what's in this world." if self.world_id else
                      "Quick play: this isn't saved as a world.", 13),
            ]
            for name, desc, fn in PRESETS:
                wd.append(Button(name, lambda fn=fn: self.load_preset(fn), tip=desc, height=28))
            wd += [Header("Save / Load")]
            for i in (1, 2, 3):
                path = SAVE_DIR / f"slot{i}.json"
                wd.append(Row(Button(f"Save {i}", lambda p=path: self.save_file(p)),
                              Button(lambda p=path, i=i: f"Load {i}" if p.exists() else "(empty)",
                                     lambda p=path: self.load_file(p))))
            wd.append(Button("Reset all settings", self.reset_settings, color=(90, 30, 45), text_color=TEXT))
        elif tab == "Physics":
            wd += [
                Header("Gravity & time"),
                self._slider("Gravity", "gravity", 0, 1.0, 0.01),
                self._slider("Gravity direction", "gravity_angle", 0, 360, 5,
                             "90 = down, 270 = up, 0 = right, 180 = left.", fmt=lambda v: f"{int(v)} deg"),
                self._slider("Time speed", "time_speed", 0.05, 4, 0.05),
                self._slider("Substeps", "substeps", 1, 8, 1, "More = more accurate but slower."),
                Header("Walls"),
                self._slider("Ring bounciness", "wall_bounce", 0.1, 1.6, 0.05,
                             "Above 1 adds energy, below 1 absorbs it."),
                self._slider("Energy boost per hit", "energy_boost", 1.0, 1.2, 0.005,
                             "Speed multiplier every time a ball hits a ring (the old game used 1.03)."),
                self._slider("Ring grip", "wall_grip", 0.0, 1.0, 0.01,
                             "How much a spinning ring drags balls along with it."),
                Header("Balls"),
                self._toggle("Ball collisions", "ball_collisions"),
                self._slider("Ball-ball bounce", "ball_bounce", 0.0, 1.2, 0.05),
                self._slider("Air drag", "air_drag", 0.0, 0.05, 0.001),
                self._slider("Max speed", "max_speed", 3, 80, 1),
            ]
        elif tab == "Visual":
            wd += [
                Header("Look"),
                Choice("World theme", THEME_ORDER, lambda: s.theme, lambda v: setattr(s, "theme", v),
                       tip=lambda: theme(s.theme)["desc"]),
                Choice("Colour scheme", list(COLOR_SCHEMES), lambda: s.color_scheme,
                       lambda v: setattr(s, "color_scheme", v)),
                Button("Recolour all balls", self.recolor, height=28),
                self._toggle("Glow", "glow"),
                self._toggle("Motion trails", "trails"),
                self._slider("Trail length", "trail_length", 2, 40, 1),
                self._toggle("Particles", "particles"),
                self._toggle("Screen shake", "screen_shake"),
                self._toggle("Background grid", "show_grid"),
                self._toggle("Snap to grid (G)", "snap_to_grid", "Snap block placement to a 25px grid."),
                self._toggle("Show hitboxes (dev)", "show_hitboxes"),
                Header("Audio"),
                self._toggle("Sound effects", "sound"),
                self._slider("Volume", "volume", 0, 1, 0.05),
                Header("Stats"),
                Label(self._stats_text, 14, TEXT),
                Header("Achievements", WARN),
                Label(self._ach_text, 13, TEXT_DIM),
            ]
        elif tab == "Online":
            wd += self._online_widgets()
        else:
            wd += self._inspector_widgets()
        self._inspected = self.selected
        self.right_list.set(wd, keep_scroll=True)
        r = self.right_rect
        self.right_list.layout(pygame.Rect(r.x, r.y + 46, r.w, r.h - 46))

    def _stats_text(self):
        st = self.world.stats
        return (f"Balls now: {len(self.world.balls)}   Peak: {st['peak']}\n"
                f"Escapes: {st['escapes']}   Spawned: {st['spawned']}\n"
                f"Lost: {st['lost']}   Coins: {self.world.coins}\n"
                f"Bricks: {st['bricks']}   Glass: {st['glass']}\n"
                f"Explosions: {st['explosions']}   Goals: {st['goals']}\n"
                f"Teleports: {st['teleports']}   Bumps: {st['bumps']}")

    def _ach_text(self):
        got = self.app.achievements.unlocked
        lines = [f"{len(got)}/{len(ACHIEVEMENTS)} unlocked"]
        for key, name, desc, _ in ACHIEVEMENTS:
            lines.append(("[x] " if key in got else "[  ] ") + f"{name}: {desc}")
        return "\n".join(lines)

    def _inspector_widgets(self):
        blk = self.selected
        if blk is None or not blk.alive:
            return [Header("Inspector"),
                    Label("Nothing selected.\n\nPick the Select tool (key 1 in the Tools tab) and click a "
                          "block, or place a new one, to edit its properties here.", 14)]
        wd = [Header(blk.name), Label(blk.desc, 13)]

        def attr_slider(label, attr, lo, hi, step):
            return Slider(label, lambda: getattr(blk, attr), lambda v: setattr(blk, attr, v), lo, hi, step)

        if blk.rotatable:
            wd.append(Slider("Rotation", lambda: math.degrees(blk.angle) % 360,
                             lambda v: setattr(blk, "angle", math.radians(v)), 0, 359, 1,
                             lambda v: f"{int(v)} deg"))
        if blk.resizable:
            if blk.shape == "circle":
                wd.append(attr_slider("Radius", "r", 4, 900, 1))
            else:
                wd.append(attr_slider("Width", "w", 6, 1500, 1))
                wd.append(attr_slider("Height", "h", 6, 1500, 1))
        for p in blk.props:
            if isinstance(p[2], list):
                opts = p[2]
                wd.append(Choice(p[1], opts, lambda a=p[0]: getattr(blk, a),
                                 lambda v, a=p[0]: setattr(blk, a, v),
                                 names=(lambda k: BALL_TYPES[k]["name"]) if opts is BALL_ORDER else None))
            else:
                attr, label, lo, hi, step = p
                wd.append(attr_slider(label, attr, lo, hi, step))
        wd += [Spacer(6),
               Row(Button("Duplicate", self.duplicate_selected, tip="Ctrl+D"),
                   Button("Rotate 45", lambda: setattr(blk, "angle", blk.angle + math.pi / 4))),
               Button("Delete", self.delete_selected, color=(120, 35, 50), text_color=TEXT, tip="Delete key")]
        return wd

    # ------------------------------------------------------------------
    # actions
    # ------------------------------------------------------------------
    def set_tool(self, tool):
        self.tool = tool
        if tool[0] == "ball":
            self.ball_kind = tool[1]
            if self.left_tab == "Balls":
                self._build_left()
        self.place_start = None

    def toggle_pause(self):
        self.world.paused = not self.world.paused

    def select(self, blk):
        self.selected = blk
        if blk is not None and self.right_tab != "Inspect":
            self.right_tab = "Inspect"
        self._build_right()

    def push_undo(self, entry):
        self.undo_stack.append(entry)
        if len(self.undo_stack) > 200:
            self.undo_stack.pop(0)

    def undo(self):
        if not self.undo_stack:
            self.toast("Nothing to undo", TEXT_DIM)
            return
        kind, *data = self.undo_stack.pop()
        w = self.world
        if kind == "add":
            for blk in data[0]:
                blk.alive = False
            w.blocks = [b for b in w.blocks if b.alive]
            if self.selected in data[0]:
                self.select(None)
        elif kind == "remove":
            for blk in data[0]:
                blk.alive = True
                w.blocks.append(blk)
        elif kind == "state":
            blk, snap = data
            for k, v in snap.items():
                if k != "key":
                    setattr(blk, k, v)
            blk.after_load()
        self.toast("Undone", TEXT_DIM)
        self._build_right()

    def clear_blocks(self):
        live = [b for b in self.world.blocks if b.alive]
        if live:
            self.push_undo(("remove", live))
        self.world.clear_blocks()
        self.select(None)

    def delete_selected(self):
        blk = self.selected
        if blk and blk.alive:
            self.world.remove_block(blk)
            self.world.blocks = [b for b in self.world.blocks if b.alive]
            self.push_undo(("remove", [blk]))
            self.world.fx.burst(blk.x, blk.y, (200, 200, 220), 10, 2, 2, 20)
        self.select(None)

    def duplicate_selected(self):
        blk = self.selected
        if blk and blk.alive:
            nb = blk.clone()
            if nb.key == "portal":
                nb.channel = self.next_portal_channel()
            self.world.add_block(nb)
            self.push_undo(("add", [nb]))
            self.select(nb)

    def recolor(self):
        from .settings import scheme_color
        for b in self.world.balls:
            if BALL_TYPES[b.kind]["color"] is None and b.kind != "rainbow":
                b.color = scheme_color(self.s.color_scheme)

    def reset_settings(self):
        snd, vol = self.s.sound, self.s.volume
        self.s.reset()
        self.s.sound, self.s.volume = snd, vol
        self.world.rings = []
        self.world.rebuild_rings()
        self.toast("Settings reset")

    def load_preset(self, fn):
        th = self.s.theme
        fn(self.world)
        if self.world_id:
            self.s.theme = th  # a world keeps its theme when you load a level into it
        self.select(None)
        self.undo_stack.clear()
        self.fit_camera()
        self.resize()

    def save_file(self, path, quiet=False):
        data = self.world.to_dict()
        data["coins"] = self.world.coins
        data["camera"] = [self.cam.x, self.cam.y, self.cam.zoom]
        ok = _write_json(path, data)
        if not quiet:
            self.toast(f"Saved to {Path(path).name}" if ok else "Could not save!", ACCENT if ok else DANGER)
        self._build_right()

    def load_file(self, path):
        data = _read_json(path)
        if not data:
            self.toast("That save slot is empty", TEXT_DIM)
            return
        snd, vol = self.s.sound, self.s.volume
        self.world.load_dict(data)
        self.s.sound, self.s.volume = snd, vol
        self.world.coins = data.get("coins", 0)
        if self.world.rings:
            self.world.spawn_center(1)
        cam = data.get("camera")
        if cam:
            self.cam.x, self.cam.y, self.cam.zoom = cam
        self.select(None)
        self.undo_stack.clear()
        self.toast(f"Loaded {Path(path).name}")
        self.resize()

    def autosave(self):
        """Called when leaving: worlds always save, quick-play sessions don't."""
        if self.world_id:
            self.save_world()

    # ------------------------------------------------------------------
    # worlds
    # ------------------------------------------------------------------
    def create_world(self, name, theme_name, preset):
        preset(self.world)
        self.s.theme = theme_name
        for k, v in theme(theme_name)["physics"].items():
            setattr(self.s, k, v)
        self.world.rings = []
        self.world.rebuild_rings()
        self.world_id = W.new_id(name)
        self.meta = W.make_meta(name, theme_name)
        self.fit_camera()
        self.resize()
        self.save_world(thumb=False)
        self.toast(f"Created world: {name}")

    def open_world(self, wid):
        data = W.load_world(wid)
        if not data:
            return False
        self.world.load_dict(data)
        self.world.coins = data.get("coins", 0)
        for k, v in data.get("stats", {}).items():
            if k in self.world.stats:
                self.world.stats[k] = v
        if not self.world.balls and self.world.rings:
            self.world.spawn_center(1)
        self.world_id = wid
        self.meta = dict(data.get("meta") or W.make_meta("World", self.s.theme))
        cam = data.get("camera")
        if cam:
            self.cam.x, self.cam.y, self.cam.zoom = cam
        else:
            self.fit_camera()
        self.resize()
        self.toast(f"Welcome back to {self.meta['name']}")
        return True

    def save_world(self, thumb=True, quiet=True):
        if not self.world_id:
            return False
        self.meta["last_played"] = time.time()
        self.meta["theme"] = self.s.theme
        data = self.world.to_dict(balls=True)
        data["coins"] = self.world.coins
        data["camera"] = [self.cam.x, self.cam.y, self.cam.zoom]
        data["stats"] = dict(self.world.stats)
        data["meta"] = self.meta
        ok = W.save_world(self.world_id, data)
        if thumb and self.app.overlay is None and not self.show_help:
            try:
                shot = self.app.screen.subsurface(self.cam.viewport.clip(self.app.screen.get_rect())).copy()
                pygame.image.save(pygame.transform.smoothscale(shot, (320, 200)),
                                  str(W.thumb_path(self.world_id)))
            except (pygame.error, ValueError, OSError):
                pass
        self.autosave_timer = 0.0
        if not quiet:
            self.toast("World saved" if ok else "Could not save the world!", ACCENT if ok else DANGER)
        return ok

    def rename_world(self, name):
        if self.meta:
            self.meta["name"] = name
            self.save_world(thumb=False)

    def to_menu(self):
        if self.net:
            self.net.close()
            self.net = None
        self.autosave()
        self.app.save_profile()
        self.app.set_scene(MenuScene(self.app))

    # ------------------------------------------------------------------
    # online: multiplayer rooms, cloud physics, sharing levels
    # ------------------------------------------------------------------
    def clear_balls(self):
        self.world.clear_balls()
        if self.net and self.net.connected:
            self.net.send_clear()

    def _can_go_online(self):
        if not N.Api(N.server_url(self.s)).configured:
            self.toast("Online isn't switched on in this copy of the game yet", WARN)
            return False
        if not N.multiplayer_available():
            self.toast("Multiplayer needs: pip install websocket-client", WARN)
            return False
        return True

    def host_room(self, cloud=False):
        if self.net or not self._can_go_online():
            return
        code = N.new_room_code()
        self.net = N.Session(self, N.server_url(self.s), code, self.s.player_name, creator=True, cloud=cloud)
        if not self.solo_cloud:
            self.toast(f"Hosting room {code}. Tell your friends the code!")
        self._build_right()

    def join_room(self, code):
        code = "".join(ch for ch in code.upper() if ch.isalnum())
        if self.net or not self._can_go_online():
            return
        if not 4 <= len(code) <= 8:
            self.toast("Room codes are 5 letters/numbers", WARN)
            return
        self.net = N.Session(self, N.server_url(self.s), code, self.s.player_name)
        self.toast(f"Joining room {code}...")
        self._build_right()

    def leave_room(self, quiet=False):
        if self.net:
            self.net.close()
            self.net = None
            self.world.rebuild_rings()  # recompute which ring each ball is in
            self.solo_cloud = False
            if not quiet:
                self.toast("Left the room")
            self._build_right()

    # --- PC / CLOUD physics switch ----------------------------------------------
    def _cloud_label(self):
        if self.net and self.net.cloud:
            p = (self.net.cloud_stats or {}).get("power")
            return f"CLOUD {p}%" if p is not None else "CLOUD"
        if self.solo_cloud:
            return "CLOUD..."
        return "PC"

    def _cloud_color(self):
        return (150, 90, 255) if (self.net and self.net.cloud) or self.solo_cloud else None

    def toggle_cloud(self):
        net = self.net
        if net and (net.cloud or self.solo_cloud):
            if self.solo_cloud:
                self.leave_room(quiet=True)   # balls carry on from where the cloud left them
            else:
                net.stop_cloud()
            self.toast("Physics: your PC")
        elif net:
            net.start_cloud()
        else:
            self.solo_cloud = True
            self._solo_was_cloud = False
            self.host_room(cloud=True)
            if self.net:
                self.toast("Physics: moving to the cloud...")
            else:
                self.solo_cloud = False

    def share_level(self):
        api = self.app.api()
        name = (self.share_name or (self.meta or {}).get("name") or "My level").strip()
        data = self.world.to_dict(balls=False)
        self.share_status = "Uploading..."

        def done(ok, res):
            if ok:
                ups = self.app.profile.setdefault("uploads", {})
                ups[res["id"]] = {"token": res["token"], "name": name}
                self.app.save_profile()
                self.share_status = f"Shared! Level ID: {res['id']}"
                self.toast(f"Level shared online as {name}")
            else:
                self.share_status = f"Upload failed: {res}"
            self._build_right()
        api.upload(name, self.s.player_name, self.share_desc, self.s.theme, data, done)
        self._build_right()

    def _online_widgets(self):
        wd = []
        net = self.net
        if net is None:
            wd += [
                Header("Multiplayer"),
                Label("Build together in the same world. Everyone sees the same blocks, settings and balls.", 13),
                Button("Host a room with this world", lambda: self.host_room(False), color=ACCENT, height=32),
                Button("Host with cloud physics", lambda: self.host_room(True), height=32,
                       tip="The server runs the physics so your PC only has to draw. Has limits on balls, "
                           "blocks and session length so nobody can overload the server."),
                Row(TextInput(lambda: self.join_code, lambda v: setattr(self, "join_code", v.upper()[:8]),
                              "CODE", 8, live=True),
                    Button("Join", lambda: self.join_room(self.join_code), height=38)),
                Label("Joining replaces what you see with the host's world.", 12),
            ]
        else:
            wd += [Header(f"Room {net.code}", ACCENT2), Label(lambda: net.status, 13)]
            for pid, p in list(net.players.items()):
                tag = " (you)" if pid == net.my_id else ""
                wd.append(Label(f"- {p['name']}{tag}", 14, p["color"]))
            if net.connected:
                if net.cloud:
                    wd += [Header("Cloud physics"),
                           Label(lambda: self._cloud_text(), 13, lambda: WARN if (net.cloud_stats or {}).get("overloaded")
                                 else TEXT),
                           Button("Stop cloud physics", net.stop_cloud, height=30)]
                else:
                    wd += [Button("Start cloud physics", net.start_cloud, height=30,
                                  tip="Let the server simulate this room (with limits).")]
            wd += [Label("Press Enter or T to chat. Share the room code with friends.", 12),
                   Button("Leave room", self.leave_room, color=(90, 30, 45), text_color=TEXT, height=30)]
        wd += [
            Header("Share this level"),
            TextInput(lambda: self.share_name or (self.meta or {}).get("name", ""),
                      lambda v: setattr(self, "share_name", v), "Level name", 40, live=True),
            TextInput(lambda: self.share_desc, lambda v: setattr(self, "share_desc", v), "Short description", 120,
                      live=True),
            Button("Upload level", self.share_level, color=ACCENT2, height=32,
                   tip="Uploads the blocks and settings (not the balls). Browse levels from the main menu: ONLINE."),
            Label(lambda: self.share_status, 13),
        ]
        return wd

    def _cloud_text(self):
        st = self.net.cloud_stats if self.net else None
        if not st:
            return "Waiting for the server..."

        def mins(sec):
            sec = int(sec)
            return f"{sec // 3600}h {sec % 3600 // 60:02d}m" if sec >= 3600 else f"{sec // 60} min"
        energy = st.get("energy", 100)
        bar = "#" * round(energy / 10) + "-" * (10 - round(energy / 10))
        txt = (f"Cloud power: {st.get('power', 100)}%  (up to {st.get('cap', st['max']):,} balls)\n"
               f"Why: {st.get('why') or 'starting up'}\n"
               f"Energy: [{bar}] {energy}%\n"
               f"Lasts {mins(st.get('left', 0))} at this pace, {mins(st.get('calm', 0))} if you take it easy\n"
               f"Server load right now: {st.get('load', 0)}%   Balls: {st['balls']:,}")
        if self.net.spawn_queue:
            txt += f"\nSending balls to the cloud... {len(self.net.spawn_queue):,} to go"
        if st.get("overloaded"):
            txt += "\nOverloaded! Removing balls to keep up."
        return txt

    def toast(self, text, color=ACCENT):
        self.toasts.append([text, color, 3.0])
        if len(self.toasts) > 5:
            self.toasts.pop(0)

    def next_portal_channel(self):
        counts = {}
        for b in self.world.blocks:
            if b.alive and b.key == "portal":
                counts[int(b.channel)] = counts.get(int(b.channel), 0) + 1
        for ch in range(6):
            if counts.get(ch, 0) == 1:
                return ch
        for ch in range(6):
            if counts.get(ch, 0) == 0:
                return ch
        return 0

    def snap(self, x, y):
        if self.s.snap_to_grid:
            return round(x / 25) * 25, round(y / 25) * 25
        return x, y

    def make_block(self, key, start, end):
        """Create the block that a click (start==end) or drag would place."""
        cls = B.REGISTRY[key]
        sx, sy = start
        dx, dy = end[0] - sx, end[1] - sy
        L = math.hypot(dx, dy)
        dragged = L > 10 / self.cam.zoom
        if not dragged:
            blk = B.create(key, sx, sy)
            if cls.rotatable:
                blk.angle = self.place_angle if key != "cannon" else self.place_angle - 0.6
            return blk
        ang = math.atan2(dy, dx)
        if key == "laser":
            return B.create(key, sx, sy, angle=ang, length=clamp(L, 50, 2000))
        if key == "cannon":
            return B.create(key, sx, sy, angle=ang, power=clamp(L / 12, 1, 30))
        if not cls.resizable:
            return B.create(key, sx, sy, angle=ang if cls.rotatable else 0.0)
        if cls.shape == "circle":
            return B.create(key, sx, sy, r=clamp(L, 6, 900))
        return B.create(key, sx + dx / 2, sy + dy / 2, angle=ang, w=clamp(L, 6, 3000))

    # ------------------------------------------------------------------
    # input
    # ------------------------------------------------------------------
    def over_ui(self, pos):
        if not self.show_ui:
            return False
        return (self.top_rect.collidepoint(pos) or self.left_rect.collidepoint(pos)
                or self.right_rect.collidepoint(pos))

    def event(self, e):
        ui = self.ui
        if self.show_help and e.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
            self.show_help = False
            return
        if e.type == pygame.KEYDOWN:
            self.key(e)
            return
        if e.type == pygame.MOUSEWHEEL:
            pos = pygame.mouse.get_pos()
            if self.over_ui(pos):
                return
            mods = pygame.key.get_mods()
            if mods & (pygame.KMOD_SHIFT | pygame.KMOD_CTRL):
                step = math.radians(15) * (1 if e.y > 0 else -1)
                if self.tool[0] == "block":
                    self.place_angle += step
                elif self.selected and self.selected.rotatable:
                    self.selected.angle += step
            else:
                self.cam.zoom_at(pos[0], pos[1], 1.12 if e.y > 0 else 1 / 1.12)
            return
        if self.show_ui and hasattr(e, "pos") and self.over_ui(e.pos):
            if e.type == pygame.MOUSEBUTTONDOWN:
                if self.top_rect.collidepoint(e.pos):
                    for w in self.top_widgets:
                        if w.event(e, ui):
                            return
                elif self.left_rect.collidepoint(e.pos):
                    if not self.left_tabs.event(e, ui):
                        self.left_list.event(e, ui)
                else:
                    if not self.right_tabs.event(e, ui):
                        self.right_list.event(e, ui)
                return
            if e.type != pygame.MOUSEBUTTONUP:
                return
        if e.type == pygame.MOUSEBUTTONDOWN:
            self.mouse_down(e)
        elif e.type == pygame.MOUSEBUTTONUP:
            self.mouse_up(e)
        elif e.type == pygame.MOUSEMOTION:
            self.mouse_move(e)

    def key(self, e):
        k = e.key
        mods = pygame.key.get_mods()
        ctrl = mods & (pygame.KMOD_CTRL | pygame.KMOD_META)
        if k == pygame.K_ESCAPE:
            if self.selected or self.tool[0] != "tool" or self.tool[1] != "select":
                self.select(None)
                self.set_tool(("tool", "select"))
            else:
                self.to_menu()
        elif k == pygame.K_SPACE:
            self.toggle_pause()
        elif k == pygame.K_n:
            self.world.step_once = True
        elif ctrl and k == pygame.K_z:
            self.undo()
        elif ctrl and k == pygame.K_s:
            if self.world_id:
                self.save_world(quiet=False)
            else:
                self.save_file(SAVE_DIR / "slot1.json")
        elif ctrl and k == pygame.K_l:
            self.load_file(SAVE_DIR / "slot1.json")
        elif ctrl and k == pygame.K_d:
            self.duplicate_selected()
        elif k == pygame.K_F5:
            self.save_file(SAVE_DIR / "slot1.json")
        elif k == pygame.K_F9:
            self.load_file(SAVE_DIR / "slot1.json")
        elif k in (pygame.K_DELETE, pygame.K_BACKSPACE):
            self.delete_selected()
        elif k in (pygame.K_q, pygame.K_e):
            step = math.radians(15) * (-1 if k == pygame.K_q else 1)
            if self.selected and self.selected.alive and self.selected.rotatable:
                self.selected.angle += step
            else:
                self.place_angle += step
        elif k == pygame.K_b:
            self.spawn_center(self.s.burst_size)
        elif k == pygame.K_r and not ctrl:
            self.rain = not self.rain
            self.toast("Ball rain " + ("on" if self.rain else "off"))
            if self.left_tab == "Balls":
                self._build_left()
        elif k == pygame.K_c:
            self.clear_balls()
        elif k in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_t) and self.net and self.net.connected:
            self.chat_input.focus(self.ui)
        elif k == pygame.K_g:
            self.s.snap_to_grid = not self.s.snap_to_grid
            self.toast("Snap to grid " + ("on" if self.s.snap_to_grid else "off"))
        elif k == pygame.K_TAB:
            self.show_ui = not self.show_ui
            self.resize()
        elif k == pygame.K_o:
            self.app.open_settings()
        elif k in (pygame.K_h, pygame.K_F1):
            self.show_help = not self.show_help
        elif k == pygame.K_HOME:
            self.fit_camera()
        elif k in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
            self._build_top_speed(1)
        elif k in (pygame.K_MINUS, pygame.K_KP_MINUS):
            self._build_top_speed(-1)
        elif pygame.K_1 <= k <= pygame.K_9:
            i = k - pygame.K_1
            tab = self.left_tab
            if tab == "Tools" and i < len(TOOLS):
                self.set_tool(("tool", TOOLS[i][0]))
            elif tab == "Balls" and i < len(BALL_ORDER):
                self.set_tool(("ball", BALL_ORDER[i]))
            elif tab in B.CATEGORIES and i < len(B.CATEGORIES[tab]):
                self.set_tool(("block", B.CATEGORIES[tab][i]))

    def _build_top_speed(self, d):
        i = min(range(len(SPEEDS)), key=lambda k: abs(SPEEDS[k] - self.s.time_speed))
        self.s.time_speed = SPEEDS[clamp(i + d, 0, len(SPEEDS) - 1)]

    def mouse_down(self, e):
        wx, wy = self.cam.s2w(*e.pos)
        self.mouse_w = self.prev_mouse_w = (wx, wy)
        if e.button == 2:
            self.drag = ("pan", e.pos[0], e.pos[1], self.cam.x, self.cam.y)
            return
        if e.button == 3:
            blk = self.world.block_at(wx, wy, 4 / self.cam.zoom)
            if blk:
                self.world.remove_block(blk)
                self.world.blocks = [b for b in self.world.blocks if b.alive]
                self.push_undo(("remove", [blk]))
                self.world.fx.burst(blk.x, blk.y, (200, 200, 220), 10, 2, 2, 20)
                self.world.sound("pop", 3)
                if blk is self.selected:
                    self.select(None)
            else:
                self.rmb = True
            return
        if e.button != 1:
            return
        self.lmb = True
        kind, name = self.tool
        if kind == "block":
            self.place_start = self.snap(wx, wy)
        elif kind == "ball":
            self._start_spray()
        elif name == "select":
            blk = self.world.block_at(wx, wy, 6 / self.cam.zoom)
            if blk:
                self.select(blk)
                self.drag = ("move", blk, wx - blk.x if blk.key != "mover" else wx - blk.ox,
                             wy - blk.y if blk.key != "mover" else wy - blk.oy, blk.to_dict(), False)
            else:
                if self.selected:
                    self.select(None)
                self.drag = ("pan", e.pos[0], e.pos[1], self.cam.x, self.cam.y)
        elif name == "spawn":
            self._start_spray()
        elif name == "grab":
            rad = max(30, 40 / self.cam.zoom)
            self.grabbed = []
            for b in self.world.balls:
                if math.hypot(b.x - wx, b.y - wy) < rad + b.r:
                    b.grabbed = True
                    self.grabbed.append((b, b.x - wx, b.y - wy))
                    if len(self.grabbed) > 60:
                        break
        elif name == "eraser":
            self.erase_batch = []
        elif name == "explode":
            if self.net and self.net.connected:
                self.net.send_boom(wx, wy, 170, 15)
            if not (self.net and self.net.cloud):
                self.world.explode(wx, wy, 170, 15)

    def mouse_up(self, e):
        wx, wy = self.cam.s2w(*e.pos)
        if e.button == 3:
            self.rmb = False
            return
        if e.button == 2:
            self.drag = None
            return
        if e.button != 1:
            return
        self.lmb = False
        if self.drag and self.drag[0] == "move" and self.drag[5]:
            self.push_undo(("state", self.drag[1], self.drag[4]))
        self.drag = None
        if self.tool[0] == "block" and self.place_start:
            end = self.snap(wx, wy)
            blk = self.make_block(self.tool[1], self.place_start, end)
            if blk.key == "portal":
                blk.channel = self.next_portal_channel()
            self.world.add_block(blk)
            self.push_undo(("add", [blk]))
            self.world.fx.burst(blk.x, blk.y, (180, 220, 255), 8, 2, 2, 16, 0)
            self.world.sound("place", 4)
            self.select(blk)
            self.place_start = None
        if self.grabbed:
            vx, vy = self.mouse_vel
            for b, _, _ in self.grabbed:
                b.grabbed = False
                b.vx, b.vy = clamp(vx, -40, 40), clamp(vy, -40, 40)
            self.grabbed = []
        if self.erase_batch:
            self.push_undo(("remove", self.erase_batch))
        self.erase_batch = None

    def mouse_move(self, e):
        wx, wy = self.cam.s2w(*e.pos)
        self.mouse_w = (wx, wy)
        if self.drag:
            if self.drag[0] == "pan":
                _, sx, sy, cx, cy = self.drag
                self.cam.x = cx - (e.pos[0] - sx) / self.cam.zoom
                self.cam.y = cy - (e.pos[1] - sy) / self.cam.zoom
            elif self.drag[0] == "move":
                _, blk, ox, oy, snap, _ = self.drag
                nx, ny = self.snap(wx - ox, wy - oy)
                blk.move_to(nx, ny)
                self.drag = ("move", blk, ox, oy, snap, True)

    def _start_spray(self):
        self.spray_t = 0.0
        if pygame.key.get_mods() & pygame.KMOD_SHIFT:
            self._spawn_at_mouse(self.s.burst_size, max(self.s.spray_size, 40.0, self._spread(self.s.burst_size)))
        else:
            self._spawn_at_mouse(1)

    def _spawn_at_mouse(self, n=1, radius=None):
        n = self._room_left(n)
        wx, wy = self.mouse_w
        kind = self.tool[1] if self.tool[0] == "ball" else self.ball_kind
        radius = self.s.spray_size if radius is None else radius
        mvx, mvy = self.mouse_vel
        out = []
        for _ in range(n):
            a = random.uniform(0, TAU)
            sp = random.uniform(0, 1.5)
            d = math.sqrt(random.random()) * radius + random.uniform(0, 4)
            pa = random.uniform(0, TAU)
            out.append((wx + math.cos(pa) * d, wy + math.sin(pa) * d,
                        math.cos(a) * sp + mvx * 0.5, math.sin(a) * sp + mvy * 0.5, kind))
        self.emit_spawns(out)

    def _room_left(self, n):
        """Don't build a huge list of balls that the ball limit would throw away anyway."""
        if self.net and self.net.cloud:
            cap = (self.net.cloud_stats or {}).get("cap") or (self.net.limits or {}).get("maxBalls", 2000)
            return min(n, cap)
        if self.s.limit_action == "Delete Oldest" or self.s.unlimited_balls:
            return min(n, int(min(self.s.ball_limit(), 100000)))
        return max(0, min(n, int(self.s.ball_limit()) - len(self.world.balls)))

    def _spread(self, n, inside_ring=False):
        """How wide to spread n balls so a big spawn isn't one giant pile."""
        if n <= 20:
            return 3.0
        r = self.s.ball_radius * 1.15 * math.sqrt(n)
        if inside_ring and self.world.rings:
            r = min(r, max(3.0, self.world.rings[0].radius - self.s.ball_radius * 2))
        return r

    def spawn_center(self, n):
        n = self._room_left(n)
        spread = self._spread(n, inside_ring=True)
        out = []
        for _ in range(n):
            a = random.uniform(0, TAU)
            sp = self.s.spawn_speed * random.uniform(0.66, 1.33)
            d = math.sqrt(random.random()) * spread
            pa = random.uniform(0, TAU)
            out.append((math.cos(pa) * d, math.sin(pa) * d, math.cos(a) * sp, math.sin(a) * sp, self.s.spawn_type))
        self.emit_spawns(out)

    def _rain(self, frames):
        self.rain_t += frames * self.s.rain_rate / 60.0
        n = min(int(self.rain_t), 100)
        if not n:
            return
        self.rain_t -= n
        x0, y0, x1, _ = self.cam.visible_rect()
        kind = self.ball_kind
        self.emit_spawns([(random.uniform(x0, x1), y0 + 5, random.uniform(-0.5, 0.5),
                           random.uniform(0, 2), kind) for _ in range(n)])

    def emit_spawns(self, items):
        """Spawn balls locally (and tell the room/cloud about them when online)."""
        net = self.net
        if net is not None and net.connected:
            net.send_spawns(items)
            if net.cloud:
                return  # the cloud simulates them
        for x, y, vx, vy, kind in items:
            if not self.world.spawn_ball(x, y, vx, vy, kind=kind):
                break

    # ------------------------------------------------------------------
    # update & draw
    # ------------------------------------------------------------------
    def update(self, frames, dt):
        if dt > 0:
            self.fps = self.fps * 0.95 + (1.0 / dt) * 0.05
        if self.world_id:
            self.meta["playtime"] = self.meta.get("playtime", 0.0) + dt
            self.autosave_timer += dt
            if self.s.autosave and self.autosave_timer > 120:
                self.save_world()
        w = self.world
        mx, my = pygame.mouse.get_pos()
        if not self.over_ui((mx, my)) or self.lmb or self.rmb:
            self.mouse_w = self.cam.s2w(mx, my)
        f = max(frames, 0.01)
        self.mouse_vel = ((self.mouse_w[0] - self.prev_mouse_w[0]) / f,
                          (self.mouse_w[1] - self.prev_mouse_w[1]) / f)
        self.prev_mouse_w = self.mouse_w
        wx, wy = self.mouse_w

        # keyboard panning
        keys = pygame.key.get_pressed()
        pan = 12 * frames / self.cam.zoom
        if not pygame.key.get_mods() & (pygame.KMOD_CTRL | pygame.KMOD_META):
            if keys[pygame.K_a] or keys[pygame.K_LEFT]:
                self.cam.x -= pan
            if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
                self.cam.x += pan
            if keys[pygame.K_w] or keys[pygame.K_UP]:
                self.cam.y -= pan
            if keys[pygame.K_s] or keys[pygame.K_DOWN]:
                self.cam.y += pan

        kind, name = self.tool
        if self.lmb:
            if kind == "ball" or name == "spawn":
                self.spray_t += frames * self.s.spray_rate / 60.0
                n = int(self.spray_t)
                if n:
                    self.spray_t -= n
                    self._spawn_at_mouse(min(n, 100))
            elif name == "grab":
                for b, ox, oy in self.grabbed:
                    b.x, b.y = wx + ox, wy + oy
                    b.vx, b.vy = self.mouse_vel
                    b.history.clear()
            elif name == "eraser" and self.erase_batch is not None:
                rad = 18 / self.cam.zoom
                blk = w.block_at(wx, wy, rad)
                if blk:
                    w.remove_block(blk)
                    w.blocks = [b for b in w.blocks if b.alive]
                    self.erase_batch.append(blk)
                    w.fx.burst(blk.x, blk.y, (200, 200, 220), 10, 2, 2, 20)
                    if blk is self.selected:
                        self.select(None)
                for b in w.balls:
                    if math.hypot(b.x - wx, b.y - wy) < rad + b.r:
                        w.kill_ball(b, "pop")
            elif name in ("attract", "repel"):
                self._force(wx, wy, 1 if name == "attract" else -1, frames)
        if self.rmb:
            self._force(wx, wy, 1, frames)
        if self.rain:
            self._rain(frames)

        w.update(frames)
        if self.net:
            self.net.tick(dt)
            if self.solo_cloud:
                if self.net.cloud:
                    self._solo_was_cloud = True
                elif self.net.cloud_refused or (self._solo_was_cloud and self.net.connected):
                    # the server said no, or ended the session: back to PC physics
                    self.leave_room(quiet=True)
            if self.net and self.net.ended:
                self.net.close()
                self.net = None
                self._build_right()
            elif self.net and self.right_tab == "Online" and self.ui.focus is None:
                self._online_refresh -= dt
                if self._online_refresh <= 0:
                    self._online_refresh = 1.0
                    self._build_right()
        self.app.achievements.update(w, frames)
        for text, color in w.toasts:
            self.toast(text, color)
        w.toasts.clear()
        for t in self.toasts:
            t[2] -= dt
        self.toasts = [t for t in self.toasts if t[2] > 0]
        if self.selected is not None and not self.selected.alive:
            self.select(None)
        if self._inspected is not self.selected and self.right_tab == "Inspect":
            self._build_right()
        # re-layout dynamic panels (labels can change height)
        self.right_list.layout(self.right_list.rect)
        self.left_list.layout(self.left_list.rect)

    def _force(self, wx, wy, sign, frames):
        R = 300
        for b in self.world.balls:
            dx, dy = wx - b.x, wy - b.y
            d = math.hypot(dx, dy)
            if 4 < d < R:
                a = sign * 1.2 * (1 - d / R) * frames
                b.vx += dx / d * a
                b.vy += dy / d * a

    def _draw_overlay(self, surf, cam):
        """Ghost previews and selection, drawn in world space."""
        if self.selected and self.selected.alive:
            self.selected.draw_selection(surf, cam, ACCENT)
        if self.net:
            for pid, (x, y, tool, age) in self.net.cursors.items():
                if age > 5:
                    continue
                p = self.net.players.get(pid)
                if not p:
                    continue
                sx, sy = cam.w2s(x, y)
                col = p["color"]
                pygame.draw.polygon(surf, col, [(sx, sy), (sx, sy + 16), (sx + 4, sy + 12), (sx + 11, sy + 12)])
                self.ui.text(surf, p["name"], (sx + 12, sy + 12), 12, col, True)
        kind, name = self.tool
        mx, my = pygame.mouse.get_pos()
        if not cam.viewport.collidepoint(mx, my) and not self.place_start:
            return
        if kind == "block":
            start = self.place_start or self.snap(*self.mouse_w)
            end = self.snap(*self.mouse_w) if self.place_start else start
            ghost = self.make_block(name, start, end)
            ghost.t = self.world.time
            ghost.draw(surf, cam)
            ghost.draw_selection(surf, cam, (255, 255, 255))
            if self.place_start:
                pygame.draw.line(surf, (255, 255, 255), cam.w2s(*start), cam.w2s(*end), 1)
        elif name == "eraser" or name in ("attract", "repel", "grab") or kind == "ball" or name == "spawn":
            c = (mx, my)
            if name == "eraser":
                pygame.draw.circle(surf, (255, 110, 150), c, 18, 2)
            elif name in ("attract", "repel"):
                col = (0, 255, 204) if name == "attract" else (255, 51, 85)
                pygame.draw.circle(surf, mix(BG, col, 0.5), c, 300 * cam.zoom, 1)
                pygame.draw.circle(surf, col, c, 6, 2)
            elif name == "grab":
                pygame.draw.circle(surf, (255, 204, 0), c, max(30 * cam.zoom, 40), 1)
            else:
                k = self.tool[1] if kind == "ball" else self.ball_kind
                col = BALL_TYPES[k]["color"] or ACCENT
                pygame.draw.circle(surf, col, c, max(3, self.s.ball_radius * BALL_TYPES[k]["size"] * cam.zoom), 1)
        if self.rmb:
            pygame.draw.circle(surf, (0, 255, 204), (mx, my), 300 * cam.zoom, 1)

    def draw(self, surf):
        self.renderer.draw(surf, self.world, self.cam, self._draw_overlay)
        vp = self.cam.viewport
        # toasts
        y = vp.y + 12
        for text, color, life in self.toasts:
            f = self.ui.font(15, True)
            tw = f.size(text)[0] + 28
            r = pygame.Rect(vp.centerx - tw // 2, y, tw, 32)
            a = clamp(life / 0.4, 0, 1)
            pygame.draw.rect(surf, mix(BG, (16, 16, 28), a), r, border_radius=8)
            pygame.draw.rect(surf, mix(BG, color, a), r, 1, border_radius=8)
            self.ui.text(surf, text, r.center, 15, mix(BG, color, a), True, "center")
            y += 38
        if self.world.paused:
            self.ui.text(surf, "PAUSED", (vp.centerx, vp.bottom - 60), 28, WARN, True, "center")
        if self.net:
            self._draw_chat(surf, vp)
        # hint line
        self._draw_hint(surf, vp)
        if self.show_ui:
            self._draw_panels(surf)
        else:
            self.ui.text(surf, "Tab: show UI", (12, 10), 13, TEXT_DIM)
            if self.s.show_fps:
                self.ui.text(surf, f"{self.fps:.0f} FPS", (surf.get_width() - 12, 10), 14, ACCENT, True, "topright")
        if self.show_help:
            self._draw_help(surf)

    def _draw_chat(self, surf, vp):
        ui = self.ui
        y = vp.bottom - 60
        for name, text, color, age in reversed(self.net.chat[-8:]):
            if age > 12 and self.ui.focus is not self.chat_input:
                continue
            a = 1.0 if age < 10 else max(0.0, 1 - (age - 10) / 2)
            r = ui.text(surf, f"{name}: ", (vp.x + 12, y), 14, mix(BG, color, a), True)
            ui.text(surf, text, (r.right, y), 14, mix(BG, TEXT, a))
            y -= 20
        if self.ui.focus is self.chat_input:
            self.chat_input.layout(vp.x + 10, vp.bottom - 40, min(520, vp.w - 20))
            self.chat_input.draw(surf, ui)
        else:
            ui.text(surf, "Enter or T to chat", (vp.x + 12, vp.bottom - 44), 12, TEXT_DIM)

    def _draw_hint(self, surf, vp):
        kind, name = self.tool
        if kind == "block":
            cls = B.REGISTRY[name]
            if cls.shape == "circle" and cls.resizable:
                how = "Click to place, drag to set its size"
            elif cls.resizable and cls.shape == "rect":
                how = "Click to place, drag to draw it at any length & angle"
            else:
                how = "Click to place, drag to aim"
            hint = f"{cls.name}: {how}.{'  Q/E rotate -' if cls.rotatable else ''} right-click deletes"
        elif kind == "ball":
            hint = f"{BALL_TYPES[name]['name']} ball: click or hold to spawn"
        else:
            hint = TOOL_INFO[name][1]
        self.ui.text(surf, hint, (vp.x + 12, vp.bottom - 24), 13, TEXT_DIM)
        wx, wy = self.mouse_w
        self.ui.text(surf, f"x {int(wx)}  y {int(wy)}  zoom {self.cam.zoom:.2f}",
                     (vp.right - 12, vp.bottom - 24), 13, TEXT_DIM, False, "topright")

    def _draw_panels(self, surf):
        ui = self.ui
        W, H = surf.get_size()
        w = self.world
        # top bar
        pygame.draw.rect(surf, (14, 14, 24), self.top_rect)
        pygame.draw.line(surf, BORDER, (0, TOP_H - 1), (W, TOP_H - 1))
        ui.text(surf, "FUN BALL GAME", (16, 9), 20, ACCENT, True)
        sub = self.meta["name"] if self.meta else "quick play (not saved)"
        if self.net and self.net.connected:
            sub = f"room {self.net.code} - {len(self.net.players)} online" + (" - CLOUD" if self.net.cloud else "")
        f11 = ui.font(11, True)
        while f11.size(sub)[0] > 162 and len(sub) > 4:
            sub = sub[:-2]
        ui.text(surf, sub, (18, 33), 11, ACCENT2 if self.meta else TEXT_DIM, True)
        x = 188
        limit = self.s.ball_limit()
        stats = [("BALLS" if not self.s.unlimited_balls else "BALLS (NO LIMIT)",
                  str(len(w.balls)) if self.s.unlimited_balls else f"{len(w.balls)}/{self.s.max_balls}",
                  DANGER if len(w.balls) >= limit else TEXT)]
        if self.s.show_fps:
            stats.append(("FPS", f"{self.fps:.0f}",
                          ACCENT if self.fps > 50 else (WARN if self.fps > 30 else DANGER)))
        stats += [("COINS", str(w.coins), (255, 215, 60)),
                  ("ESCAPES", str(w.stats["escapes"]), TEXT),
                  ("BLOCKS", str(len(w.blocks)), TEXT)]
        for label, val, col in stats:
            lw = max(ui.font(18, True).size(val)[0], ui.font(10, True).size(label)[0])
            if x + lw > self.top_stats_right:
                break
            ui.text(surf, label, (x, 9), 10, TEXT_DIM, True)
            ui.text(surf, val, (x, 22), 18, col, True)
            x += max(52, lw + 18)
        for b in self.top_widgets:
            b.hover(ui)
            b.draw(surf, ui)

        # left
        pygame.draw.rect(surf, PANEL, self.left_rect)
        pygame.draw.line(surf, BORDER, self.left_rect.topright, self.left_rect.bottomright)
        self.left_tabs.draw(surf, ui)
        self.left_list.draw(surf, ui)
        info = pygame.Rect(self.left_rect.x + 8, self.left_rect.bottom - 124, LEFT_W - 16, 116)
        panel(surf, info, (16, 16, 26))
        kind, name = self.tool
        if kind == "block":
            cls = B.REGISTRY[name]
            title, desc = cls.name, cls.desc
            icon = self._icon_for_block(name)
        elif kind == "ball":
            title, desc = BALL_TYPES[name]["name"] + " Ball", BALL_TYPES[name]["desc"]
            icon = self._icon_for_ball(name)
        else:
            title, desc = TOOL_INFO[name]
            icon = next(t[3] for t in TOOLS if t[0] == name)
        ir = pygame.Rect(info.x + 8, info.y + 8, 40, 40)
        pygame.draw.rect(surf, PANEL_LIGHT, ir, border_radius=6)
        prev = surf.get_clip()
        surf.set_clip(ir)
        icon(surf, ir)
        surf.set_clip(prev)
        ui.text(surf, "SELECTED", (info.x + 56, info.y + 10), 10, TEXT_DIM, True)
        ui.text(surf, title, (info.x + 56, info.y + 24), 15, ACCENT, True)
        for i, line in enumerate(wrap(ui.font(12), desc, info.w - 16)[:4]):
            ui.text(surf, line, (info.x + 8, info.y + 54 + i * 15), 12, TEXT)

        # right
        pygame.draw.rect(surf, PANEL, self.right_rect)
        pygame.draw.line(surf, BORDER, self.right_rect.topleft, self.right_rect.bottomleft)
        self.right_tabs.draw(surf, ui)
        self.right_list.draw(surf, ui)
        for t in (self.left_tabs, self.right_tabs):
            for name_, r in zip(t.names, t._rects()):
                if r.collidepoint(ui.mouse):
                    ui.set_tip(t, name_)

    def _draw_help(self, surf):
        W, H = surf.get_size()
        shade = pygame.Surface((W, H), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 170))
        surf.blit(shade, (0, 0))
        r = pygame.Rect(W // 2 - 360, H // 2 - 265, 720, 530)
        panel(surf, r, (16, 16, 26), ACCENT)
        self.ui.text(surf, "CONTROLS", (r.centerx, r.y + 22), 22, ACCENT, True, "center")
        y = r.y + 50
        for key, desc in HELP_LINES:
            if desc is None:
                y += 4
                self.ui.text(surf, key, (r.x + 24, y), 13, ACCENT2, True)
            else:
                self.ui.text(surf, key, (r.x + 24, y), 14, WARN, True)
                self.ui.text(surf, desc, (r.x + 230, y), 14, TEXT)
            y += 22
        self.ui.text(surf, "Press any key to close", (r.centerx, r.bottom - 22), 13, TEXT_DIM, False, "center")


class SettingsOverlay:
    """The settings screen. Opens over the menu or the game."""

    TABS = ["Display", "Performance", "Gameplay", "Audio", "Online"]

    def __init__(self, app):
        self.app = app
        self.tab = "Display"
        self.test_status = ""
        self.test_color = TEXT_DIM
        self.list = ScrollList()
        self.build()

    def rect(self):
        W, H = self.app.screen.get_size()
        h = min(640, H - 60)
        return pygame.Rect(W // 2 - 340, H // 2 - h // 2, 680, h)

    def _set_tab(self, t):
        self.tab = t
        self.build()

    def _bind(self, attr):
        s = self.app.settings
        return (lambda: getattr(s, attr)), (lambda v: setattr(s, attr, v))

    def _slider(self, label, attr, lo, hi, step, tip=None, fmt=None):
        g, st = self._bind(attr)
        if isinstance(getattr(self.app.settings, attr), int):
            st_int = st
            st = lambda v: st_int(int(v))  # noqa: E731
        return Slider(label, g, st, lo, hi, step, fmt, tip)

    def _toggle(self, label, attr, tip=None):
        g, st = self._bind(attr)
        return Toggle(label, g, st, tip)

    def _update_action(self):
        up = self.app.updater
        if up.state == "installed":
            self.app.restart_for_update()
        elif up.state == "available":
            up.install()
        else:
            up.check(install=True)

    def _test(self):
        self.test_status, self.test_color = "Testing...", TEXT_DIM

        def done(ok, data):
            if ok and isinstance(data, dict) and data.get("game") == "fun-ball-game":
                lim = data.get("limits", {})
                self.test_status = (f"Connected! Cloud limits: {lim.get('maxBalls')} balls, "
                                    f"{lim.get('maxBlocks')} blocks, {lim.get('energyMinutes')} min energy bar, "
                                    f"{lim.get('maxCloudRooms')} cloud rooms at once.")
                self.test_color = ACCENT
            else:
                self.test_status = data if not ok else "That address isn't a Fun Ball Game server."
                self.test_color = DANGER
        self.app.api().health(done)

    def _fullscreen(self, v):
        if v != self.app.fullscreen:
            self.app.toggle_fullscreen()

    def _reset(self):
        self.app.settings.reset(keep_prefs=False)
        scene = self.app.scene
        if isinstance(scene, SandboxScene):
            scene.world.rings = []
            scene.world.rebuild_rings()
        self.build()

    def build(self):
        s = self.app.settings
        r = self.rect()
        self.tabs = Tabs(self.TABS, lambda: self.tab, self._set_tab, 14)
        self.tabs.layout(r.x + 20, r.y + 58, r.w - 40)
        if self.tab == "Display":
            wd = [
                Header("Frame rate"),
                Choice("FPS limit", FPS_OPTIONS, lambda: s.fps_limit, lambda v: setattr(s, "fps_limit", v),
                       "How many frames per second to draw. Unlimited = as fast as your PC can go.",
                       names=lambda v: "Unlimited" if v == 0 else f"{v} FPS"),
                NumberInput("Custom FPS limit (0 = unlimited)", lambda: s.fps_limit,
                            lambda v: setattr(s, "fps_limit", v), 0, 1000,
                            "Type any frame-rate cap and press Enter."),
                self._toggle("Show FPS counter", "show_fps"),
                Label("Physics runs at the same speed whatever your FPS, so a higher FPS just "
                      "makes everything smoother.", 13),
                Header("Screen"),
                Toggle("Fullscreen (F11)", lambda: self.app.fullscreen, self._fullscreen),
                Header("Look"),
                Choice("Colour scheme", list(COLOR_SCHEMES), lambda: s.color_scheme,
                       lambda v: setattr(s, "color_scheme", v)),
                self._toggle("Glow", "glow"),
                self._toggle("Motion trails", "trails"),
                self._toggle("Particles", "particles"),
                self._toggle("Screen shake", "screen_shake"),
                self._toggle("Background grid", "show_grid"),
            ]
        elif self.tab == "Performance":
            wd = [
                Header("Quality"),
                self._slider("Full detail up to (balls)", "detail_threshold", 100, 10000, 50,
                             "Above this many balls, glow and shading switch off to keep the FPS up."),
                self._slider("Max particles", "max_particles", 0, 20000, 100,
                             "Sparks, smoke and shards. Fewer = faster."),
                self._slider("Trail length", "trail_length", 2, 40, 1),
                Header("Physics"),
                self._slider("Physics substeps", "substeps", 1, 8, 1,
                             "More substeps = more accurate collisions, but slower."),
                self._toggle("Ball-to-ball collisions", "ball_collisions",
                             "Turning this off makes huge swarms MUCH faster."),
                Label("Tip: for thousands of balls, turn off ball collisions and glow, and "
                      "lower the substeps.", 13),
            ]
        elif self.tab == "Gameplay":
            wd = [
                Header("Ball limit"),
                self._slider("Max balls", "max_balls", 10, 5000, 10),
                NumberInput("Custom ball limit", lambda: s.max_balls, lambda v: setattr(s, "max_balls", v),
                            1, 1_000_000, "Type any number and press Enter."),
                self._toggle("Unlimited balls", "unlimited_balls",
                             "No limit at all. It will get slow eventually!"),
                Choice("When the limit is reached", LIMIT_ACTIONS, lambda: s.limit_action,
                       lambda v: setattr(s, "limit_action", v)),
                Header("Spawning"),
                self._slider("Balls per escape", "balls_per_escape", 0, 10, 1),
                self._slider("Free ball lifetime (s)", "escaped_lifetime", 0, 120, 1,
                             "Escaped balls disappear after this long. 0 = never."),
                Header("Saving"),
                self._toggle("Autosave every 2 minutes", "autosave",
                             "Worlds always save when you leave. This also saves them every 2 minutes."),
                Header("Updates"),
                Label(f"You have version {__version__}.", 13),
                self._toggle("Auto-update", "auto_update",
                             "When the game starts, download and install new versions from GitHub."),
                Row(Button("Check for updates", lambda: self.app.updater.check(install=self.app.settings.auto_update)),
                    Button(lambda: "Restart now" if self.app.updater.state == "installed" else "Install update",
                           self._update_action)),
                Label(lambda: self.app.updater.message, 13),
            ]
        elif self.tab == "Online":
            wd = [
                Header("You"),
                TextInput(lambda: s.player_name, lambda v: setattr(s, "player_name", v[:20]), "Your name", 20,
                          tip="Shown to other players and on levels you share"),
                Label("To play with friends: open a world, go to the Online tab and press Host. Give your "
                      "friends the 5-letter code, and they type it in to join.", 13),
                Row(Button("Test connection", self._test), Spacer(0)),
                Label(lambda: self.test_status, 13, lambda: self.test_color),
                Header("Advanced", TEXT_DIM),
                Label("Leave this empty to use the game's server. Only fill it in to use a different one.", 12),
                TextInput(lambda: s.server_url, lambda v: setattr(s, "server_url", v.strip()),
                          "Custom server address (optional)", 120),
            ]
            if not N.multiplayer_available():
                wd.append(Label("Multiplayer needs one extra package: pip install websocket-client "
                                "(run.py installs it for you).", 13, WARN))
        else:
            wd = [
                Header("Sound"),
                self._toggle("Sound effects", "sound"),
                self._slider("Volume", "volume", 0, 1, 0.05),
                Button("Test sound", lambda: self.app.audio.play("achievement", 10)),
            ]
            if not self.app.audio.ok:
                wd.append(Label("No audio device found, so the game is running silently.", 13, WARN))
        self.list.set(wd)
        self.list.layout(pygame.Rect(r.x + 8, r.y + 98, r.w - 16, r.h - 160))
        bw = 170
        self.done = Button("DONE", self.app.close_settings, color=ACCENT, height=38, size=15)
        self.done.layout(r.right - bw - 20, r.bottom - 52, bw)
        self.reset = Button("Reset everything", self._reset, color=(90, 30, 45), text_color=TEXT,
                            height=38, tip="Put every setting back to its default")
        self.reset.layout(r.x + 20, r.bottom - 52, bw)

    def event(self, e):
        ui = self.app.ui
        if e.type == pygame.KEYDOWN and e.key in (pygame.K_ESCAPE, pygame.K_o):
            self.app.close_settings()
            return
        if e.type == pygame.MOUSEBUTTONDOWN:
            for w in (self.done, self.reset, self.tabs):
                if w.event(e, ui):
                    return
            self.list.event(e, ui)

    def draw(self, surf):
        ui = self.app.ui
        W, H = surf.get_size()
        shade = pygame.Surface((W, H), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 170))
        surf.blit(shade, (0, 0))
        r = self.rect()
        panel(surf, r, (16, 16, 26), ACCENT)
        ui.text(surf, "SETTINGS", (r.x + 24, r.y + 18), 24, ACCENT, True)
        ui.text(surf, "Saved automatically", (r.right - 24, r.y + 26), 12, TEXT_DIM, False, "topright")
        self.list.layout(self.list.rect)
        self.tabs.draw(surf, ui)
        self.list.draw(surf, ui)
        for w in (self.done, self.reset):
            w.hover(ui)
            w.draw(surf, ui)


def main():
    App().run()
