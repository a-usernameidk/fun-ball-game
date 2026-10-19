"""A tiny widget toolkit drawn entirely with pygame (buttons, sliders, tabs...)."""

import pygame

from .settings import (ACCENT, ACCENT2, BORDER, PANEL, PANEL_HOVER, PANEL_LIGHT,
                       TEXT, TEXT_DIM)
from .util import clamp, mix

_FONT_NAMES = "segoeui,helveticaneue,helvetica,arial,dejavusans,liberationsans"


class UI:
    """Shared state: fonts, the widget being dragged, tooltip."""

    def __init__(self):
        self._fonts = {}
        self.active = None
        self.tip = None
        self.tip_time = 0.0
        self.tip_owner = None
        self.mouse = (0, 0)
        self.sound = None
        self.focus = None   # widget receiving keyboard input (NumberInput)

    def font(self, size, bold=False):
        key = (size, bold)
        f = self._fonts.get(key)
        if f is None:
            try:
                f = pygame.font.SysFont(_FONT_NAMES, size, bold=bold)
            except Exception:
                f = pygame.font.Font(None, size + 6)
            self._fonts[key] = f
        return f

    def text(self, surf, text, pos, size=15, color=TEXT, bold=False, anchor="topleft"):
        img = self.font(size, bold).render(str(text), True, color)
        r = img.get_rect(**{anchor: pos})
        surf.blit(img, r)
        return r

    def click(self):
        if self.sound:
            self.sound("click", 3)

    def set_tip(self, owner, text):
        if owner is not self.tip_owner:
            self.tip_owner = owner
            self.tip_time = 0.0
        self.tip = text

    def draw_tip(self, surf, dt):
        if not self.tip:
            self.tip_owner = None
            return
        self.tip_time += dt
        if self.tip_time < 0.45:
            return
        lines = wrap(self.font(14), self.tip, 260)
        w = max(self.font(14).size(l)[0] for l in lines) + 16
        h = len(lines) * 18 + 10
        x, y = self.mouse[0] + 16, self.mouse[1] + 18
        sw, sh = surf.get_size()
        if x + w > sw:
            x = self.mouse[0] - w - 8
        if y + h > sh:
            y = self.mouse[1] - h - 8
        r = pygame.Rect(x, y, w, h)
        pygame.draw.rect(surf, (10, 10, 18), r, border_radius=6)
        pygame.draw.rect(surf, ACCENT, r, 1, border_radius=6)
        for i, l in enumerate(lines):
            self.text(surf, l, (x + 8, y + 5 + i * 18), 14)


def wrap(font, text, width):
    out = []
    for para in str(text).split("\n"):
        line = ""
        for word in para.split(" "):
            test = (line + " " + word).strip()
            if font.size(test)[0] <= width or not line:
                line = test
            else:
                out.append(line)
                line = word
        out.append(line)
    return out


def panel(surf, rect, color=PANEL, border=BORDER, radius=10):
    pygame.draw.rect(surf, color, rect, border_radius=radius)
    pygame.draw.rect(surf, border, rect, 1, border_radius=radius)


def _val(v):
    return v() if callable(v) else v


# --------------------------------------------------------------------------
class Widget:
    height = 30

    def __init__(self, tip=None):
        self.rect = pygame.Rect(0, 0, 0, 0)
        self.tip = tip

    def layout(self, x, y, w):
        self.rect = pygame.Rect(x, y, w, self.height)
        return self.height

    def event(self, e, ui):
        return False

    def drag(self, pos, ui):
        pass

    def hover(self, ui):
        if self.tip and self.rect.collidepoint(ui.mouse):
            ui.set_tip(self, _val(self.tip))

    def draw(self, surf, ui):
        pass


class Spacer(Widget):
    def __init__(self, h=8):
        super().__init__()
        self.height = h


