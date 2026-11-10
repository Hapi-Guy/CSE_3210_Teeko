"""Pygame application shell: window, scaling, screen switching and the frame loop."""

import os
import sys
import time

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame  # noqa: E402

from . import theme  # noqa: E402
from .gfx import Gfx  # noqa: E402
from .settings import GameSettings  # noqa: E402

MOUSE_EVENTS = (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION)


def _enable_dpi_awareness():
    """Ask Windows for real pixels so text stays crisp on high-DPI screens."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


class Screen:
    def __init__(self, app):
        self.app = app
        self.widgets = []

    def enter(self, **kwargs):
        pass

    def leave(self):
        pass

    def handle(self, event, pos) -> bool:
        for w in self.widgets:                       # an open dropdown gets first pick
            if getattr(w, "open", False) and w.visible and w.handle(event, pos):
                return True
        for w in reversed(self.widgets):
            if w.visible and w.handle(event, pos):
                return True
        return False

    def update(self, now):
        pass

    def draw(self, g, now):
        pass

    def draw_widgets(self, g):
        for w in self.widgets:
            w.draw(g)
        for w in self.widgets:
            w.draw_overlay(g)

    def wants_fast_frames(self, now) -> bool:
        return False


class App:
    def __init__(self, size=None):
        _enable_dpi_awareness()
        pygame.init()
        pygame.display.set_caption(f"{theme.APP_TITLE} — {theme.COURSE_LABEL}")
        if size is None:
            size = self._initial_size()
        self.windowed_size = size
        self.surface = pygame.display.set_mode(size, pygame.RESIZABLE)
        self._set_icon()
        self.g = Gfx()
        self.settings = GameSettings()
        self.mouse = (0.0, 0.0)
        self.fullscreen = False
        self.running = True
        self.clock = pygame.time.Clock()

        from .benchmark_screen import BenchmarkScreen
        from .game_screen import GameScreen
        from .setup_screen import StartScreen
        self.screens = {"start": StartScreen(self), "game": GameScreen(self),
                        "bench": BenchmarkScreen(self)}
        self.current = self.screens["start"]
        self.current.enter()

    @staticmethod
    def _initial_size():
        try:
            dw, dh = pygame.display.get_desktop_sizes()[0]
        except Exception:
            return 1280, 720
        w = int(min(dw * 0.85, dh * 0.85 * 16 / 9))
        return max(960, w), max(540, int(w * 9 / 16))

    def _set_icon(self):
        icon = pygame.Surface((64, 64), pygame.SRCALPHA)
        pygame.draw.circle(icon, theme.RED, (22, 22), 18)
        pygame.draw.circle(icon, theme.BLUE_PIECE, (42, 42), 18)
        pygame.display.set_icon(icon)

    # ---------------------------------------------------------------- control
    def switch(self, name, **kwargs):
        self.current.leave()
        self.current = self.screens[name]
        self.current.enter(**kwargs)

    def toggle_fullscreen(self):
        if self.fullscreen:
            self.surface = pygame.display.set_mode(self.windowed_size, pygame.RESIZABLE)
        else:
            self.windowed_size = self.surface.get_size()
            self.surface = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        self.fullscreen = not self.fullscreen

    def quit(self):
        self.running = False

    # ------------------------------------------------------------------ loop
    def run(self):
        while self.running:
            self.frame()
        for screen in self.screens.values():
            screen.leave()
        pygame.quit()

    def frame(self, now=None):
        now = time.monotonic() if now is None else now
        for event in pygame.event.get():
            self.dispatch(event)
        self.current.update(now)
        self.draw(now)
        fast = self.current.wants_fast_frames(now)
        self.clock.tick(60 if fast else 30)

    def dispatch(self, event):
        if event.type == pygame.QUIT:
            self.quit()
            return
        if event.type in (pygame.VIDEORESIZE, pygame.WINDOWSIZECHANGED):
            self.surface = pygame.display.get_surface()
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
            self.toggle_fullscreen()
            return
        if event.type in MOUSE_EVENTS:
            self.mouse = self.g.to_units(event.pos)
        self.current.handle(event, self.mouse)

    def draw(self, now):
        self.g.begin(self.surface)
        self.current.draw(self.g, now)
        pygame.display.flip()
