"""Teeko rules engine (pure Python, no pygame)."""

from .board import CELL_NAMES, PATTERNS, cell_name, parse_cell
from .rules import (apply_move, has_winning_move, is_legal, legal_moves, limit_result,
                    limit_scores, new_game, special_status, winning_moves)
from .state import (DEFAULT_LIMIT, FLY, P1, P2, PLACE, STEP, SWAP, GameResult, GameState)

__all__ = [
    "CELL_NAMES", "PATTERNS", "cell_name", "parse_cell",
    "apply_move", "has_winning_move", "is_legal", "legal_moves", "limit_result",
    "limit_scores", "new_game", "special_status", "winning_moves",
    "DEFAULT_LIMIT", "FLY", "P1", "P2", "PLACE", "STEP", "SWAP", "GameResult", "GameState",
]