class Header(Widget):
    height = 32

    def __init__(self, text, color=ACCENT):
        super().__init__()
        self.text, self.color = text, color

    def draw(self, surf, ui):
        ui.text(surf, self.text.upper(), (self.rect.x, self.rect.y + 12), 13, self.color, True)
        y = self.rect.bottom - 2
        pygame.draw.line(surf, BORDER, (self.rect.x, y), (self.rect.right, y))


class Label(Widget):
    def __init__(self, text, size=14, color=TEXT_DIM, tip=None):
        super().__init__(tip)
        self.text, self.size, self.color = text, size, color
        self._lines = [""]

    def layout(self, x, y, w):
        # wrapping depends on width; text may be dynamic so recompute each layout
        self._lines = []
        for line in str(_val(self.text)).split("\n"):
            self._lines += wrap(_LBL_FONT(self.size), line, w)
        self.height = len(self._lines) * (self.size + 4) + 4
        return super().layout(x, y, w)

    def draw(self, surf, ui):
        for i, l in enumerate(self._lines):
            ui.text(surf, l, (self.rect.x, self.rect.y + i * (self.size + 4)), self.size, _val(self.color))


_LBL_CACHE = {}


def _LBL_FONT(size):
    f = _LBL_CACHE.get(size)
    if f is None:
        try:
            f = pygame.font.SysFont(_FONT_NAMES, size)
        except Exception:
            f = pygame.font.Font(None, size + 6)
        _LBL_CACHE[size] = f
    return f


class Button(Widget):
    def __init__(self, text, on_click, color=None, active=None, tip=None, height=30,
                 text_color=None, size=14, icon=None):
        super().__init__(tip)
        self.text, self.on_click = text, on_click
        self.color = color
        self.active = active
        self.height = height
        self.text_color = text_color
        self.size = size
        self.icon = icon

    def event(self, e, ui):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and self.rect.collidepoint(e.pos):
            ui.click()
            self.on_click()
            return True
        return False

    def draw(self, surf, ui):
        hov = self.rect.collidepoint(ui.mouse)
        act = bool(_val(self.active)) if self.active is not None else False
        base = _val(self.color) or PANEL_LIGHT
        if act:
            bg = mix(base if self.color else ACCENT, (0, 0, 0), 0.25) if self.color else mix(PANEL_LIGHT, ACCENT, 0.35)
        else:
            bg = mix(base, (255, 255, 255), 0.12) if hov else base
        pygame.draw.rect(surf, bg, self.rect, border_radius=7)
        if act:
            pygame.draw.rect(surf, ACCENT, self.rect, 2, border_radius=7)
        elif hov:
            pygame.draw.rect(surf, mix(BORDER, ACCENT, 0.5), self.rect, 1, border_radius=7)
        tc = self.text_color or ((15, 15, 25) if self.color and sum(base) > 450 else TEXT)
        if self.icon:
            self.icon(surf, pygame.Rect(self.rect.x + 6, self.rect.y + 4, self.rect.h - 8, self.rect.h - 8))
            ui.text(surf, _val(self.text), (self.rect.x + self.rect.h + 4, self.rect.centery), _val(self.size),
                    tc, True, "midleft")
        else:
            ui.text(surf, _val(self.text), self.rect.center, _val(self.size), tc, True, "center")


class Row(Widget):
    """Lays several widgets side by side."""

    def __init__(self, *children, gap=6):
        super().__init__()
        self.children = list(children)
        self.gap = gap

    def layout(self, x, y, w):
        n = len(self.children)
        cw = (w - self.gap * (n - 1)) / n
        h = 0
        for i, c in enumerate(self.children):
            h = max(h, c.layout(int(x + i * (cw + self.gap)), y, int(cw)))
        self.height = h
        self.rect = pygame.Rect(x, y, w, h)
        return h

    def event(self, e, ui):
        return any(c.event(e, ui) for c in self.children)

    def hover(self, ui):
        for c in self.children:
            c.hover(ui)

    def draw(self, surf, ui):
        for c in self.children:
            c.draw(surf, ui)


