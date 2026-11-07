"""Resolution-independent drawing helpers.

Layout is written in a fixed 1280x720 design space. ``Gfx`` maps design units
to window pixels (uniform scale, centred), caches fonts and rendered text, and
draws anti-aliased pieces and dashed outlines. Characters missing from the
bundled rounded font (arrows, symbols) are rendered with a system fallback font.
"""

import math
import os

import pygame

from . import theme

class Gfx:
    def __init__(self):
        self.surface = None
        self.scale = 1.0
        self.ox = self.oy = 0.0
        self._fonts = {}
        self._fallback_fonts = {}
        self._text_cache = {}
        self._glyph_cache = {}
        self._sprite_cache = {}
        self._notdef = {}

    # ------------------------------------------------------------ scaling
    def begin(self, surface: pygame.Surface) -> None:
        w, h = surface.get_size()
        scale = min(w / theme.DESIGN_W, h / theme.DESIGN_H)
        if abs(scale - self.scale) > 1e-9:
            self._fonts.clear()
            self._fallback_fonts.clear()
            self._text_cache.clear()
            self._sprite_cache.clear()
            self._notdef.clear()
        self.scale = scale
        self.ox = (w - theme.DESIGN_W * scale) / 2
        self.oy = (h - theme.DESIGN_H * scale) / 2
        self.surface = surface

    def px(self, v: float) -> int:
        return max(0, round(v * self.scale))

    def pt(self, x: float, y: float) -> tuple:
        return (round(self.ox + x * self.scale), round(self.oy + y * self.scale))

    def rect(self, r) -> pygame.Rect:
        x, y, w, h = r
        x0, y0 = self.pt(x, y)
        x1, y1 = self.pt(x + w, y + h)
        return pygame.Rect(x0, y0, x1 - x0, y1 - y0)

    def to_units(self, pos) -> tuple:
        return ((pos[0] - self.ox) / self.scale, (pos[1] - self.oy) / self.scale)

    # --------------------------------------------------------------- fonts
    def font(self, size: float, weight: str = "regular") -> pygame.font.Font:
        px = max(6, round(size * self.scale))
        key = (px, weight)
        f = self._fonts.get(key)
        if f is None:
            path = theme.FONT_FILES.get(weight)
            if path and os.path.exists(path):
                f = pygame.font.Font(path, px)
            else:
                f = pygame.font.SysFont("segoeui", px, bold=weight in ("semibold", "bold"))
            self._fonts[key] = f
        return f

    def _fallback(self, size: float, index: int, bold: bool) -> pygame.font.Font:
        px = max(6, round(size * self.scale))
        key = (px, index, bold)
        f = self._fallback_fonts.get(key)
        if f is None:
            f = pygame.font.SysFont(theme.FALLBACK_FONTS[index], px, bold=bold)
            self._fallback_fonts[key] = f
        return f

    def _has_glyph(self, font: pygame.font.Font, key, ch: str) -> bool:
        ck = (key, ch)
        hit = self._glyph_cache.get(ck)
        if hit is None:
            nd = self._notdef.get(key)
            if nd is None:
                nd = self._notdef[key] = font.metrics("")[0]
            m = font.metrics(ch)[0]
            hit = m is not None and m != nd
            self._glyph_cache[ck] = hit
        return hit

    def _runs(self, text: str, size: float, weight: str):
        """Split text into runs rendered by the main font or a fallback font."""
        main = self.font(size, weight)
        bold = weight in ("semibold", "bold")
        runs = []
        for ch in text:
            if ord(ch) < 128 or self._has_glyph(main, ("main", weight, size), ch):
                f = main
            else:
                f = None
                for i in range(len(theme.FALLBACK_FONTS)):
                    cand = self._fallback(size, i, bold)
                    if self._has_glyph(cand, ("fb", i, size, bold), ch):
                        f = cand
                        break
                f = f or main
            if runs and runs[-1][0] is f:
                runs[-1][1].append(ch)
            else:
                runs.append((f, [ch]))
        return [(f, "".join(chars)) for f, chars in runs]

    def text_surface(self, text: str, size: float, color, weight: str = "regular") -> pygame.Surface:
        key = (text, size, weight, color)
        surf = self._text_cache.get(key)
        if surf is not None:
            return surf
        if len(self._text_cache) > 3000:
            self._text_cache.clear()
        runs = self._runs(text, size, weight)
        if not runs:
            font = self.font(size, weight)
            surf = pygame.Surface((1, font.get_height()), pygame.SRCALPHA)
        elif len(runs) == 1:
            surf = runs[0][0].render(runs[0][1], True, color)
        else:
            parts = [(f, f.render(t, True, color)) for f, t in runs]
            ascent = max(f.get_ascent() for f, _ in parts)
            height = max(ascent - f.get_ascent() + s.get_height() for f, s in parts)
            surf = pygame.Surface((sum(s.get_width() for _, s in parts), height), pygame.SRCALPHA)
            x = 0
            for f, s in parts:
                surf.blit(s, (x, ascent - f.get_ascent()))
                x += s.get_width()
        self._text_cache[key] = surf
        return surf

    def text_width(self, text: str, size: float, weight: str = "regular") -> float:
        return self.text_surface(text, size, (0, 0, 0), weight).get_width() / self.scale

    def text(self, text: str, pos, size: float, color, weight: str = "regular",
             anchor: str = "topleft", max_width: float = None, strike: bool = False) -> pygame.Rect:
        if max_width is not None and self.text_width(text, size, weight) > max_width:
            while len(text) > 1 and self.text_width(text + "…", size, weight) > max_width:
                text = text[:-1]
            text = text.rstrip() + "…"
        surf = self.text_surface(text, size, color, weight)
        r = surf.get_rect()
        setattr(r, anchor, self.pt(*pos))
        self.surface.blit(surf, r)
        if strike:
            y = r.centery + 1
            pygame.draw.line(self.surface, color, (r.left - 2, y), (r.right + 2, y), max(1, self.px(1.6)))
        return r

    # -------------------------------------------------------------- shapes
    def round_rect(self, r, fill=None, radius: float = 0, border=None, width: float = 0) -> None:
        pr = self.rect(r)
        rad = self.px(radius)
        if fill is not None:
            if len(fill) == 4:
                s = pygame.Surface(pr.size, pygame.SRCALPHA)
                pygame.draw.rect(s, fill, s.get_rect(), border_radius=rad)
                self.surface.blit(s, pr.topleft)
            else:
                pygame.draw.rect(self.surface, fill, pr, border_radius=rad)
        if border is not None and width:
            pygame.draw.rect(self.surface, border, pr, max(1, self.px(width)), border_radius=rad)

    def shadow(self, r, radius: float = 16, offset: float = 4, alpha: int = 38) -> None:
        x, y, w, h = r
        pr = self.rect((x, y + offset, w, h))
        s = pygame.Surface(pr.size, pygame.SRCALPHA)
        pygame.draw.rect(s, (*theme.SHADOW, alpha), s.get_rect(), border_radius=self.px(radius))
        self.surface.blit(s, pr.topleft)

    def circle(self, c, radius: float, color, width: float = 0) -> None:
        center = self.pt(*c)
        rad = max(1, self.px(radius))
        if width:
            pygame.draw.aacircle(self.surface, color, center, rad, max(1, self.px(width)))
        else:
            pygame.draw.aacircle(self.surface, color, center, rad)

    def circle_alpha(self, c, radius: float, color, alpha: int) -> None:
        rad = max(1, self.px(radius))
        s = pygame.Surface((rad * 2 + 2, rad * 2 + 2), pygame.SRCALPHA)
        pygame.draw.aacircle(s, (*color, alpha), (rad + 1, rad + 1), rad)
        cx, cy = self.pt(*c)
        self.surface.blit(s, (cx - rad - 1, cy - rad - 1))

    def line(self, a, b, color, width: float = 1) -> None:
        w = max(1, self.px(width))
        if w <= 1:
            pygame.draw.aaline(self.surface, color, self.pt(*a), self.pt(*b))
        else:
            pygame.draw.line(self.surface, color, self.pt(*a), self.pt(*b), w)

    def dashed_line(self, a, b, color, width: float = 1, dash: float = 6, gap: float = 6) -> None:
        self.dashed_path([a, b], color, width, dash, gap)

    def dashed_path(self, points, color, width: float = 2, dash: float = 10, gap: float = 7,
                    closed: bool = False) -> None:
        pts = list(points) + ([points[0]] if closed else [])
        on, remaining = True, dash
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            seg = math.hypot(x1 - x0, y1 - y0)
            pos = 0.0
            while pos < seg - 1e-9:
                step = min(remaining, seg - pos)
                if on:
                    t0, t1 = pos / seg, (pos + step) / seg
                    self.line((x0 + (x1 - x0) * t0, y0 + (y1 - y0) * t0),
                              (x0 + (x1 - x0) * t1, y0 + (y1 - y0) * t1), color, width)
                pos += step
                remaining -= step
                if remaining <= 1e-9:
                    on = not on
                    remaining = dash if on else gap

    def ellipse(self, r, fill, border=None, width: float = 0) -> None:
        import pygame.gfxdraw as gd
        pr = self.rect(r)
        if border is not None and width:
            pygame.draw.ellipse(self.surface, border, pr)
            gd.aaellipse(self.surface, pr.centerx, pr.centery, pr.w // 2, pr.h // 2, border)
            bw = max(1, self.px(width))
            pr = pr.inflate(-2 * bw, -2 * bw)
        pygame.draw.ellipse(self.surface, fill, pr)
        gd.aaellipse(self.surface, pr.centerx, pr.centery, pr.w // 2, pr.h // 2, fill)

    def wrap(self, text: str, size: float, width: float, weight: str = "regular") -> list:
        lines = []
        for para in text.split("\n"):
            line = ""
            for word in para.split(" "):
                trial = (line + " " + word).strip()
                if line and self.text_width(trial, size, weight) > width:
                    lines.append(line)
                    line = word
                else:
                    line = trial
            lines.append(line)
        return lines

    def paragraph(self, text: str, pos, size: float, color, width: float, weight: str = "regular",
                  line_height: float = None) -> float:
        """Draw wrapped text; returns the y just below it (design units)."""
        x, y = pos
        lh = line_height or size * 1.35
        for line in self.wrap(text, size, width, weight):
            self.text(line, (x, y), size, color, weight)
            y += lh
        return y

    def triangle(self, points, color) -> None:
        pygame.draw.polygon(self.surface, color, [self.pt(*p) for p in points])
        pygame.draw.aalines(self.surface, color, True, [self.pt(*p) for p in points])

    # -------------------------------------------------------------- pieces
    def piece(self, player: int, c, radius: float, scale: float = 1.0, alpha: int = 255) -> None:
        rad = max(2, self.px(radius * scale))
        key = (player, rad)
        sprite = self._sprite_cache.get(key)
        if sprite is None:
            sprite = self._sprite_cache[key] = _render_piece(player, rad)
        cx, cy = self.pt(*c)
        if alpha < 255:
            sprite = sprite.copy()
            sprite.set_alpha(alpha)
        self.surface.blit(sprite, (cx - sprite.get_width() // 2, cy - sprite.get_height() // 2))

    # ---------------------------------------------------------- background
    def checkerboard(self, square: float = 92) -> None:
        """The light-blue / white checkerboard background of the slides."""
        surf = self.surface
        surf.fill(theme.WHITE)
        size = max(4, self.px(square))
        w, h = surf.get_size()
        ox = round(self.ox) % (2 * size)
        for row, y in enumerate(range(-size, h + size, size)):
            for col, x in enumerate(range(-2 * size + ox, w + size, size)):
                if (row + col) % 2 == 0:
                    surf.fill(theme.BLUE_LIGHT, (x, y, size, size))


def _render_piece(player: int, rad: int) -> pygame.Surface:
    """Flat slide-style piece: fill, darker rim, soft shadow and a faint highlight (4x supersampled)."""
    fill, rim = theme.PIECE_COLORS[player]
    ss = 4
    R = rad * ss
    pad = max(2, rad // 6) * ss
    size = 2 * R + 2 * pad
    big = pygame.Surface((size, size), pygame.SRCALPHA)
    c = size // 2
    pygame.draw.circle(big, (*theme.SHADOW, 55), (c, c + max(2, R // 14)), R)
    pygame.draw.circle(big, rim, (c, c), R)
    pygame.draw.circle(big, fill, (c, c), R - max(2, R // 14))
    hl = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.ellipse(hl, (255, 255, 255, 46), (c - R * 0.55, c - R * 0.78, R * 1.1, R * 0.62))
    big.blit(hl, (0, 0))
    small = (size // ss, size // ss)
    return pygame.transform.smoothscale(big, small)
