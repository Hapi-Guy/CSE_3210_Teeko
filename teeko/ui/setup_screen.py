"""Start / mode-selection screen, styled after the proposal's title slide."""

import os

import pygame

from ..ai.presets import LEVEL_NAMES, LEVELS, budget_text, describe
from . import theme
from .app import Screen
from .settings import MODE_NAMES
from .widgets import Button, Checkbox, Segmented, Selector, Slider, Stepper, inside

MODES = (
    ("hva", "Human vs AI", "vs Minimax or MCTS"),
    ("ava", "AI vs AI", "Watch & compare agents"),
    ("hvh", "Human vs Human", "Two players · rules demo"),
    ("bench", "Benchmark", "Compare all four pairings"),
)
MODE_DESCRIPTIONS = {
    "hva": "Choose your colour, the AI's algorithm and its difficulty. Red always moves first.",
    "ava": "Pick an algorithm and budget for each side. Start, pause, step through moves, or "
           "auto-play a series of games for comparison.",
    "hvh": "Two players share the mouse. Handy for demonstrating the shuttle trigger and the "
           "Swap and Fly abilities.",
    "bench": "Plays Minimax v Minimax, Minimax v MCTS, MCTS v Minimax and MCTS v MCTS without "
             "animation, then reports win rates, game length and decision times.",
}
LEVEL_OPTIONS = [(lv, LEVEL_NAMES[lv]) for lv in LEVELS] + [("custom", "Custom")]
ALGO_OPTIONS = [("minimax", "Minimax"), ("mcts", "MCTS")]
TIME_OPTIONS = [(None, "Level default"), (0.25, "0.25 s"), (0.5, "0.5 s"), (1.0, "1 s"), (2.0, "2 s")]
RULES = ("5×5 board · 4 pieces each. Place all 8 pieces, then move one piece per turn to an "
         "adjacent point (diagonals too). Win with four in a line or a 2×2 square.\n"
         "Shuttling one piece A→B→A→B→A unlocks the opponent's one-use Swap and Fly.\n"
         "After the movement limit, open patterns score +1/+3/+10; ties go to central pieces.")

OPT_X, OPT_Y, OPT_W, OPT_H = 640, 84, 590, 602
INNER_X = OPT_X + 28
INNER_W = OPT_W - 56


class StartScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.selected = "hva"
        self.bench = {"games": 6, "mm_level": "easy", "mcts_level": "easy", "time": None,
                      "openings": 2, "jobs": max(1, min(8, (os.cpu_count() or 2) - 1)), "limit": 24}
        self.start_button = Button((OPT_X + OPT_W - 236, OPT_Y + OPT_H - 74, 208, 54), "Start Game",
                                   self._start, size=21)
        self.rebuild()

    def enter(self, **kwargs):
        self.rebuild()

    # --------------------------------------------------------------- widgets
    def rebuild(self):
        s = self.app.settings
        self.widgets = []
        if self.selected == "hva":
            self._build_hva(s)
        elif self.selected == "ava":
            self._build_ava(s)
        elif self.selected == "hvh":
            self._limit_stepper(s, OPT_Y + 200)
        else:
            self._build_bench()
        self.start_button.text = "Run Benchmark" if self.selected == "bench" else "Start Game"
        self.widgets.append(self.start_button)

    def _limit_stepper(self, s, y):
        def set_limit(v):
            s.limit = v
        self.widgets.append(Stepper((INNER_X, y, 330, 34), "Movement turns per player", s.limit,
                                    4, 60, 1, set_limit))

    def _build_hva(self, s):
        y = OPT_Y + 132

        def set_side(v):
            s.human_side = v
        self.widgets.append(Segmented((INNER_X, y + 22, INNER_W, 42),
                                      [(0, "Red · P1 (moves first)"), (1, "Blue · P2")],
                                      s.human_side, set_side, size=16))

        def set_algo(v):
            s.ai.algorithm = v
            self.rebuild()
        self.widgets.append(Segmented((INNER_X, y + 104, INNER_W, 42),
                                      [("minimax", "Minimax  (alpha–beta)"), ("mcts", "MCTS  (UCT)")],
                                      s.ai.algorithm, set_algo, size=16))

        def set_level(v):
            s.ai.level = v
            self.rebuild()
        self.widgets.append(Segmented((INNER_X, y + 186, INNER_W, 40), LEVEL_OPTIONS, s.ai.level,
                                      set_level, size=15))
        if s.ai.level == "custom":
            self._custom_sliders(s.ai, INNER_X, y + 262, INNER_W, horizontal=True)
        self._limit_stepper(s, OPT_Y + OPT_H - 132)

    def _build_ava(self, s):
        col_w = (INNER_W - 20) / 2
        for seat in (0, 1):
            x = INNER_X + seat * (col_w + 20)
            cfg = s.seats[seat]

            def set_algo(v, cfg=cfg):
                cfg.algorithm = v
                self.rebuild()

            def set_level(v, cfg=cfg):
                cfg.level = v
                self.rebuild()
            self.widgets.append(Segmented((x, OPT_Y + 158, col_w, 38), ALGO_OPTIONS, cfg.algorithm,
                                          set_algo, size=15))
            self.widgets.append(Selector((x, OPT_Y + 204, col_w, 36), LEVEL_OPTIONS, cfg.level,
                                         set_level))
            if cfg.level == "custom":
                self._custom_sliders(cfg, x, OPT_Y + 284, col_w, horizontal=False)

        y = OPT_Y + 410

        def set_delay(v):
            s.delay = v
        self.widgets.append(Slider((INNER_X, y, INNER_W, 40), 0.0, 3.0, s.delay, set_delay, step=0.1,
                                   fmt="{:.1f} s", label="Delay between moves"))

        def set_series(v):
            s.series = v
            self.rebuild()

        def set_games(v):
            s.series_games = v

        def set_alt(v):
            s.alternate = v

        def set_openings(v):
            s.openings = v
        self.widgets.append(Checkbox((INNER_X, y + 52, 230, 30), "Auto-play a series", s.series,
                                     set_series))
        games = Stepper((INNER_X + 250, y + 52, INNER_W - 250, 30), "Games", s.series_games, 2, 100,
                        2, set_games)
        alt = Checkbox((INNER_X, y + 88, 230, 30), "Alternate sides", s.alternate, set_alt)
        openings = Stepper((INNER_X + 250, y + 88, INNER_W - 250, 30), "Random opening plies",
                           s.openings, 0, 4, 1, set_openings)
        for w in (games, alt, openings):
            w.enabled = s.series
        self.widgets += [games, alt, openings]
        self._limit_stepper(s, OPT_Y + OPT_H - 64)
        self.widgets[-1].rect = (INNER_X, OPT_Y + OPT_H - 66, 320, 34)

    def _custom_sliders(self, cfg, x, y, w, horizontal):
        p = cfg.custom[cfg.algorithm]
        specs = []
        if cfg.algorithm == "minimax":
            specs.append(("depth", 1, 10, 1, "{:.0f}", "Depth", False))
        else:
            specs.append(("simulations", 100, 30000, 50, "{:,.0f}", "Simulations", True))
        specs.append(("time_limit", 0.5, 10.0, 0.5, "{:.1f} s", "Time cap", False))
        if cfg.algorithm == "mcts":
            specs.append(("exploration", 0.3, 2.5, 0.05, "{:.2f}", "Exploration C", False))
        n = len(specs)
        for i, (key, lo, hi, step, fmt, label, log) in enumerate(specs):
            def setter(v, key=key):
                p[key] = int(v) if key in ("depth", "simulations") else round(v, 2)
            if horizontal:
                sw = (w - 20 * (n - 1)) / n
                rect = (x + i * (sw + 20), y, sw, 40)
            else:
                rect = (x, y + i * 44, w, 40)
            self.widgets.append(Slider(rect, lo, hi, p[key], setter, step=step, fmt=fmt, label=label,
                                       log=log, size=13))

    def _build_bench(self):
        b = self.bench
        y = OPT_Y + 168

        def setter(key):
            def f(v):
                b[key] = v
            return f
        self.widgets.append(Stepper((INNER_X, y, INNER_W, 34), "Games per pairing", b["games"], 2, 50,
                                    2, setter("games")))
        self.widgets.append(Selector((INNER_X + 230, y + 50, INNER_W - 230, 34), LEVEL_OPTIONS[:4],
                                     b["mm_level"], setter("mm_level")))
        self.widgets.append(Selector((INNER_X + 230, y + 96, INNER_W - 230, 34), LEVEL_OPTIONS[:4],
                                     b["mcts_level"], setter("mcts_level")))
        self.widgets.append(Selector((INNER_X + 230, y + 142, INNER_W - 230, 34), TIME_OPTIONS,
                                     b["time"], setter("time")))
        self.widgets.append(Stepper((INNER_X, y + 196, INNER_W, 34), "Random opening plies",
                                    b["openings"], 0, 4, 1, setter("openings")))
        self.widgets.append(Stepper((INNER_X, y + 242, INNER_W, 34), "Worker processes", b["jobs"], 1,
                                    max(1, os.cpu_count() or 1), 1, setter("jobs")))
        self.widgets.append(Stepper((INNER_X, y + 288, INNER_W, 34), "Movement turns per player",
                                    b["limit"], 4, 60, 1, setter("limit")))

    # --------------------------------------------------------------- actions
    def _start(self):
        if self.selected == "bench":
            self.app.switch("bench", options=dict(self.bench))
            return
        self.app.settings.mode = self.selected
        self.app.switch("game", settings=self.app.settings.copy())

    def _mode_rects(self):
        rects = {}
        for i, (key, _, _) in enumerate(MODES):
            rects[key] = (52 + (i % 2) * 286, 386 + (i // 2) * 108, 270, 94)
        return rects

    def handle(self, event, pos):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for key, r in self._mode_rects().items():
                if inside(r, pos):
                    if key != self.selected:
                        self.selected = key
                        self.rebuild()
                    return True
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self._start()
                return True
            if event.key == pygame.K_ESCAPE:
                self.app.quit()
                return True
        return super().handle(event, pos)

    # ----------------------------------------------------------------- draw
    def draw(self, g, now):
        g.checkerboard()
        # course header bar + full-width rule, as on the title slide
        g.round_rect((70, -24, 1140, 80), theme.BLUE, 16)
        g.text(theme.COURSE_LABEL, (640, 28), 28, theme.WHITE, "semibold", "center")
        g.round_rect((-200, 62, 1680, 5), theme.BLUE)

        g.ellipse((52, 84, 556, 220), theme.WHITE, theme.BLUE, 5)
        g.text("Teeko", (330, 194), 104, theme.BLUE, "semibold", "center")
        g.round_rect((52, 318, 556, 50), theme.BLUE, 25)
        g.text("AI Lab — Teeko AI  ·  Minimax & MCTS", (330, 343), 21, theme.WHITE, "medium", "center")

        mouse = self.app.mouse
        for key, r in self._mode_rects().items():
            title, sub = next((t, s) for k, t, s in MODES if k == key)
            sel = key == self.selected
            hover = inside(r, mouse)
            if sel:
                g.shadow(r, 16, 4, 40)
            g.round_rect(r, theme.BLUE_PALE if sel else theme.WHITE, 16,
                         theme.BLUE if (sel or hover) else theme.BLUE_LINE, 3.5 if sel else 2.5)
            _mode_icon(g, key, (r[0] + 44, r[1] + r[3] / 2))
            g.text(title, (r[0] + 84, r[1] + 30), 20, theme.BLUE_DARK, "semibold", "midleft")
            g.text(sub, (r[0] + 84, r[1] + 60), 14, theme.NAVY, "regular", "midleft", max_width=r[2] - 92)

        for i, (name, roll) in enumerate(theme.TEAM):
            r = (52 + i * 286, 608, 270, 76)
            g.round_rect(r, theme.WHITE, 16, theme.BLUE, 2.5)
            g.text(name, (r[0] + r[2] / 2, r[1] + 26), 18, theme.BLUE_DARK, "semibold", "center")
            g.text(roll, (r[0] + r[2] / 2, r[1] + 52), 15, theme.NAVY, "medium", "center")

        self._draw_options(g)
        self.draw_widgets(g)

    def _draw_options(self, g):
        s = self.app.settings
        r = (OPT_X, OPT_Y, OPT_W, OPT_H)
        g.shadow(r, 24, 5, 30)
        g.round_rect(r, theme.WHITE, 24, theme.BLUE, 4)
        title = MODE_NAMES.get(self.selected, "Benchmark")
        g.text(title, (INNER_X, OPT_Y + 26), 28, theme.BLUE_DARK, "semibold")
        g.paragraph(MODE_DESCRIPTIONS[self.selected], (INNER_X, OPT_Y + 66), 15, theme.NAVY, INNER_W)

        if self.selected == "hva":
            y = OPT_Y + 132
            g.text("You play as", (INNER_X, y), 14, theme.GREY_LABEL, "semibold")
            g.text("AI algorithm", (INNER_X, y + 82), 14, theme.GREY_LABEL, "semibold")
            g.text("Difficulty", (INNER_X, y + 164), 14, theme.GREY_LABEL, "semibold")
            g.text(describe(s.ai.config()), (INNER_X, y + 236), 15, theme.NAVY, "medium")
        elif self.selected == "ava":
            col_w = (INNER_W - 20) / 2
            for seat in (0, 1):
                x = INNER_X + seat * (col_w + 20)
                g.piece(seat, (x + 10, OPT_Y + 138), 9)
                g.text(("P1 · Red" if seat == 0 else "P2 · Blue"), (x + 26, OPT_Y + 138), 17,
                       theme.NAVY, "semibold", "midleft")
                cfg = s.seats[seat].config()
                g.text(budget_text(cfg), (x, OPT_Y + 250), 13, theme.GREY_TEXT, "medium",
                       max_width=col_w)
        elif self.selected == "hvh":
            box = (INNER_X, OPT_Y + 260, INNER_W, 210)
            g.round_rect(box, theme.BLUE_PALE, 14)
            g.text("Rules at a glance", (box[0] + 18, box[1] + 14), 16, theme.BLUE_DARK, "semibold")
            g.paragraph(RULES, (box[0] + 18, box[1] + 44), 14, theme.NAVY, box[2] - 36)
        else:
            y = OPT_Y + 168
            for i, label in enumerate(("Minimax level", "MCTS level", "Equal time cap")):
                g.text(label, (INNER_X, y + 67 + i * 46), 15, theme.GREY_LABEL, "medium", "midleft")
            g.text("Each algorithm plays both seats equally; results are shown per algorithm and "
                   "per seat.", (INNER_X, OPT_Y + OPT_H - 104), 13, theme.GREY_TEXT, "medium",
                   max_width=INNER_W)


def _mode_icon(g, key, c):
    x, y = c
    if key == "hva":
        g.piece(0, (x - 9, y - 6), 15)
        g.piece(1, (x + 11, y + 8), 15)
        g.text("AI", (x + 11, y + 8), 11, theme.WHITE, "bold", "center")
    elif key == "ava":
        g.piece(1, (x - 10, y - 6), 15)
        g.piece(0, (x + 10, y + 8), 15)
        g.text("AI", (x - 10, y - 6), 11, theme.WHITE, "bold", "center")
        g.text("AI", (x + 10, y + 8), 11, theme.WHITE, "bold", "center")
    elif key == "hvh":
        g.piece(0, (x - 10, y), 15)
        g.piece(1, (x + 12, y), 15)
    else:
        for i, h in enumerate((16, 28, 22)):
            g.round_rect((x - 20 + i * 14, y + 16 - h, 10, h), theme.BLUE if i != 1 else theme.AMBER, 3)
        g.line((x - 24, y + 17), (x + 24, y + 17), theme.NAVY, 2)