class Slider(Widget):
    height = 44

    def __init__(self, label, get, set, lo, hi, step=0.01, fmt=None, tip=None):
        super().__init__(tip)
        self.label, self.get, self.set = label, get, set
        self.lo, self.hi, self.step = lo, hi, step
        self.fmt = fmt

    @property
    def bar(self):
        return pygame.Rect(self.rect.x + 2, self.rect.y + 26, self.rect.w - 4, 8)

    def _fmt(self, v):
        if self.fmt:
            return self.fmt(v)
        if self.step >= 1:
            return str(int(round(v)))
        if self.step >= 0.1:
            return f"{v:.1f}"
        if self.step >= 0.01:
            return f"{v:.2f}"
        return f"{v:.3f}"

    def _apply(self, mx):
        b = self.bar
        k = clamp((mx - b.x) / max(1, b.w), 0.0, 1.0)
        v = self.lo + k * (self.hi - self.lo)
        v = round(v / self.step) * self.step
        v = clamp(v, self.lo, self.hi)
        if self.step >= 1:
            v = int(round(v))
        self.set(v)

    def event(self, e, ui):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and \
                self.rect.inflate(0, 4).collidepoint(e.pos) and e.pos[1] >= self.rect.y + 18:
            ui.active = self
            self._apply(e.pos[0])
            return True
        if e.type == pygame.MOUSEBUTTONDOWN and e.button in (4, 5) and self.rect.collidepoint(e.pos) \
                and pygame.key.get_mods() & pygame.KMOD_SHIFT:
            v = self.get() + (self.step if e.button == 4 else -self.step)
            self.set(clamp(v, self.lo, self.hi))
            return True
        return False

    def drag(self, pos, ui):
        self._apply(pos[0])

    def draw(self, surf, ui):
        v = self.get()
        ui.text(surf, self.label, (self.rect.x, self.rect.y + 4), 14, TEXT)
        ui.text(surf, self._fmt(v), (self.rect.right, self.rect.y + 4), 14, ACCENT, True, "topright")
        b = self.bar
        pygame.draw.rect(surf, (12, 12, 20), b, border_radius=4)
        k = clamp((v - self.lo) / ((self.hi - self.lo) or 1), 0, 1)
        fill = b.copy()
        fill.w = max(4, int(b.w * k))
        pygame.draw.rect(surf, mix(ACCENT, ACCENT2, 0.0), fill, border_radius=4)
        hov = self.rect.collidepoint(ui.mouse) or ui.active is self
        pygame.draw.circle(surf, (255, 255, 255) if hov else (210, 215, 230),
                           (b.x + int(b.w * k), b.centery), 8 if hov else 7)


class Toggle(Widget):
    height = 30

    def __init__(self, label, get, set, tip=None):
        super().__init__(tip)
        self.label, self.get, self.set = label, get, set

    def event(self, e, ui):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and self.rect.collidepoint(e.pos):
            ui.click()
            self.set(not self.get())
            return True
        return False

    def draw(self, surf, ui):
        on = self.get()
        ui.text(surf, self.label, (self.rect.x, self.rect.centery), 14, TEXT, False, "midleft")
        sw = pygame.Rect(self.rect.right - 42, self.rect.centery - 10, 42, 20)
        pygame.draw.rect(surf, mix(PANEL_LIGHT, ACCENT, 0.8) if on else (50, 50, 70), sw, border_radius=10)
        kx = sw.right - 10 if on else sw.x + 10
        pygame.draw.circle(surf, (255, 255, 255), (kx, sw.centery), 8)


