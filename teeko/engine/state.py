"""Immutable game state.

``GameState`` objects are never modified after construction: every action
produces a new state (see ``rules.apply_move``). That makes any state a safe
snapshot to hand to a background search thread.

Moves are plain tuples ``(kind, frm, to)``:
    (PLACE, -1, to)      drop a piece during the placement phase
    (STEP,  frm, to)     move to an adjacent empty point (diagonals allowed)
    (SWAP,  own, opp)    exchange one own piece with one opponent piece
    (FLY,   frm, to)     move an own piece to any empty point
"""

from typing import NamedTuple, Optional

PLACE, STEP, SWAP, FLY = 0, 1, 2, 3
MOVE_KINDS = ("place", "step", "swap", "fly")

P1, P2 = 0, 1                 # P1 = Red (moves first), P2 = Blue
PIECES_PER_PLAYER = 4
DEFAULT_LIMIT = 24            # movement turns per player (spec; the PDF said 25)
SHUTTLE_TRIGGER = 4           # A->B, B->A, A->B, B->A unlocks the opponent's specials


class GameResult(NamedTuple):
    winner: Optional[int]           # 0, 1, or None for a draw
    reason: str                     # "line", "square", "limit_score", "limit_center", "draw"
    pattern: Optional[int] = None   # index into board.PATTERNS for pattern wins
    scores: Optional[tuple] = None  # (P1, P2) limit scores, for limit endings
    center: Optional[tuple] = None  # (P1, P2) pieces in the central 3x3, for limit endings
    breakdown: Optional[tuple] = None  # per player: (#patterns with 1, 2, 3 own pieces)

    @property
    def by_limit(self) -> bool:
        return self.reason in ("limit_score", "limit_center", "draw")


class GameState:
    __slots__ = ("boards", "turn", "move_counts", "last_step", "streak", "unlocked",
                 "swap_used", "fly_used", "limit", "ply", "result")

    def __init__(self, boards, turn, move_counts, last_step, streak, unlocked,
                 swap_used, fly_used, limit, ply, result):
        self.boards = boards            # (P1 mask, P2 mask)
        self.turn = turn                # player to move
        self.move_counts = move_counts  # movement turns used (steps + specials)
        self.last_step = last_step      # each player's previous action if it was a STEP, else None
        self.streak = streak            # length of each player's current shuttle sequence
        self.unlocked = unlocked        # specials unlocked by the opponent's shuttling
        self.swap_used = swap_used
        self.fly_used = fly_used
        self.limit = limit              # movement-turn limit per player
        self.ply = ply                  # actions played so far
        self.result = result            # GameResult or None

    # --- derived information -------------------------------------------------
    @property
    def pieces_on_board(self) -> int:
        return (self.boards[0] | self.boards[1]).bit_count()

    @property
    def in_placement(self) -> bool:
        return self.pieces_on_board < 2 * PIECES_PER_PLAYER

    @property
    def phase(self) -> str:
        if self.result is not None:
            return "over"
        return "placement" if self.in_placement else "movement"

    @property
    def is_over(self) -> bool:
        return self.result is not None

    def can_swap(self, player: int) -> bool:
        return self.unlocked[player] and not self.swap_used[player]

    def can_fly(self, player: int) -> bool:
        return self.unlocked[player] and not self.fly_used[player]

    # --- keys -----------------------------------------------------------------
    def position_key(self) -> int:
        """Board + player to move. Used to detect repeated positions."""
        return (self.boards[0] << 26) | (self.boards[1] << 1) | self.turn

    def state_key(self) -> tuple:
        """Everything that affects future legal moves or evaluation.

        The same board with different special-move availability, shuttle
        streaks or movement counts is a different state.
        """
        flags = ((self.unlocked[0] << 0) | (self.unlocked[1] << 1)
                 | (self.swap_used[0] << 2) | (self.swap_used[1] << 3)
                 | (self.fly_used[0] << 4) | (self.fly_used[1] << 5))
        l0, l1 = self.last_step
        return (self.boards[0], self.boards[1], self.turn,
                self.move_counts[0], self.move_counts[1], self.limit,
                -1 if l0 is None else l0[1] * 32 + l0[2],
                -1 if l1 is None else l1[1] * 32 + l1[2],
                min(self.streak[0], SHUTTLE_TRIGGER), min(self.streak[1], SHUTTLE_TRIGGER),
                flags)

    def __repr__(self) -> str:
        return (f"GameState(ply={self.ply}, turn={self.turn}, phase={self.phase}, "
                f"boards=({self.boards[0]:#x}, {self.boards[1]:#x}), moves={self.move_counts}, "
                f"streak={self.streak}, unlocked={self.unlocked}, result={self.result})")
