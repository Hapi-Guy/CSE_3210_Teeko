"""Shared helpers for the test-suite: build positions from text and play moves."""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from teeko.engine.board import BIT, parse_cell  # noqa: E402
from teeko.engine.rules import apply_move, legal_moves, new_game  # noqa: E402
from teeko.engine.state import FLY, PLACE, STEP, SWAP, GameState  # noqa: E402


def make_state(rows, turn=0, move_counts=(0, 0), limit=24, unlocked=(False, False),
               swap_used=(False, False), fly_used=(False, False), last_step=(None, None),
               streak=(0, 0)):
    """Build a position from 5 strings such as ``"R . . B ."`` (R = P1, B = P2)."""
    red = blue = 0
    for r, row in enumerate(rows):
        cells = row.split()
        assert len(cells) == 5, row
        for c, ch in enumerate(cells):
            if ch == "R":
                red |= BIT[r * 5 + c]
            elif ch == "B":
                blue |= BIT[r * 5 + c]
    ply = red.bit_count() + blue.bit_count() + sum(move_counts)
    return GameState((red, blue), turn, tuple(move_counts), tuple(last_step), tuple(streak),
                     tuple(unlocked), tuple(swap_used), tuple(fly_used), limit, ply, None)


def mv(text):
    """'place C3' | 'C3-D3' | 'swap B2 D4' | 'fly A1 E5' -> move tuple."""
    parts = text.replace("-", " ").split()
    head = parts[0].lower()
    if head == "place":
        return (PLACE, -1, parse_cell(parts[1]))
    if head == "swap":
        return (SWAP, parse_cell(parts[1]), parse_cell(parts[2]))
    if head == "fly":
        return (FLY, parse_cell(parts[1]), parse_cell(parts[2]))
    return (STEP, parse_cell(parts[0]), parse_cell(parts[1]))


def play(state, *moves, check_legal=True):
    for text in moves:
        move = mv(text) if isinstance(text, str) else text
        if check_legal:
            assert move in legal_moves(state), f"illegal move {text!r} in {state!r}"
        state = apply_move(state, move)
    return state


def random_states(count, seed=1, unlock_prob=0.5, limit=24, min_ply=0):
    """Yield varied non-terminal positions reached by random legal play.

    With probability ``unlock_prob`` both players' specials are force-unlocked
    (as if the opponent had shuttled) so positions with Swap/Fly are covered.
    """
    rng = random.Random(seed)
    produced = 0
    while produced < count:
        s = new_game(limit)
        target = rng.randrange(min_ply, 8 + 2 * limit)
        while s.result is None and s.ply < target:
            s = apply_move(s, rng.choice(legal_moves(s)))
        if s.result is not None:
            continue
        if not s.in_placement and rng.random() < unlock_prob:
            swap_used = (rng.random() < 0.3, rng.random() < 0.3)
            fly_used = (rng.random() < 0.3, rng.random() < 0.3)
            s = GameState(s.boards, s.turn, s.move_counts, s.last_step, s.streak, (True, True),
                          swap_used, fly_used, s.limit, s.ply, None)
        produced += 1
        yield s


def check_invariants(test, s):
    """Assertions that must hold for every reachable state."""
    b0, b1 = s.boards
    test.assertEqual(b0 & b1, 0, "pieces overlap")
    test.assertLessEqual(b0.bit_count(), 4)
    test.assertLessEqual(b1.bit_count(), 4)
    test.assertTrue(0 <= b0 < (1 << 25) and 0 <= b1 < (1 << 25))
    test.assertLessEqual(s.move_counts[0], s.limit)
    test.assertLessEqual(s.move_counts[1], s.limit)
    if s.in_placement:
        test.assertEqual(s.move_counts, (0, 0))
