"""Human-readable text for players, moves and results."""

from .board import PATTERNS, cell_name
from .state import FLY, PLACE, STEP, SWAP, GameResult

PLAYER_NAMES = ("Red", "Blue")
PLAYER_LABELS = ("P1 · Red", "P2 · Blue")

ARROW = "→"
SWAP_ARROW = "↔"


def move_text(move, ascii_only: bool = False) -> str:
    """'C3 → D3', 'Place C3', 'Swap B2 ↔ D4', 'Fly A1 → E5'."""
    kind, frm, to = move
    arrow = "->" if ascii_only else ARROW
    if kind == PLACE:
        return f"Place {cell_name(to)}"
    if kind == STEP:
        return f"{cell_name(frm)} {arrow} {cell_name(to)}"
    if kind == SWAP:
        return f"Swap {cell_name(frm)} {'<->' if ascii_only else SWAP_ARROW} {cell_name(to)}"
    if kind == FLY:
        return f"Fly {cell_name(frm)} {arrow} {cell_name(to)}"
    return str(move)


def pattern_text(pattern_index: int) -> str:
    p = PATTERNS[pattern_index]
    names = " · ".join(cell_name(c) for c in p.cells)
    kind = {"row": "four in a row", "column": "four in a column", "diagonal": "four on a diagonal",
            "anti-diagonal": "four on a diagonal", "square": "a 2×2 square"}[p.kind]
    return f"{kind} ({names})"


def result_headline(result: GameResult) -> str:
    if result.winner is None:
        return "Draw"
    return f"{PLAYER_NAMES[result.winner]} wins!"


def result_reason(result: GameResult, limit: int) -> str:
    if result.reason in ("line", "square"):
        return f"{PLAYER_NAMES[result.winner]} made {pattern_text(result.pattern)}."
    s0, s1 = result.scores
    c0, c1 = result.center
    if result.reason == "limit_score":
        return (f"Movement limit reached ({limit} turns each). "
                f"Board score {s0} – {s1}.")
    if result.reason == "limit_center":
        return (f"Movement limit reached. Scores tied {s0} – {s1}; "
                f"{PLAYER_NAMES[result.winner]} has more central pieces ({c0} – {c1}).")
    return f"Movement limit reached. Scores tied {s0} – {s1} and central pieces tied {c0} – {c1}."
