"""Benchmark screen: all four pairings played headlessly, reported per seat and per algorithm."""

import threading
import time
import traceback

import pygame

from ..ai.presets import agent_config, describe
from ..game.tournament import COMBOS, REASON_NAMES, build_report, combo_name, run_benchmark
from . import theme
from .app import Screen
from .widgets import Button

WIN = (20, 14, 1240, 692)


class BenchmarkScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.options = None
        self.thread = None
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.records = []
        self.report = None
        self.error = None
        self.total = 0
        self.started = 0.0
        self.finished_at = None
        self.stop_button = Button((1040, 92, 196, 44), "Stop", self.stop, style="danger", size=17)
        self.again_button = Button((1040, 92, 196, 44), "Run again", self.start, size=17)
        self.menu_button = Button((830, 92, 196, 44), "Menu", self.to_menu, style="secondary", size=17)
        self.widgets = [self.stop_button, self.again_button, self.menu_button]

    def enter(self, options=None, **kwargs):
        if options is not None:
            self.options = options
        self.start()

    def leave(self):
        self.stop_event.set()

    def configs(self):
        o = self.options
        extra = {} if o["time"] is None else {"time_limit": o["time"]}
        return {"minimax": agent_config("minimax", o["mm_level"], **extra),
                "mcts": agent_config("mcts", o["mcts_level"], **extra)}

    def start(self):
        if self.thread is not None and self.thread.is_alive():
            return
        self.stop_event = threading.Event()
        self.records = []
        self.report = None
        self.error = None
        self.total = 4 * self.options["games"]
        self.started = time.monotonic()
        self.finished_at = None
        stop_event = self.stop_event
        self.thread = threading.Thread(target=self._run, args=(stop_event,), daemon=True,
                                       name="teeko-benchmark")
        self.thread.start()

    def _run(self, stop_event):
        o = self.options
        try:
            report = run_benchmark(self.configs(), o["games"], o["limit"], o["openings"], seed=1,
                                   jobs=o["jobs"], on_progress=self._progress,
                                   should_stop=stop_event.is_set)
        except Exception:
            with self.lock:
                self.error = traceback.format_exc()
            report = None
        with self.lock:
            if stop_event is self.stop_event:
                self.report = report
                self.finished_at = time.monotonic()

    def _progress(self, done, total, record):
        with self.lock:
            self.records.append(record)

    def stop(self):
        self.stop_event.set()

    def to_menu(self):
        self.stop()
        self.app.switch("start")

    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def handle(self, event, pos):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.to_menu()
            return True
        return super().handle(event, pos)

    def update(self, now):
        run = self.running()
        self.stop_button.visible = run
        self.again_button.visible = not run

    def wants_fast_frames(self, now):
        return False

    # ----------------------------------------------------------------- draw
    def draw(self, g, now):
        g.checkerboard()
        x, y, w, h = WIN
        g.shadow(WIN, 20, 6, 40)
        g.round_rect(WIN, theme.BLUE, 18)
        g.round_rect((x + 3, y + 48, w - 6, 24), theme.WHITE)
        g.round_rect((x + 3, y + 48, w - 6, h - 51), theme.WHITE, 15)
        g.text("Teeko AI", (x + 22, y + 24), 21, theme.WHITE, "semibold", "midleft")
        g.text("—  Benchmark: Minimax vs MCTS", (x + 128, y + 24), 17, (225, 238, 252), "medium", "midleft")

        with self.lock:
            records = list(self.records)
            report = self.report
            error = self.error
        o = self.options
        cfg = self.configs()
        g.text(describe(cfg["minimax"]) + "   vs   " + describe(cfg["mcts"]), (40, 88), 17, theme.NAVY,
               "semibold", max_width=770)
        g.text(f"{o['games']} games per pairing  ·  {o['openings']} random opening plies  ·  "
               f"limit {o['limit']} moves each  ·  {o['jobs']} worker process(es)  ·  seed 1",
               (40, 114), 14, theme.GREY_TEXT, "medium")

        # progress bar
        done = len(records)
        elapsed = (self.finished_at or time.monotonic()) - self.started
        bar = (40, 146, 1196, 16)
        g.round_rect(bar, theme.BLUE_PALE, 8)
        if self.total:
            g.round_rect((bar[0], bar[1], bar[2] * done / self.total, bar[3]), theme.BLUE, 8)
        if self.running():
            state = f"Playing… {done}/{self.total} games · {elapsed:.0f} s"
        elif report is not None and report.get("stopped"):
            state = f"Stopped after {done}/{self.total} games · {elapsed:.0f} s"
        elif report is not None:
            state = f"Finished {done} games in {elapsed:.1f} s"
        else:
            state = "Starting…"
        g.text(state, (40, 172), 14, theme.NAVY, "semibold")
        if error:
            g.paragraph("Benchmark failed:\n" + error.strip().splitlines()[-1], (40, 210), 15, theme.RED_DARK,
                        1180)
            self.draw_widgets(g)
            return

        rep = report if report is not None else build_report(records)
        self._pairings_table(g, rep, 40, 204, 1196)
        self._algorithm_table(g, rep, 40, 470, 1196)
        self.draw_widgets(g)

    def _pairings_table(self, g, rep, x, y, w):
        g.text("By pairing (P1 v P2)", (x, y), 18, theme.BLUE_DARK, "semibold")
        cols = [("Pairing", 0.17), ("Games", 0.06), ("Result share  (P1 · draw · P2)", 0.25),
                ("P1 win", 0.07), ("P2 win", 0.07), ("Draw", 0.06), ("Avg actions", 0.08),
                ("P1 time", 0.07), ("P2 time", 0.07), ("End reasons", 0.10)]
        xs = [x]
        for _, fw in cols[:-1]:
            xs.append(xs[-1] + fw * w)
        hy = y + 30
        g.round_rect((x - 8, hy, w + 16, 30), theme.BLUE_PALE, 8)
        for (name, fw), cx in zip(cols, xs):
            g.text(name, (cx, hy + 15), 13, theme.GREY_LABEL, "semibold", "midleft")
        for i, combo in enumerate(COMBOS):
            st = rep["by_combo"][combo]
            ry = hy + 52 + i * 46
            g.text(combo_name(combo), (xs[0], ry), 16, theme.NAVY, "semibold", "midleft")
            if not st.games:
                g.text("waiting…", (xs[1], ry), 14, theme.USED_TEXT, "medium", "midleft")
                continue
            s = st.seat_summary()
            t1, t2 = st.seat_times()
            g.text(str(s["games"]), (xs[1], ry), 15, theme.NAVY, "medium", "midleft")
            bx, bw = xs[2], cols[2][1] * w - 20
            segs = ((s["p1_pct"], theme.RED), (s["draw_pct"], theme.USED_BORDER), (s["p2_pct"], theme.BLUE_PIECE))
            cx = bx
            for pct, color in segs:
                if pct > 0:
                    g.round_rect((cx, ry - 9, bw * pct / 100, 18), color, 4)
                cx += bw * pct / 100
            for j, val in enumerate((f"{s['p1_pct']:.0f}%", f"{s['p2_pct']:.0f}%", f"{s['draw_pct']:.0f}%",
                                     f"{st.avg_plies():.1f}", f"{t1:.2f} s", f"{t2:.2f} s")):
                g.text(val, (xs[3 + j], ry), 15, theme.NAVY, "medium", "midleft")
            reasons = ", ".join(f"{REASON_NAMES[k]} {v}" for k, v in st.reasons().most_common())
            g.text(reasons, (xs[9], ry), 13, theme.GREY_TEXT, "medium", "midleft", max_width=cols[9][1] * w + 30)

    def _algorithm_table(self, g, rep, x, y, w):
        g.text("Minimax vs MCTS — sides balanced (both cross pairings pooled)", (x, y), 18,
               theme.BLUE_DARK, "semibold")
        cross = rep["cross"]
        cols = [("Algorithm", 0.16), ("Wins", 0.07), ("Losses", 0.07), ("Draws", 0.07), ("Win rate", 0.09),
                ("Score", 0.08), ("Wins as P1", 0.11), ("Wins as P2", 0.11), ("Avg decision", 0.12)]
        xs = [x]
        for _, fw in cols[:-1]:
            xs.append(xs[-1] + fw * w)
        hy = y + 30
        g.round_rect((x - 8, hy, w + 16, 30), theme.BLUE_PALE, 8)
        for (name, fw), cx in zip(cols, xs):
            g.text(name, (cx, hy + 15), 13, theme.GREY_LABEL, "semibold", "midleft")
        agents = cross.agent_summary()
        for i, name in enumerate(("Minimax", "MCTS")):
            ry = hy + 50 + i * 40
            g.text(name, (xs[0], ry), 16, theme.NAVY, "semibold", "midleft")
            a = agents.get(name)
            if a is None:
                g.text("waiting…", (xs[1], ry), 14, theme.USED_TEXT, "medium", "midleft")
                continue
            vals = (a["wins"], a["losses"], a["draws"], f"{a['win_pct']:.0f}%", f"{a['score_pct']:.0f}%",
                    f"{a['wins_as_p1']}/{a['as_p1']}", f"{a['wins_as_p2']}/{a['as_p2']}",
                    f"{a['avg_time']:.2f} s")
            for j, v in enumerate(vals):
                g.text(str(v), (xs[1 + j], ry), 15, theme.NAVY, "medium", "midleft")
        if cross.games:
            s = cross.seat_summary()
            g.text(f"By seat in these games: P1 (Red) {s['p1_pct']:.0f}%  ·  P2 (Blue) {s['p2_pct']:.0f}%  ·  "
                   f"draws {s['draw_pct']:.0f}%      Score counts a draw as half a win.",
                   (x, hy + 140), 14, theme.GREY_TEXT, "medium")
