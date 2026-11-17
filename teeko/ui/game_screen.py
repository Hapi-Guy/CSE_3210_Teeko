"""The game screen: the proposal's slide-10 mockup ("Teeko AI — Concept") made real."""

import math
import random

import pygame

from ..ai.evaluation import MATE_THRESHOLD
from ..ai.presets import ALGORITHM_NAMES, LEVEL_NAMES
from ..engine.notation import PLAYER_NAMES, move_text, result_headline, result_reason
from ..engine.rules import legal_moves, special_status
from ..engine.state import FLY, PLACE, STEP, SWAP
from ..game.match import Match, Series
from . import theme
from .app import Screen
from .board_view import BoardView
from .settings import MODE_NAMES
from .widgets import Button, Dropdown, Segmented, Selector, Slider, inside, spinner

WIN_X, WIN_Y, WIN_W, WIN_H = 20, 14, 1240, 692
LEFT = (36, 76, 248, 614)
BOARD_CARD = (298, 76, 572, 614)
STATUS_CARD = (884, 76, 360, 152)
SPECIAL_CARD = (884, 238, 360, 160)
MOVES_CARD = (884, 408, 360, 172)
AI_CARD = (884, 590, 360, 100)
LX, LW = 52, 216
ROW_H = 22

LEVEL_OPTIONS = [(lv, LEVEL_NAMES[lv]) for lv in ("easy", "medium", "hard", "expert", "custom")]
ALGO_OPTIONS = [("minimax", "Minimax"), ("mcts", "MCTS")]
PLAY_TYPES = [("hva", "Human vs AI"), ("ava", "AI vs AI"), ("hvh", "Human vs Human")]


class GameScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.board = BoardView((306, 86, 556, 520))
        self.settings = app.settings.copy()
        self.pending = self.settings.copy()
        self.series = None
        self._match = None
        self.toasts = []
        self.overlay = None              # result overlay state
        self.overlay_at = None
        self.history_scroll = 0
        self.follow_history = True
        self.sel = None
        self.special_mode = None
        self.hover_cell = None
        self.last_ai = None              # (player, stats) of the latest AI decision

    # ------------------------------------------------------------ lifecycle
    def enter(self, settings=None, **kwargs):
        if settings is not None:
            self.settings = settings.copy()
        self.pending = self.settings.copy()
        self.new_game()

    def leave(self):
        if self.series is not None:
            self.series.match.cancel()
        if self._match is not None:
            self._match.cancel()

    @property
    def match(self) -> Match:
        return self.series.match if self.series is not None else self._match

    def new_game(self):
        self.leave()
        st = self.settings
        seed = random.randrange(1 << 30)
        if st.mode == "ava" and st.series:
            self.series = Series(st.seats[0].config(), st.seats[1].config(), st.series_games,
                                 st.alternate, st.openings, st.limit, st.delay, seed=seed)
            self._match = None
        else:
            self.series = None
            delay = st.delay if st.mode == "ava" else 0.35
            self._match = Match(st.players(), st.limit, delay, seed=seed,
                                autostart=st.mode != "ava")
        self.board.reset(self.match.state)
        self.toasts.clear()
        self.overlay = None
        self.overlay_at = None
        self.history_scroll = 0
        self.follow_history = True
        self.sel = None
        self.special_mode = None
        self.last_ai = None
        self.build_left_panel()
        if st.mode == "ava":
            self.toast("Press Start (or Space) to begin. Step (N) plays one move.", 6)
        elif st.mode == "hva" and st.human_side == 1:
            self.toast("The AI plays Red and moves first.", 3)

    def apply_pending(self):
        self.settings = self.pending.copy()
        self.app.settings = self.settings.copy()
        self.new_game()

    def restart(self):
        if self.series is not None:
            self.series.restart()
        else:
            self.match.restart()
        self.board.reset(self.match.state)
        self.overlay = None
        self.overlay_at = None
        self.sel = None
        self.special_mode = None
        self.last_ai = None
        self.history_scroll = 0
        self.follow_history = True

    # ----------------------------------------------------------- left panel
    def build_left_panel(self):
        p = self.pending
        self.widgets = []
        self.new_button = Button((LX, 92, LW, 52), "New Game", self.apply_pending, size=22)
        self.widgets.append(self.new_button)

        def set_type(v):
            p.mode = v
            self.build_left_panel()
        self.widgets.append(Dropdown((LX, 176, LW, 42), PLAY_TYPES, p.mode, set_type))

        if p.mode == "ava":
            for seat in (0, 1):
                y = 250 + seat * 96
                cfg = p.seats[seat]

                def set_algo(v, cfg=cfg):
                    cfg.algorithm = v

                def set_level(v, cfg=cfg):
                    cfg.level = v
                self.widgets.append(Segmented((LX, y, LW, 32), ALGO_OPTIONS, cfg.algorithm, set_algo,
                                              size=14))
                self.widgets.append(Selector((LX, y + 38, LW, 28), LEVEL_OPTIONS, cfg.level, set_level,
                                             size=14))
        elif p.mode == "hva":
            def set_side(v):
                p.human_side = v

            def set_algo(v):
                p.ai.algorithm = v

            def set_level(v):
                p.ai.level = v
            self.widgets.append(Segmented((LX, 250, LW, 32), [(0, "Red"), (1, "Blue")], p.human_side,
                                          set_side, size=14))
            self.widgets.append(Segmented((LX, 346, LW, 32), ALGO_OPTIONS, p.ai.algorithm, set_algo,
                                          size=14))
            self.widgets.append(Selector((LX, 384, LW, 28), LEVEL_OPTIONS, p.ai.level, set_level,
                                         size=14))

        self.run_button = Button((LX, 498, LW, 40), "▶  Start", self.toggle_run, size=17)
        self.step_button = Button((LX, 546, 104, 34), "Step", self.step, style="secondary", size=15)
        self.restart_button = Button((LX + 112, 546, 104, 34), "Restart", self.restart,
                                     style="secondary", size=15)
        self.delay_slider = Slider((LX, 590, LW, 38), 0.0, 3.0, self.settings.delay, self.set_delay,
                                   step=0.1, fmt="{:.1f} s", label="Delay", size=13)
        self.menu_button = Button((LX, 664, LW, 24), "‹ Back to menu", self.to_menu, style="link",
                                  size=14, weight="medium")
        ai_game = self.settings.mode == "ava"
        if ai_game:
            self.widgets += [self.run_button, self.step_button, self.restart_button, self.delay_slider]
        else:
            self.restart_button.rect = (LX, 498, LW, 40)
            self.restart_button.size = 17
            self.widgets.append(self.restart_button)
        self.widgets.append(self.menu_button)

    def set_delay(self, v):
        self.settings.delay = v
        self.pending.delay = v
        if self.series is not None:
            self.series.set_delay(v)
        else:
            self.match.set_delay(v)

    def toggle_run(self):
        target = self.series if self.series is not None else self.match
        if self.match.status == "ready":
            target.start()
        else:
            target.toggle_pause()

    def step(self):
        target = self.series if self.series is not None else self.match
        target.step()

    def to_menu(self):
        self.leave()
        self.app.switch("start")

    # ----------------------------------------------------------- updating
    def toast(self, text, seconds=3.5, color=theme.NAVY):
        self.toasts = [t for t in self.toasts if t[0] != text][-1:]
        self.toasts.append((text, color, None, seconds))

    def update(self, now):
        if self.series is not None:
            if self.series.update(now):
                self.board.reset(self.match.state)
                ids = self.series.seats(self.series.index)
                self.toast(f"Game {self.series.index + 1} of {self.series.games}: "
                           f"Agent {ids[0]} plays Red, Agent {ids[1]} plays Blue.", 4)
                self.last_ai = None
                self.overlay = None
        else:
            self.match.update(now)

        m = self.match
        for ev in m.pop_events():
            kind = ev["type"]
            if kind == "move":
                rec = ev["record"]
                self.board.on_move(rec.move, ev["before"], ev["after"], now)
                self.follow_history = True
                self.sel = None
                self.special_mode = None
                if rec.stats is not None:
                    self.last_ai = (rec.player, rec.stats, rec.move)
                if rec.move[0] in (SWAP, FLY):
                    name = "Swap" if rec.move[0] == SWAP else "Fly"
                    self.toast(f"{PLAYER_NAMES[rec.player]} used {name}: {move_text(rec.move)}", 4,
                               theme.AMBER_DARK)
            elif kind == "unlock":
                self.toast(f"{PLAYER_NAMES[ev['by']]} shuttled one piece back and forth four times — "
                           f"{PLAYER_NAMES[ev['player']]} unlocks Swap & Fly!", 6, theme.AMBER_DARK)
            elif kind == "over":
                self.overlay_at = now + 0.9
                if self.series is not None:
                    r = ev["result"]
                    ids = self.series.seats(self.series.index)
                    who = "Draw" if r.winner is None else \
                        f"{PLAYER_NAMES[r.winner]} (Agent {ids[r.winner]}) wins"
                    self.toast(f"Game {self.series.index + 1}/{self.series.games}: {who} — "
                               f"{_reason_short(r)}", 3)
            elif kind == "restart":
                self.board.reset(m.state)

        if self.overlay_at is not None and now >= self.overlay_at:
            self.overlay_at = None
            if self.series is None or self.series.finished:
                self.overlay = {"visible": True}
        self.toasts = [(t, c, start if start is not None else now, d)
                       for t, c, start, d in self.toasts if start is None or now - start < d]
        self._update_buttons()

    def _update_buttons(self):
        m = self.match
        status = m.status
        if self.series is not None and self.series.paused and status not in ("ready",):
            status = "paused" if status != "over" else status
        self.run_button.text = {"ready": "▶  Start", "running": "❚❚  Pause",
                                "paused": "▶  Resume"}.get(status, "▶  Resume")
        self.run_button.enabled = not (m.over and (self.series is None or self.series.finished))
        self.step_button.enabled = not m.over or (self.series is not None and not self.series.finished)
        changed = self.pending != self.settings
        if changed and not self.new_button.highlight:
            self.toast("Settings changed — press New Game to apply them.", 4)
        self.new_button.highlight = changed

    def wants_fast_frames(self, now):
        return self.board.animating(now) or bool(self.toasts) or self.overlay is not None \
            or not self.match.thinking

    # ------------------------------------------------------------- input
    def handle(self, event, pos):
        if self.overlay and self.overlay.get("visible"):
            return self._handle_overlay(event, pos)
        if event.type == pygame.KEYDOWN:
            return self._handle_key(event)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self._title_buttons(pos):
            return True
        if super().handle(event, pos):
            return True
        if event.type == pygame.MOUSEWHEEL and inside(MOVES_CARD, pos):
            self.history_scroll = max(0, self.history_scroll - event.y * ROW_H)
            self.follow_history = False
            return True
        if event.type == pygame.MOUSEMOTION:
            self.hover_cell = self.board.cell_at(pos) if inside(BOARD_CARD, pos) else None
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self._click_specials(pos):
                return True
            if inside(BOARD_CARD, pos):
                cell = self.board.cell_at(pos)
                if cell is not None:
                    self._click_cell(cell)
                elif self.overlay is not None and not self.overlay.get("visible"):
                    if inside(self._show_result_rect(), pos):
                        self.overlay["visible"] = True
                return True
        return False

    def _handle_key(self, event):
        k = event.key
        if k == pygame.K_ESCAPE:
            if self.sel is not None or self.special_mode is not None:
                self.sel = None
                self.special_mode = None
            else:
                self.to_menu()
            return True
        if self.settings.mode == "ava":
            if k == pygame.K_SPACE:
                self.toggle_run()
                return True
            if k == pygame.K_n:
                self.step()
                return True
        if k == pygame.K_r:
            self.restart()
            return True
        return False

    def _title_buttons(self, pos):
        for i, action in enumerate((pygame.display.iconify, self.app.toggle_fullscreen, self.to_menu)):
            cx = WIN_X + WIN_W - 86 + i * 30
            if math.hypot(pos[0] - cx, pos[1] - (WIN_Y + 24)) <= 12:
                action()
                return True
        return False

    def _human_turn_ready(self):
        m = self.match
        return m.is_human_turn() and m.status != "over"

    def _click_cell(self, cell):
        m = self.match
        if not self._human_turn_ready():
            return
        s = m.state
        p = s.turn
        own, opp = s.boards[p], s.boards[1 - p]
        is_own = own >> cell & 1
        is_opp = opp >> cell & 1
        if s.in_placement:
            if not (is_own or is_opp):
                m.submit_human_move((PLACE, -1, cell))
            return
        if self.special_mode == "swap":
            if is_own:
                self.sel = cell
            elif is_opp and self.sel is not None:
                m.submit_human_move((SWAP, self.sel, cell))
            return
        if self.special_mode == "fly":
            if is_own:
                self.sel = cell
            elif not is_opp and self.sel is not None:
                m.submit_human_move((FLY, self.sel, cell))
            return
        if is_own:
            self.sel = None if self.sel == cell else cell
        elif self.sel is not None and (STEP, self.sel, cell) in legal_moves(s):
            m.submit_human_move((STEP, self.sel, cell))
        else:
            self.sel = None

    def _special_button_rects(self, player):
        y = SPECIAL_CARD[1] + 30 + player * 62
        return (968, y, 120, 36), (1100, y, 120, 36)

    def _click_specials(self, pos):
        m = self.match
        if not self._human_turn_ready():
            return False
        s = m.state
        p = s.turn
        for name, r in zip(("swap", "fly"), self._special_button_rects(p)):
            if inside(r, pos):
                status = special_status(s, p)[0 if name == "swap" else 1]
                if status == "available" and not s.in_placement:
                    self.special_mode = None if self.special_mode == name else name
                    self.sel = None
                return True
        return False

    def _handle_overlay(self, event, pos):
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_ESCAPE, pygame.K_SPACE):
                self.overlay["visible"] = False
            elif event.key in (pygame.K_RETURN, pygame.K_r):
                self._overlay_again()
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for label, r, action in self._overlay_buttons():
                if inside(r, pos):
                    action()
                    return True
        if event.type == pygame.MOUSEMOTION:
            self.overlay["hover"] = next((label for label, r, _ in self._overlay_buttons()
                                          if inside(r, pos)), None)
        return True

    def _overlay_again(self):
        self.overlay = None
        if self.series is not None:
            self.series.restart()
            self.series.start()
            self.board.reset(self.match.state)
        else:
            self.restart()
            if self.settings.mode == "ava":
                self.match.start()

    def _overlay_buttons(self):
        x, y, w, h = self._overlay_rect()
        bw = (w - 64 - 24) / 3
        by = y + h - 70
        return [("Play again", (x + 32, by, bw, 46), self._overlay_again),
                ("Menu", (x + 32 + bw + 12, by, bw, 46), self.to_menu),
                ("View board", (x + 32 + 2 * (bw + 12), by, bw, 46),
                 lambda: self.overlay.__setitem__("visible", False))]

    # ---------------------------------------------------------- drawing
    def draw(self, g, now):
        g.checkerboard()
        self._draw_window(g)
        self._draw_left(g)
        self._draw_board(g, now)
        self._draw_status(g, now)
        self._draw_specials(g)
        self._draw_moves(g)
        self._draw_ai(g, now)
        self.draw_widgets(g)
        if self.overlay and self.overlay.get("visible"):
            self._draw_overlay(g)

    def _draw_window(self, g):
        g.shadow((WIN_X, WIN_Y, WIN_W, WIN_H), 20, 6, 40)
        g.round_rect((WIN_X, WIN_Y, WIN_W, WIN_H), theme.BLUE, 18)
        g.round_rect((WIN_X + 3, WIN_Y + 48, WIN_W - 6, 24), theme.WHITE, 0)
        g.round_rect((WIN_X + 3, WIN_Y + 48, WIN_W - 6, WIN_H - 51), theme.WHITE, 15)
        mode = MODE_NAMES[self.settings.mode]
        if self.series is not None:
            mode += f" · series game {self.series.index + 1}/{self.series.games}"
        g.text("Teeko AI", (WIN_X + 22, WIN_Y + 24), 21, theme.WHITE, "semibold", "midleft")
        g.text("—  " + mode, (WIN_X + 22 + g.text_width("Teeko AI", 21, "semibold") + 10, WIN_Y + 24),
               17, (225, 238, 252), "medium", "midleft")
        for i in range(3):
            cx, cy = WIN_X + WIN_W - 86 + i * 30, WIN_Y + 24
            hover = math.hypot(self.app.mouse[0] - cx, self.app.mouse[1] - cy) <= 12
            g.circle((cx, cy), 10, theme.WHITE if not hover else theme.AMBER_PALE)
            if i == 0:
                g.line((cx - 4.5, cy), (cx + 4.5, cy), theme.BLUE, 2.2)
            elif i == 1:
                g.round_rect((cx - 4.5, cy - 4.5, 9, 9), None, 1.5, theme.BLUE, 2)
            else:
                g.line((cx - 4, cy - 4), (cx + 4, cy + 4), theme.BLUE, 2.2)
                g.line((cx - 4, cy + 4), (cx + 4, cy - 4), theme.BLUE, 2.2)

    def _draw_left(self, g):
        g.round_rect(LEFT, theme.WHITE, 12, theme.BLUE_LINE, 2)
        p = self.pending
        g.text("Play Type", (LX, 154), 15, theme.GREY_LABEL, "semibold")
        if p.mode == "ava":
            for seat in (0, 1):
                y = 250 + seat * 96
                g.piece(seat, (LX + 7, y - 13), 6)
                g.text(f"AI Mode {seat + 1}", (LX + 18, y - 13), 15, theme.GREY_LABEL, "semibold",
                       "midleft")
        elif p.mode == "hva":
            g.text("You play", (LX, 230), 15, theme.GREY_LABEL, "semibold")
            g.piece(1 - p.human_side, (LX + 7, 333), 6)
            g.text("AI Mode", (LX + 18, 333), 15, theme.GREY_LABEL, "semibold", "midleft")
        else:
            g.paragraph("Two players share the mouse. Shuttle a piece A→B→A→B→A to unlock the "
                        "other side's Swap and Fly.", (LX, 236), 14, theme.NAVY, LW)
        g.text("Game phase", (LX, 430), 15, theme.GREY_LABEL, "semibold")
        phase = self.match.state.phase
        for i, (name, active) in enumerate((("Place", phase == "placement"), ("Move", phase == "movement"))):
            r = (LX + i * 112, 452, 104, 34)
            g.round_rect(r, theme.BLUE if active else theme.BLUE_PALE, 10)
            g.text(name, (r[0] + 52, r[1] + 17), 16, theme.WHITE if active else theme.USED_TEXT,
                   "semibold", "center")
        g.line((LX, 488 - 0), (LX + LW, 488), theme.BLUE_LINE, 1.5)
        if self.settings.mode != "ava":
            hint = ("Click an empty point to place a piece. Then click one of your pieces and an amber "
                    "point to move. Esc cancels.")
            g.paragraph(hint, (LX, 552), 13, theme.GREY_TEXT, LW)
        if self.series is not None:
            self._draw_series(g)

    def _draw_series(self, g):
        st = self.series.stats
        agents = st.agent_summary()
        a = agents.get("Agent A", {"wins": 0})
        b = agents.get("Agent B", {"wins": 0})
        draws = st.seat_summary()["draws"]
        y = 634
        g.text(f"Series {min(self.series.index + 1, self.series.games)}/{self.series.games}", (LX, y),
               13, theme.GREY_LABEL, "semibold")
        g.text(f"A {a['wins']}  ·  B {b['wins']}  ·  draws {draws}", (LX + LW, y), 13, theme.NAVY,
               "semibold", "topright")

    def _board_overlay(self, now):
        m = self.match
        s = m.state
        ov = {}
        if m.history:
            ov["last_move"] = m.history[-1].move
        if s.result is not None and s.result.pattern is not None:
            ov["win"] = s.result.pattern
        badges = []
        for p in (0, 1):
            last = s.last_step[p]
            if last is not None and s.streak[p] >= 2 and not s.unlocked[1 - p] and s.result is None:
                f, t = last[1], last[2]
                a, b = (f, t) if s.streak[p] % 2 else (t, f)
                badges += [(a, "A"), (b, "B")]
        ov["badges"] = badges
        if not self._human_turn_ready():
            return ov
        p = s.turn
        own, opp = s.boards[p], s.boards[1 - p]
        empty = [c for c in range(25) if not ((own | opp) >> c & 1)]
        own_cells = [c for c in range(25) if own >> c & 1]
        opp_cells = [c for c in range(25) if opp >> c & 1]
        hover = self.hover_cell
        if s.in_placement:
            if hover in empty:
                ov["hover"] = hover
            return ov
        if self.special_mode is not None:
            if self.sel is None:
                ov["selectable"] = own_cells
            else:
                ov["selected"] = self.sel
                ov["targets"] = opp_cells if self.special_mode == "swap" else empty
                ov["target_style"] = "ring" if self.special_mode == "swap" else "dot"
            if hover in own_cells or (self.sel is not None and hover in ov.get("targets", ())):
                ov["hover"] = hover
            return ov
        if self.sel is not None:
            ov["selected"] = self.sel
            ov["targets"] = [t for k, f, t in legal_moves(s) if k == STEP and f == self.sel]
        if hover in own_cells or hover in ov.get("targets", ()):
            ov["hover"] = hover
        return ov

    def _draw_board(self, g, now):
        g.round_rect(BOARD_CARD, theme.BLUE_PALE, 18, theme.BLUE, 2.5)
        self.board.draw(g, now, self._board_overlay(now))
        # footer: hint or toast
        fx, fy, fw = BOARD_CARD[0] + 16, BOARD_CARD[1] + BOARD_CARD[3] - 50, BOARD_CARD[2] - 32
        if self.overlay is not None and not self.overlay.get("visible"):
            r = self._show_result_rect()
            g.round_rect(r, theme.BLUE, 17)
            g.text("Show result", (r[0] + r[2] / 2, r[1] + r[3] / 2), 15, theme.WHITE, "semibold", "center")
            return
        if self.toasts:
            text, color, _, _ = self.toasts[-1]
            accent = color == theme.AMBER_DARK
            box = (fx, fy - 2, fw, 40)
            g.round_rect(box, theme.AMBER_PALE if accent else theme.WHITE, 12,
                         theme.AMBER if accent else theme.BLUE_LINE, 2)
            g.text(text, (fx + fw / 2, fy + 18), 14, theme.NAVY, "medium", "center", max_width=fw - 20)
            return
        g.text(self._hint(), (fx + fw / 2, fy + 18), 14, theme.GREY_TEXT, "medium", "center",
               max_width=fw)

    def _show_result_rect(self):
        return (BOARD_CARD[0] + BOARD_CARD[2] / 2 - 70, BOARD_CARD[1] + BOARD_CARD[3] - 52, 140, 34)

    def _hint(self):
        m = self.match
        s = m.state
        if s.result is not None:
            return "Game over — press Restart (R) or New Game."
        if m.status == "ready":
            return "Ready — press Start."
        if m.status == "paused":
            return "Paused — Resume (Space) or Step (N)."
        if m.is_ai_turn():
            return f"{PLAYER_NAMES[s.turn]} ({m.players[s.turn].label}) is thinking…"
        name = PLAYER_NAMES[s.turn]
        if s.in_placement:
            return f"{name}: click any empty point to place a piece ({4 - s.boards[s.turn].bit_count()} left)."
        if self.special_mode == "swap":
            return ("Swap: pick one of your pieces." if self.sel is None
                    else "Swap: now pick an opponent piece to trade places with.")
        if self.special_mode == "fly":
            return ("Fly: pick one of your pieces." if self.sel is None
                    else "Fly: pick any empty point.")
        return f"{name}: select one of your pieces, then an amber point (diagonals allowed)."

    def _draw_status(self, g, now):
        x, y, w, h = STATUS_CARD
        g.round_rect(STATUS_CARD, theme.WHITE, 12, theme.BLUE_LINE, 2)
        g.text("STATUS", (x + 16, y + 12), 13, theme.GREY_LABEL, "semibold")
        m = self.match
        s = m.state
        r = s.result
        if r is not None:
            if r.winner is not None:
                g.piece(r.winner, (x + 31, y + 54), 15)
            head = result_headline(r)
        else:
            g.piece(s.turn, (x + 31, y + 54), 15)
            name = PLAYER_NAMES[s.turn]
            if m.players[s.turn].is_ai:
                head = f"{name} is thinking…" if m.thinking else f"{name} to move"
            else:
                head = f"{name} to move" + (" (you)" if self.settings.mode == "hva" else "")
        g.text(head, (x + 56, y + 54), 23, theme.NAVY, "semibold", "midleft", max_width=w - 100)
        if m.thinking:
            spinner(g, (x + w - 30, y + 54), 11, now)
        phase = {"placement": "Placement phase", "movement": "Movement phase", "over": "Game over"}[s.phase]
        g.text(f"{phase} · Turn {s.ply + 1 if r is None else s.ply}", (x + 16, y + 80), 15,
               theme.GREY_TEXT, "medium")
        for p in (0, 1):
            ry = y + 108 + p * 22
            g.piece(p, (x + 22, ry), 6)
            g.text(PLAYER_NAMES[p], (x + 34, ry), 14, theme.NAVY, "medium", "midleft")
            bx, bw = x + 84, w - 190
            used = s.move_counts[p]
            g.round_rect((bx, ry - 4, bw, 8), theme.BLUE_PALE, 4)
            if used:
                g.round_rect((bx, ry - 4, bw * min(1, used / s.limit), 8), theme.PLAYER_COLORS[p], 4)
            g.text(f"{used}/{s.limit} moves", (x + w - 16, ry), 13, theme.GREY_TEXT, "medium", "midright")

    def _draw_specials(self, g):
        x, y, w, h = SPECIAL_CARD
        g.round_rect(SPECIAL_CARD, theme.WHITE, 12, theme.BLUE_LINE, 2)
        g.text("SPECIAL MOVES", (x + 16, y + 12), 13, theme.GREY_LABEL, "semibold")
        m = self.match
        s = m.state
        human_turn = self._human_turn_ready() and not s.in_placement
        for p in (0, 1):
            ry = y + 30 + p * 62
            current = s.turn == p and s.result is None
            if current:
                g.round_rect((x + 8, ry - 4, w - 16, 58), theme.BLUE_PALE, 10)
            g.piece(p, (x + 24, ry + 12), 7)
            g.text(PLAYER_NAMES[p], (x + 36, ry + 12), 16, theme.NAVY, "semibold", "midleft")
            streak = s.streak[p] if not s.unlocked[1 - p] else 0
            if streak >= 2 and s.last_step[p] is not None:
                g.text(f"shuttle {min(streak, 4)}/4", (x + 18, ry + 34), 12, theme.AMBER_DARK, "semibold",
                       "midleft")
            statuses = special_status(s, p)
            for name, r, status in zip(("Swap", "Fly"), self._special_button_rects(p), statuses):
                active = human_turn and current and self.special_mode == name.lower()
                _special_button(g, r, name, status, active,
                                clickable=human_turn and current and status == "available",
                                hover=inside(r, self.app.mouse))

    def _draw_moves(self, g):
        x, y, w, h = MOVES_CARD
        g.round_rect(MOVES_CARD, theme.WHITE, 12, theme.BLUE_LINE, 2)
        g.text("RECENT MOVES", (x + 16, y + 12), 13, theme.GREY_LABEL, "semibold")
        hist = self.match.history
        g.text(f"{len(hist)} actions", (x + w - 16, y + 12), 12, theme.GREY_TEXT, "medium", "topright")
        area = (x + 8, y + 32, w - 16, h - 40)
        total = len(hist) * ROW_H
        max_scroll = max(0, total - area[3])
        if self.follow_history:
            self.history_scroll = max_scroll
        self.history_scroll = min(self.history_scroll, max_scroll)
        clip = g.rect(area)
        g.surface.set_clip(clip)
        top = area[1] - self.history_scroll
        first = max(0, int(self.history_scroll // ROW_H) - 1)
        for i in range(first, min(len(hist), first + int(area[3] // ROW_H) + 3)):
            rec = hist[i]
            ry = top + i * ROW_H + ROW_H / 2
            g.text(str(rec.number), (x + 40, ry), 13, theme.GREY_TEXT, "medium", "midright")
            g.circle((x + 52, ry), 4.5, theme.PLAYER_COLORS[rec.player])
            g.text(PLAYER_NAMES[rec.player], (x + 62, ry), 14, theme.NAVY, "semibold", "midleft")
            text = move_text(rec.move)
            tx = x + 108
            if rec.move[0] in (SWAP, FLY):
                tag = "SWAP" if rec.move[0] == SWAP else "FLY"
                tw = g.text_width(tag, 11, "bold") + 12
                g.round_rect((tx, ry - 9, tw, 18), theme.AMBER, 9)
                g.text(tag, (tx + tw / 2, ry), 11, theme.NAVY, "bold", "center")
                tx += tw + 6
                text = text.split(" ", 1)[1]
            g.text(text, (tx, ry), 14, theme.NAVY, "regular", "midleft")
            extra = []
            if rec.repeated:
                extra.append("↺")
            if rec.source == "opening":
                extra.append("random")
            elif rec.think_time is not None and rec.stats is not None:
                extra.append(f"{rec.stats.get('time', rec.think_time):.1f}s")
            if extra:
                g.text("  ".join(extra), (x + w - 16, ry), 12, theme.GREY_TEXT, "medium", "midright")
        g.surface.set_clip(None)
        if not hist:
            g.text("No moves yet", (x + w / 2, y + h / 2 + 10), 14, theme.USED_TEXT, "medium", "center")
        elif max_scroll > 0:
            frac = self.history_scroll / max_scroll
            bar_h = max(20, area[3] * area[3] / total)
            g.round_rect((x + w - 7, area[1] + (area[3] - bar_h) * frac, 3, bar_h), theme.BLUE_LINE, 2)

    def _draw_ai(self, g, now):
        x, y, w, h = AI_CARD
        g.round_rect(AI_CARD, theme.WHITE, 12, theme.BLUE_LINE, 2)
        m = self.match
        s = m.state
        if m.thinking and m.is_ai_turn():
            g.text("AI THINKING", (x + 16, y + 12), 13, theme.GREY_LABEL, "semibold")
            spinner(g, (x + w - 24, y + 20), 8, now)
            spec = m.players[s.turn]
            g.text(f"{PLAYER_NAMES[s.turn]} · {spec.label}", (x + 16, y + 42), 15, theme.NAVY, "semibold",
                   "midleft", max_width=w - 32)
            g.text(_progress_text(m.progress(), spec.agent, now - (m.think_started or now)),
                   (x + 16, y + 66), 13, theme.GREY_TEXT, "medium", "midleft", max_width=w - 32)
            return
        g.text("AI DECISION", (x + 16, y + 12), 13, theme.GREY_LABEL, "semibold")
        if self.last_ai is None:
            msg = "No AI move yet." if any(pl.is_ai for pl in m.players) else "No AI in this game."
            g.text(msg, (x + 16, y + 44), 14, theme.USED_TEXT, "medium", "midleft")
            return
        player, stats, move = self.last_ai
        spec = m.players[player]
        lines = _decision_lines(player, spec, stats, move)
        for i, line in enumerate(lines):
            g.text(line, (x + 16, y + 40 + i * 21), 15 if i == 0 else 13,
                   theme.NAVY if i == 0 else theme.GREY_TEXT, "semibold" if i == 0 else "medium",
                   "midleft", max_width=w - 32)

    # ------------------------------------------------------------ overlay
    def _overlay_rect(self):
        r = self.match.state.result
        tall = r is not None and r.scores is not None
        if self.series is not None:
            tall = True
        h = 440 if tall else 250
        return (640 - 270, 360 - h / 2, 540, h)

    def _draw_overlay(self, g):
        g.round_rect((-400, -400, 2080, 1520), (*theme.NAVY, 120), 0)
        x, y, w, h = self._overlay_rect()
        g.shadow((x, y, w, h), 22, 8, 60)
        g.round_rect((x, y, w, h), theme.WHITE, 22, theme.BLUE, 3)
        g.round_rect((x, y, w, 64), theme.BLUE, 22)
        g.round_rect((x, y + 40, w, 24), theme.BLUE, 0)
        r = self.match.state.result
        if self.series is not None and self.series.finished:
            self._draw_series_summary(g, (x, y, w, h))
        else:
            if r.winner is not None:
                g.piece(r.winner, (x + 40, y + 32), 15)
            g.text(result_headline(r), (x + 66 if r.winner is not None else x + w / 2, y + 32), 28,
                   theme.WHITE, "semibold", "midleft" if r.winner is not None else "center")
            how = {"line": "Normal win", "square": "Normal win", "limit_score": "Decided by limit scoring",
                   "limit_center": "Decided by limit scoring", "draw": "Draw at the movement limit"}
            g.text(how[r.reason], (x + w - 24, y + 32), 15, (225, 238, 252), "medium", "midright")
            ty = g.paragraph(result_reason(r, self.match.state.limit), (x + 28, y + 86), 17, theme.NAVY,
                             w - 56, "medium")
            if r.scores is not None:
                self._draw_score_table(g, r, x + 28, ty + 10, w - 56)
            else:
                st = self.match.state
                g.text(f"{st.ply} actions · movement turns used: Red {st.move_counts[0]}, "
                       f"Blue {st.move_counts[1]}", (x + 28, ty + 8), 14, theme.GREY_TEXT, "medium")
        hover = self.overlay.get("hover")
        for label, rect, _ in self._overlay_buttons():
            primary = label == "Play again"
            fill = (theme.BLUE_DARK if hover == label else theme.BLUE) if primary else \
                (theme.BLUE_PALE if hover == label else theme.WHITE)
            g.round_rect(rect, fill, 14, None if primary else theme.BLUE, 0 if primary else 2)
            text = "New series" if (label == "Play again" and self.series is not None) else label
            g.text(text, (rect[0] + rect[2] / 2, rect[1] + rect[3] / 2), 17,
                   theme.WHITE if primary else theme.NAVY, "semibold", "center")

    def _draw_score_table(self, g, r, x, y, w):
        cols = ["", "1 piece ×1", "2 pieces ×3", "3 pieces ×10", "Score", "Centre"]
        widths = [0.18, 0.17, 0.17, 0.18, 0.14, 0.16]
        cx = [x]
        for fw in widths[:-1]:
            cx.append(cx[-1] + fw * w)
        g.round_rect((x - 8, y - 4, w + 16, 30), theme.BLUE_PALE, 8)
        for i, c in enumerate(cols):
            g.text(c, (cx[i] + (0 if i == 0 else widths[i] * w / 2), y + 11), 13, theme.GREY_LABEL,
                   "semibold", "midleft" if i == 0 else "center")
        for p in (0, 1):
            ry = y + 44 + p * 32
            n1, n2, n3 = r.breakdown[p]
            vals = [str(n1), str(n2), str(n3), str(r.scores[p]), str(r.center[p])]
            g.piece(p, (cx[0] + 8, ry), 7)
            g.text(PLAYER_NAMES[p], (cx[0] + 22, ry), 15, theme.NAVY, "semibold", "midleft")
            for i, v in enumerate(vals, start=1):
                bold = (i == 4 and r.reason == "limit_score") or (i == 5 and r.reason == "limit_center")
                win = bold and r.winner == p
                g.text(v, (cx[i] + widths[i] * w / 2, ry), 16 if bold else 15,
                       theme.GREEN if win else theme.NAVY, "bold" if bold else "medium", "center")
        g.text("Only patterns without opponent pieces count. Ties go to more pieces in the central 3×3.",
               (x, y + 112), 12, theme.GREY_TEXT, "medium", max_width=w)

    def _draw_series_summary(self, g, rect):
        x, y, w, h = rect
        g.text("Series complete", (x + 28, y + 32), 28, theme.WHITE, "semibold", "midleft")
        st = self.series.stats
        agents = st.agent_summary()
        seats = st.seat_summary()
        ty = y + 86
        cfg = {"Agent A": self.series.agents["A"], "Agent B": self.series.agents["B"]}
        for aid in ("Agent A", "Agent B"):
            a = agents.get(aid)
            if a is None:
                continue
            c = cfg[aid]
            name = f"{ALGORITHM_NAMES[c['algorithm']]} ({LEVEL_NAMES[c['level']]})"
            g.text(f"{aid}: {name}", (x + 28, ty), 17, theme.NAVY, "semibold")
            g.text(f"{a['wins']} W · {a['losses']} L · {a['draws']} D   —   win {a['win_pct']:.0f}%   "
                   f"·  as Red {a['wins_as_p1']}/{a['as_p1']}, as Blue {a['wins_as_p2']}/{a['as_p2']}   "
                   f"·  avg {a['avg_time']:.2f} s/move", (x + 28, ty + 26), 13, theme.GREY_TEXT, "medium",
                   max_width=w - 56)
            ty += 64
        g.text(f"By seat: Red (P1) {seats['p1_pct']:.0f}%  ·  Blue (P2) {seats['p2_pct']:.0f}%  ·  "
               f"draws {seats['draw_pct']:.0f}%", (x + 28, ty + 4), 15, theme.NAVY, "medium")
        g.text(f"Average length: {st.avg_plies():.1f} actions · reasons: "
               + ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in st.reasons().most_common()),
               (x + 28, ty + 32), 13, theme.GREY_TEXT, "medium", max_width=w - 56)


# --------------------------------------------------------------------- helpers
def _reason_short(r):
    return {"line": "four in a line", "square": "2×2 square", "limit_score": "limit score",
            "limit_center": "centre tie-break", "draw": "draw"}[r.reason]


def _special_button(g, r, name, status, active, clickable, hover):
    x, y, w, h = r
    if status == "available":
        fill = theme.AMBER_DARK if (hover and clickable) else theme.AMBER
        g.round_rect(r, fill, 10, theme.AMBER_DARK, 2)
        if active:
            g.round_rect((x - 3, y - 3, w + 6, h + 6), None, 12, theme.BLUE, 3)
        g.text(name, (x + w / 2, y + h / 2), 18, theme.NAVY, "semibold", "center")
        caption, color = ("Choose…" if active else "Available"), theme.NAVY
    elif status == "used":
        g.round_rect(r, theme.USED_FILL, 10)
        g.dashed_path([(x + 8, y), (x + w - 8, y), (x + w, y + 8), (x + w, y + h - 8), (x + w - 8, y + h),
                       (x + 8, y + h), (x, y + h - 8), (x, y + 8)], theme.USED_BORDER, 1.8, 6, 4,
                      closed=True)
        g.text(name, (x + w / 2, y + h / 2), 18, theme.USED_TEXT, "semibold", "center", strike=True)
        caption, color = "Used", theme.USED_TEXT
    else:
        g.round_rect(r, theme.WHITE, 10, theme.USED_BORDER, 2)
        g.text(name, (x + w / 2 + 8, y + h / 2), 17, theme.USED_TEXT, "semibold", "center")
        lx, ly = x + 18, y + h / 2
        g.round_rect((lx - 6, ly - 2, 12, 9), theme.USED_BORDER, 2)
        g.circle((lx, ly - 3), 4, theme.USED_BORDER, 1.6)
        caption, color = "Locked", theme.USED_TEXT
    g.text(caption, (x + w / 2, y + h + 9), 11, color, "semibold", "center")


def _fmt_score(score):
    if score is None:
        return "only move"
    if score >= MATE_THRESHOLD:
        return "forced win found"
    if score <= -MATE_THRESHOLD:
        return "forced loss seen"
    return f"eval {score:+d}"


def _decision_lines(player, spec, stats, move):
    head = f"{PLAYER_NAMES[player]} · {spec.label}  →  {move_text(move)}"
    t = stats.get("time", 0.0)
    if stats.get("algorithm") == "Minimax":
        stop = {"time": "time cap", "forced": "forced result", "win": "immediate win",
                "single": "only move"}.get(stats.get("stop"), "full depth")
        line2 = f"depth {stats['depth']}/{stats['max_depth']} · {stats['nodes']:,} nodes · {t:.2f} s ({stop})"
        pv = " ".join(move_text(m).replace("Place ", "") for m in stats.get("pv", [])[:4])
        line3 = f"{_fmt_score(stats.get('score'))} · PV {pv}" if pv else _fmt_score(stats.get("score"))
        return [head, line2, line3]
    stop = {"time": "time cap", "iterations": "budget", "shortcut": "immediate win",
            "single": "only move", "proven": "proven", "fallback": "fallback"}.get(stats.get("stop"), "")
    line2 = f"{stats['simulations']:,}/{stats['max_simulations']:,} sims · {t:.2f} s ({stop})"
    wr = stats.get("win_rate")
    parts = []
    if wr is not None:
        parts.append(f"win {wr:.0%}")
    if stats.get("proven"):
        parts.append(f"proven {stats['proven']}")
    top = stats.get("top") or []
    if top:
        parts.append("top " + ", ".join(f"{move_text(m).replace('Place ', '')} {v}" for m, v, _ in top[:3]))
    return [head, line2, " · ".join(parts) or "—"]


def _progress_text(info, agent, elapsed):
    if not info:
        return f"searching… {elapsed:.1f} s"
    if info.get("algorithm") == "Minimax":
        best = info.get("best")
        best_txt = f" · best {move_text(best)}" if best else ""
        return (f"depth {info.get('depth', 0)} done, searching {info.get('searching', 1)} · "
                f"{info.get('nodes', 0):,} nodes · {info.get('time', 0):.1f} s{best_txt}")
    best = info.get("best")
    return (f"{info.get('simulations', 0):,}/{info.get('max_simulations', 0):,} sims · "
            f"{info.get('time', 0):.1f} s · best {move_text(best) if best else '—'} "
            f"({info.get('win_rate', 0):.0%})")
