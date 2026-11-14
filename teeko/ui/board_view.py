"""The Teeko board as drawn in the proposal: pieces sit on the intersections of a
5x5 grid with dashed diagonals, columns A-E on top and rows 1-5 on the left."""

import math

from ..engine.board import COLUMNS, PATTERNS, SIZE, cell_col, cell_row, cells_of
from ..engine.state import FLY, PLACE, STEP, SWAP
from . import theme

MOVE_TIME = 0.26
FLY_TIME = 0.45
SWAP_TIME = 0.5
POP_TIME = 0.22


def _ease_out(u):
    return 1 - (1 - u) ** 3


def _ease_back(u):
    c = 1.7
    return 1 + (c + 1) * (u - 1) ** 3 + c * (u - 1) ** 2


class _Piece:
    __slots__ = ("player", "cell", "start", "end", "t0", "dur", "kind", "arc")

    def __init__(self, player, cell, pos):
        self.player = player
        self.cell = cell
        self.start = self.end = pos
        self.t0 = 0.0
        self.dur = 0.0
        self.kind = None
        self.arc = 0.0

    def animating(self, now):
        return self.kind is not None and now - self.t0 < self.dur

    def frame(self, now):
        """(position, scale) at time ``now``."""
        if not self.animating(now):
            return self.end, 1.0
        u = max(0.0, min(1.0, (now - self.t0) / self.dur))
        if self.kind == "pop":
            return self.end, 0.35 + 0.65 * _ease_back(u)
        e = _ease_out(u) if self.kind == "move" else (1 - math.cos(math.pi * u)) / 2
        (sx, sy), (ex, ey) = self.start, self.end
        x, y = sx + (ex - sx) * e, sy + (ey - sy) * e
        scale = 1.0
        if self.arc:
            dx, dy = ex - sx, ey - sy
            length = math.hypot(dx, dy) or 1.0
            lift = self.arc * math.sin(math.pi * u) * min(1.0, length / 120)
            x += -dy / length * lift
            y += dx / length * lift
        if self.kind == "fly":
            scale = 1 + 0.2 * math.sin(math.pi * u)
        return (x, y), scale