class Choice(Widget):
    height = 32

    def __init__(self, label, options, get, set, tip=None, names=None):
        super().__init__(tip)
        self.label, self.options, self.get, self.set = label, options, get, set
        self.names = names

    def _name(self, v):
        if self.names:
            return self.names(v)
        return str(v)

    def event(self, e, ui):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button in (1, 3) and self.rect.collidepoint(e.pos):
            opts = _val(self.options)
            try:
                i = opts.index(self.get())
            except ValueError:
                i = 0
            box = self._box()
            back = e.button == 3 or e.pos[0] < box.centerx - box.w * 0.25
            i = (i + (-1 if back else 1)) % len(opts)
            ui.click()
            self.set(opts[i])
            return True
        return False

    def _box(self):
        w = int(self.rect.w * 0.56)
        return pygame.Rect(self.rect.right - w, self.rect.y + 3, w, self.rect.h - 6)

    def draw(self, surf, ui):
        ui.text(surf, self.label, (self.rect.x, self.rect.centery), 14, TEXT, False, "midleft")
        box = self._box()
        hov = self.rect.collidepoint(ui.mouse)
        pygame.draw.rect(surf, PANEL_HOVER if hov else PANEL_LIGHT, box, border_radius=6)
        cy = box.centery
        for sgn, x in ((-1, box.x + 10), (1, box.right - 10)):
            pygame.draw.polygon(surf, ACCENT, [(x - 4 * sgn, cy - 5), (x + 4 * sgn, cy), (x - 4 * sgn, cy + 5)])
        name = self._name(self.get())
        f = ui.font(13, True)
        while f.size(name)[0] > box.w - 30 and len(name) > 3:
            name = name[:-2]
        ui.text(surf, name, box.center, 13, TEXT, True, "center")


class Tabs(Widget):
    height = 32

    def __init__(self, names, get, set, size=13):
        super().__init__()
        self.names, self.get, self.set = names, get, set
        self.size = size

    def _rects(self):
        n = len(self.names)
        w = self.rect.w / n
        return [pygame.Rect(int(self.rect.x + i * w), self.rect.y, int(w) - 2, self.rect.h)
                for i in range(n)]

    def event(self, e, ui):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            for name, r in zip(self.names, self._rects()):
                if r.collidepoint(e.pos):
                    ui.click()
                    self.set(name)
                    return True
        return False

    def draw(self, surf, ui):
        cur = self.get()
        for name, r in zip(self.names, self._rects()):
            sel = name == cur
            hov = r.collidepoint(ui.mouse)
            pygame.draw.rect(surf, PANEL_HOVER if sel else (PANEL_LIGHT if hov else PANEL), r,
                             border_radius=6)
            if sel:
                pygame.draw.line(surf, ACCENT, (r.x + 6, r.bottom - 2), (r.right - 6, r.bottom - 2), 3)
            ui.text(surf, name, r.center, self.size, TEXT if sel else TEXT_DIM, True, "center")


class Tile(Widget):
    """Square icon button used in the toolbox."""

    def __init__(self, label, draw_icon, on_click, selected, tip=None, hotkey=None):
        super().__init__(tip)
        self.label, self.draw_icon = label, draw_icon
        self.on_click, self.selected = on_click, selected
        self.hotkey = hotkey
        self.height = 0

    def event(self, e, ui):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and self.rect.collidepoint(e.pos):
            ui.click()
            self.on_click()
            return True
        return False

    def draw(self, surf, ui):
        sel = self.selected()
        hov = self.rect.collidepoint(ui.mouse)
        bg = PANEL_HOVER if sel else (PANEL_LIGHT if hov else (24, 24, 38))
        pygame.draw.rect(surf, bg, self.rect, border_radius=8)
        if sel:
            pygame.draw.rect(surf, ACCENT, self.rect, 2, border_radius=8)
        icon = pygame.Rect(self.rect.x + 8, self.rect.y + 6, self.rect.w - 16, self.rect.h - 28)
        prev = surf.get_clip()
        surf.set_clip(icon.clip(prev) if prev else icon)
        self.draw_icon(surf, icon)
        surf.set_clip(prev)
        name = self.label
        size = 11
        while size > 9 and ui.font(size, True).size(name)[0] > self.rect.w - 6:
            size -= 1
        f = ui.font(size, True)
        while f.size(name)[0] > self.rect.w - 6 and len(name) > 3:
            name = name[:-2]
        ui.text(surf, name, (self.rect.centerx, self.rect.bottom - 11), size,
                TEXT if sel or hov else TEXT_DIM, True, "center")
        if self.hotkey:
            ui.text(surf, self.hotkey, (self.rect.x + 5, self.rect.y + 3), 10, TEXT_DIM)


