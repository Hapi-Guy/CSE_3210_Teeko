"""Headless GUI smoke test (SDL dummy video driver).

Drives the real screens with synthetic mouse events. Set TEEKO_SCREENSHOTS to a
directory to save a PNG of each step.
"""

import os
import time
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import helpers  # noqa: E402,F401  (puts the project on sys.path)

try:
    import pygame  # noqa: E402
except ImportError:  # pragma: no cover
    pygame = None

from teeko.engine.board import parse_cell  # noqa: E402
from teeko.engine.state import SWAP  # noqa: E402

SHOTS = os.environ.get("TEEKO_SCREENSHOTS")


@unittest.skipIf(pygame is None, "pygame is not installed")
class UISmokeTest(unittest.TestCase):
    def setUp(self):
        from teeko.ui.app import App
        self.app = App(size=(1600, 900))
        self.app.frame()

    def tearDown(self):
        for screen in self.app.screens.values():
            screen.leave()
        pygame.quit()

    # ----------------------------------------------------------- helpers
    def px(self, x, y):
        g = self.app.g
        return (round(g.ox + x * g.scale), round(g.oy + y * g.scale))

    def click(self, x, y, frames=1):
        pos = self.px(x, y)
        for etype, extra in ((pygame.MOUSEMOTION, {"rel": (0, 0), "buttons": (0, 0, 0)}),
                             (pygame.MOUSEBUTTONDOWN, {"button": 1}),
                             (pygame.MOUSEBUTTONUP, {"button": 1})):
            self.app.dispatch(pygame.event.Event(etype, pos=pos, **extra))
        for _ in range(frames):
            self.app.frame()

    def key(self, k):
        self.app.dispatch(pygame.event.Event(pygame.KEYDOWN, key=k, mod=0, unicode="", scancode=0))
        self.app.frame()

    def click_cell(self, name):
        board = self.app.screens["game"].board
        self.click(*board.center(parse_cell(name)), frames=2)

    def frames_until(self, predicate, timeout=60.0):
        end = time.time() + timeout
        while time.time() < end:
            self.app.frame()
            if predicate():
                return True
        return False

    def shot(self, name):
        if SHOTS:
            os.makedirs(SHOTS, exist_ok=True)
            pygame.image.save(self.app.surface, os.path.join(SHOTS, f"{name}.png"))

    def game(self):
        return self.app.screens["game"]

    # ------------------------------------------------------------- tests
    def test_start_screen_modes(self):
        from teeko.ui.setup_screen import StartScreen
        start = self.app.current
        self.assertIsInstance(start, StartScreen)
        for i, key in enumerate(("hva", "ava", "hvh", "bench")):
            r = start._mode_rects()[key]
            self.click(r[0] + r[2] / 2, r[1] + r[3] / 2)
            self.assertEqual(start.selected, key)
            self.shot(f"01_start_{key}")

    def test_human_vs_ai_by_clicking(self):
        s = self.app.settings
        s.mode, s.human_side = "hva", 0
        s.ai.algorithm, s.ai.level = "minimax", "easy"
        self.app.switch("game", settings=s.copy())
        self.click_cell("C3")
        game = self.game()
        self.assertEqual(game.match.state.ply, 1, "the human's placement was applied")
        self.assertTrue(self.frames_until(lambda: game.match.state.ply >= 2 or game.match.over, 20))
        self.shot("02_hva_after_first_moves")
        # keep placing on free cells until the placement phase ends or the game finishes
        for name in ("B2", "D4", "E5", "A1", "B4", "D2"):
            if game.match.over or not game.match.state.in_placement:
                break
            if game.match.is_human_turn():
                self.click_cell(name)
            self.frames_until(lambda: game.match.is_human_turn() or game.match.over, 20)
        self.shot("03_hva_midgame")
        self.assertGreaterEqual(len(game.match.history), 3)

    def test_ai_vs_ai_all_combinations_finish(self):
        for i, (a, b) in enumerate((("minimax", "minimax"), ("minimax", "mcts"),
                                    ("mcts", "minimax"), ("mcts", "mcts"))):
            s = self.app.settings
            s.mode, s.delay, s.series = "ava", 0.0, False
            s.seats[0].algorithm, s.seats[0].level = a, "easy"
            s.seats[1].algorithm, s.seats[1].level = b, "easy"
            self.app.switch("game", settings=s.copy())
            game = self.game()
            self.assertEqual(game.match.status, "ready")
            self.key(pygame.K_n)                         # Step: exactly one move
            self.assertTrue(self.frames_until(lambda: game.match.state.ply == 1, 20))
            self.app.frame()
            self.assertEqual(game.match.status, "paused")
            self.click(*_center(game.run_button.rect))   # Resume
            self.assertTrue(self.frames_until(lambda: game.match.over, 120), (a, b))
            self.frames_until(lambda: game.overlay is not None and game.overlay.get("visible"), 5)
            self.shot(f"04_ava_{a}_vs_{b}_result")
            self.assertTrue(game.overlay and game.overlay.get("visible"))

    def test_series_auto_play(self):
        s = self.app.settings
        s.mode, s.delay, s.series, s.series_games, s.openings = "ava", 0.0, True, 2, 2
        s.seats[0].algorithm, s.seats[0].level = "minimax", "easy"
        s.seats[1].algorithm, s.seats[1].level = "mcts", "easy"
        self.app.switch("game", settings=s.copy())
        game = self.game()
        game.series.gap = 0.1
        self.key(pygame.K_SPACE)
        self.assertTrue(self.frames_until(lambda: game.series.finished, 180))
        self.frames_until(lambda: game.overlay is not None and game.overlay.get("visible"), 5)
        self.shot("05_series_summary")
        self.assertEqual(game.series.stats.games, 2)

    def test_human_vs_human_specials(self):
        s = self.app.settings
        s.mode = "hvh"
        self.app.switch("game", settings=s.copy())
        game = self.game()
        for name in ("A1", "C2", "E1", "B3", "A5", "D3", "E5", "C4"):
            self.click_cell(name)
        self.assertEqual(game.match.state.phase, "movement")
        # Red shuttles A1<->A2 four times while Blue makes different moves
        for red, blue in ((("A1", "A2"), ("C2", "C1")), (("A2", "A1"), ("B3", "B2")),
                          (("A1", "A2"), ("C4", "D4")), (("A2", "A1"), None)):
            self.click_cell(red[0])
            self.click_cell(red[1])
            if blue:
                self.click_cell(blue[0])
                self.click_cell(blue[1])
        st = game.match.state
        self.assertEqual(st.unlocked, (False, True), "Blue unlocked by Red's shuttle")
        self.shot("06_hvh_specials_unlocked")
        swap_rect = game._special_button_rects(1)[0]
        self.click(*_center(swap_rect))
        self.assertEqual(game.special_mode, "swap")
        self.click_cell("D4")
        self.shot("07_hvh_swap_targeting")
        self.click_cell("E5")
        last = game.match.history[-1]
        self.assertEqual(last.move[0], SWAP)
        self.frames_until(lambda: False, 0.6)
        self.shot("08_hvh_after_swap")

    def test_benchmark_screen(self):
        start = self.app.current
        start.selected = "bench"
        start.bench.update({"games": 2, "mm_level": "easy", "mcts_level": "easy", "jobs": 1})
        start.rebuild()
        self.click(*_center(start.start_button.rect))
        bench = self.app.screens["bench"]
        self.assertIs(self.app.current, bench)
        self.assertTrue(self.frames_until(lambda: bench.report is not None, 180))
        self.app.frame()
        self.shot("09_benchmark")
        self.assertEqual(len(bench.report["results"]), 8)
        self.assertIsNone(bench.error)


def _center(rect):
    return rect[0] + rect[2] / 2, rect[1] + rect[3] / 2


if __name__ == "__main__":
    unittest.main()