class BoardView:
    def __init__(self, rect):
        self.pieces = []
        self.set_rect(rect)

    # --------------------------------------------------------------- layout
    def set_rect(self, rect):
        self.rect = rect
        x, y, w, h = rect
        label = 30
        side = min(w - label, h - label)
        self.spacing = (side - 20) / 4.8
        grid = 4 * self.spacing
        self.gx = x + label + (w - label - grid) / 2
        self.gy = y + label + (h - label - grid) / 2
        self.radius = self.spacing * 0.34

    def center(self, cell):
        return (self.gx + cell_col(cell) * self.spacing, self.gy + cell_row(cell) * self.spacing)

    def cell_at(self, pos):
        c = round((pos[0] - self.gx) / self.spacing)
        r = round((pos[1] - self.gy) / self.spacing)
        if 0 <= r < SIZE and 0 <= c < SIZE:
            cx, cy = self.center(r * SIZE + c)
            if math.hypot(pos[0] - cx, pos[1] - cy) <= self.spacing * 0.45:
                return r * SIZE + c
        return None

    # ------------------------------------------------------------ animation
    def reset(self, state):
        self.pieces = [_Piece(p, c, self.center(c)) for p in (0, 1) for c in cells_of(state.boards[p])]

    def _piece_at(self, cell):
        return next((pc for pc in self.pieces if pc.cell == cell), None)

    def on_move(self, move, before, after, now):
        kind, f, t = move
        p = before.turn
        if kind == PLACE:
            pc = _Piece(p, t, self.center(t))
            pc.kind, pc.t0, pc.dur = "pop", now, POP_TIME
            self.pieces.append(pc)
        elif kind in (STEP, FLY):
            pc = self._piece_at(f)
            if pc is not None:
                self._launch(pc, t, now, "fly" if kind == FLY else "move",
                             FLY_TIME if kind == FLY else MOVE_TIME, 34 if kind == FLY else 0)
        elif kind == SWAP:
            a, b = self._piece_at(f), self._piece_at(t)
            if a is not None and b is not None:
                self._launch(a, t, now, "swap", SWAP_TIME, 30)
                self._launch(b, f, now, "swap", SWAP_TIME, 30)
        if not self._consistent(after):
            self.reset(after)

    def _launch(self, pc, cell, now, kind, dur, arc):
        pc.start, _ = pc.frame(now)
        pc.end = self.center(cell)
        pc.cell = cell
        pc.kind, pc.t0, pc.dur, pc.arc = kind, now, dur, arc

    def _consistent(self, state):
        for p in (0, 1):
            cells = {pc.cell for pc in self.pieces if pc.player == p}
            if cells != set(cells_of(state.boards[p])):
                return False
        return True

    def animating(self, now):
        return any(pc.animating(now) for pc in self.pieces)

    # -------------------------------------------------------------- drawing
    def draw(self, g, now, overlay=None):
        ov = overlay or {}
        sp = self.spacing
        gx, gy = self.gx, self.gy
        end = 4 * sp

        # dashed diagonals in every square, then the solid grid
        for r in range(4):
            for c in range(4):
                x0, y0 = gx + c * sp, gy + r * sp
                g.dashed_line((x0, y0), (x0 + sp, y0 + sp), theme.GRID_DIAG, 1, 5, 5)
                g.dashed_line((x0 + sp, y0), (x0, y0 + sp), theme.GRID_DIAG, 1, 5, 5)
        for i in range(5):
            g.line((gx, gy + i * sp), (gx + end, gy + i * sp), theme.GRID, 1.6)
            g.line((gx + i * sp, gy), (gx + i * sp, gy + end), theme.GRID, 1.6)
        for i in range(5):
            g.text(COLUMNS[i], (gx + i * sp, gy - self.radius - 16), 16, theme.GREY_LABEL, "semibold",
                   "center")
            g.text(str(i + 1), (gx - self.radius - 18, gy + i * sp), 16, theme.GREY_LABEL, "semibold",
                   "center")
        for cell in range(25):
            g.circle(self.center(cell), 4.2, theme.POINT)

        last = ov.get("last_move")
        if last is not None and last[0] in (STEP, FLY, SWAP):
            fx, fy = self.center(last[1])
            g.circle_alpha((fx, fy), self.radius * 0.95, theme.GRID, 60)
            g.dashed_path(_circle_points((fx, fy), self.radius * 0.95), theme.GRID, 1.5, 5, 5,
                          closed=True)

        for cell in ov.get("selectable", ()):
            g.dashed_path(_circle_points(self.center(cell), self.radius + 7), theme.AMBER, 2, 6, 5,
                          closed=True)

        hover = ov.get("hover")
        if hover is not None:
            g.circle_alpha(self.center(hover), self.radius + 6, theme.AMBER, 70)

        # pieces (animating ones on top)
        order = sorted(self.pieces, key=lambda pc: pc.animating(now))
        for pc in order:
            pos, scale = pc.frame(now)
            g.piece(pc.player, pos, self.radius, scale)

        if last is not None:
            tx, ty = self.center(last[2])
            g.circle((tx, ty), self.radius + 4, theme.AMBER_PALE if last[0] == PLACE else theme.AMBER, 2)

        sel = ov.get("selected")
        if sel is not None:
            g.circle(self.center(sel), self.radius + 8, theme.AMBER, 4.5)

        ring_targets = ov.get("target_style") == "ring"
        for cell in ov.get("targets", ()):
            c = self.center(cell)
            if ring_targets:            # dashed, like the swap illustration on slide 8
                g.dashed_path(_circle_points(c, self.radius + 7, 36), theme.AMBER_DARK, 3, 7, 5,
                              closed=True)
            else:
                g.circle(c, self.radius * 0.36, theme.AMBER)

        for cell, label in ov.get("badges", ()):
            cx, cy = self.center(cell)
            if label == "B":
                g.dashed_path(_circle_points((cx, cy), self.radius * 0.8), theme.AMBER_DARK, 2, 5, 4,
                              closed=True)
            bx, by = cx - self.radius * 0.85, cy - self.radius * 0.85
            g.circle((bx, by), 12, theme.AMBER)
            g.text(label, (bx, by), 14, theme.NAVY, "bold", "center")

        win = ov.get("win")
        if win is not None:
            self._draw_win(g, win, now)

    def _draw_win(self, g, pattern_index, now):
        cells = PATTERNS[pattern_index].cells
        pad = self.radius + 10
        pts = [self.center(c) for c in cells]
        if PATTERNS[pattern_index].kind == "square":
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            path = _rounded_rect_points(min(xs), min(ys), max(xs), max(ys), pad)
        else:
            path = _capsule_points(pts[0], pts[-1], pad)
        pulse = 0.5 + 0.5 * math.sin(now * 5)
        g.dashed_path(path, theme.AMBER, 3.5 + pulse, 11, 7, closed=True)


def _circle_points(c, r, n=28):
    return [(c[0] + r * math.cos(2 * math.pi * i / n), c[1] + r * math.sin(2 * math.pi * i / n))
            for i in range(n)]


def _capsule_points(a, b, r, n=14):
    ang = math.atan2(b[1] - a[1], b[0] - a[0])
    pts = []
    for i in range(n + 1):
        t = ang - math.pi / 2 + math.pi * i / n
        pts.append((b[0] + r * math.cos(t), b[1] + r * math.sin(t)))
    for i in range(n + 1):
        t = ang + math.pi / 2 + math.pi * i / n
        pts.append((a[0] + r * math.cos(t), a[1] + r * math.sin(t)))
    return pts


def _rounded_rect_points(x0, y0, x1, y1, r, n=8):
    corners = ((x1, y0, -math.pi / 2), (x1, y1, 0), (x0, y1, math.pi / 2), (x0, y0, math.pi))
    pts = []
    for cx, cy, start in corners:
        for i in range(n + 1):
            t = start + (math.pi / 2) * i / n
            pts.append((cx + r * math.cos(t), cy + r * math.sin(t)))
    return pts