class Grid(Widget):
    """Lays tiles out in columns."""

    def __init__(self, tiles, cols=3, tile_h=78, gap=6):
        super().__init__()
        self.tiles, self.cols, self.tile_h, self.gap = tiles, cols, tile_h, gap

    def layout(self, x, y, w):
        tw = (w - self.gap * (self.cols - 1)) / self.cols
        for i, t in enumerate(self.tiles):
            cx, cy = i % self.cols, i // self.cols
            t.rect = pygame.Rect(int(x + cx * (tw + self.gap)), int(y + cy * (self.tile_h + self.gap)),
                                 int(tw), self.tile_h)
        rows = (len(self.tiles) + self.cols - 1) // self.cols
        self.height = rows * (self.tile_h + self.gap)
        self.rect = pygame.Rect(x, y, w, self.height)
        return self.height

    def event(self, e, ui):
        return any(t.event(e, ui) for t in self.tiles)

    def hover(self, ui):
        for t in self.tiles:
            t.hover(ui)

    def draw(self, surf, ui):
        for t in self.tiles:
            t.draw(surf, ui)


class ScrollList:
    """A vertical list of widgets inside a clipped, scrollable rect."""

    def __init__(self, widgets=None, pad=12, gap=6):
        self.widgets = widgets or []
        self.rect = pygame.Rect(0, 0, 0, 0)
        self.scroll = 0.0
        self.content_h = 0
        self.pad, self.gap = pad, gap

    def set(self, widgets, keep_scroll=False):
        self.widgets = widgets
        if not keep_scroll:
            self.scroll = 0.0

    def layout(self, rect):
        self.rect = pygame.Rect(rect)
        y = self.rect.y + self.pad - int(self.scroll)
        w = self.rect.w - self.pad * 2 - 6
        for wd in self.widgets:
            y += wd.layout(self.rect.x + self.pad, y, w) + self.gap
        self.content_h = y + int(self.scroll) - self.rect.y + self.pad
        max_scroll = max(0, self.content_h - self.rect.h)
        if self.scroll > max_scroll:
            self.scroll = max_scroll
            self.layout(rect)

    def hover(self, ui):
        pass  # draw() handles hovering for the children

    def event(self, e, ui):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button in (4, 5) and self.rect.collidepoint(e.pos):
            if not pygame.key.get_mods() & pygame.KMOD_SHIFT:
                self.scroll = max(0.0, self.scroll + (-40 if e.button == 4 else 40))
                return True
        if e.type == pygame.MOUSEWHEEL:
            return False
        if hasattr(e, "pos") and not self.rect.collidepoint(e.pos):
            return False
        for wd in self.widgets:
            if wd.event(e, ui):
                return True
        return False

    def draw(self, surf, ui):
        prev = surf.get_clip()
        surf.set_clip(self.rect)
        if self.rect.collidepoint(ui.mouse):
            for wd in self.widgets:
                wd.hover(ui)
        for wd in self.widgets:
            if wd.rect.bottom >= self.rect.y and wd.rect.y <= self.rect.bottom:
                wd.draw(surf, ui)
        surf.set_clip(prev)
        if self.content_h > self.rect.h:
            k = self.rect.h / self.content_h
            h = max(30, int(self.rect.h * k))
            y = self.rect.y + int((self.rect.h - h) * (self.scroll / max(1, self.content_h - self.rect.h)))
            pygame.draw.rect(surf, (70, 70, 100), (self.rect.right - 6, y, 4, h), border_radius=2)


class NumberInput(Widget):
    """Click, type a number, press Enter."""
    height = 32

    def __init__(self, label, get, set, lo, hi, tip=None, integer=True):
        super().__init__(tip)
        self.label, self.get, self.set = label, get, set
        self.lo, self.hi, self.integer = lo, hi, integer
        self.buf = None

    def _box(self):
        w = int(self.rect.w * 0.42)
        return pygame.Rect(self.rect.right - w, self.rect.y + 3, w, self.rect.h - 6)

    def event(self, e, ui):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and self.rect.collidepoint(e.pos):
            ui.focus = self
            v = self.get()
            self.buf = str(int(v) if self.integer else v)
            return True
        return False

    def key(self, e, ui):
        if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_TAB):
            self.commit(ui)
        elif e.key == pygame.K_ESCAPE:
            self.buf = None
            ui.focus = None
        elif e.key == pygame.K_BACKSPACE:
            self.buf = self.buf[:-1]
        elif e.unicode and (e.unicode.isdigit() or (e.unicode == "." and not self.integer)) \
                and len(self.buf) < 9:
            self.buf += e.unicode

    def commit(self, ui):
        try:
            v = float(self.buf)
            v = clamp(v, self.lo, self.hi)
            self.set(int(v) if self.integer else v)
        except (TypeError, ValueError):
            pass
        self.buf = None
        if ui.focus is self:
            ui.focus = None

    def draw(self, surf, ui):
        ui.text(surf, self.label, (self.rect.x, self.rect.centery), 14, TEXT, False, "midleft")
        box = self._box()
        editing = ui.focus is self
        hov = self.rect.collidepoint(ui.mouse)
        pygame.draw.rect(surf, (12, 12, 20), box, border_radius=6)
        pygame.draw.rect(surf, ACCENT if editing else (mix(BORDER, ACCENT, 0.5) if hov else BORDER), box,
                         2 if editing else 1, border_radius=6)
        if editing:
            caret = "|" if (pygame.time.get_ticks() // 400) % 2 else " "
            txt = self.buf + caret
        else:
            v = self.get()
            txt = f"{int(v):,}" if self.integer else f"{v:g}"
        ui.text(surf, txt, (box.right - 10, box.centery), 14, ACCENT if editing else TEXT, True, "midright")


class TextInput(Widget):
    """Single-line text box. Click to type, Enter to confirm."""
    height = 38

    def __init__(self, get, set, placeholder="", max_len=28, tip=None, live=False):
        super().__init__(tip)
        self.get, self.set = get, set
        self.placeholder, self.max_len = placeholder, max_len
        self.live = live   # live=True: every keystroke updates the value
        self.buf = None

    def event(self, e, ui):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and self.rect.collidepoint(e.pos):
            self.focus(ui)
            return True
        return False

    def focus(self, ui):
        ui.focus = self
        self.buf = self.get()

    def key(self, e, ui):
        if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_TAB):
            self.commit(ui)
            return
        if e.key == pygame.K_ESCAPE:
            self.buf = None
            ui.focus = None
            return
        if e.key == pygame.K_BACKSPACE:
            self.buf = self.buf[:-1]
        elif e.unicode and e.unicode.isprintable() and len(self.buf) < self.max_len:
            self.buf += e.unicode
        if self.live:
            self.set(self.buf)

    def commit(self, ui):
        if self.buf is not None and self.buf.strip():
            self.set(self.buf.strip())
        self.buf = None
        if ui.focus is self:
            ui.focus = None

    def draw(self, surf, ui):
        editing = ui.focus is self
        hov = self.rect.collidepoint(ui.mouse)
        pygame.draw.rect(surf, (12, 12, 20), self.rect, border_radius=7)
        pygame.draw.rect(surf, ACCENT if editing else (mix(BORDER, ACCENT, 0.5) if hov else BORDER),
                         self.rect, 2 if editing else 1, border_radius=7)
        text = self.buf if editing else self.get()
        if editing and (pygame.time.get_ticks() // 400) % 2:
            text += "|"
        if text:
            ui.text(surf, text, (self.rect.x + 12, self.rect.centery), 16, TEXT, True, "midleft")
        else:
            ui.text(surf, self.placeholder, (self.rect.x + 12, self.rect.centery), 15, TEXT_DIM, False,
                    "midleft")
