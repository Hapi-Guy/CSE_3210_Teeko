import itertools
import random
import unittest

from helpers import check_invariants, make_state, mv, play, random_states

from teeko.engine.board import (CENTER_MASK, NEIGHBORS, PATTERNS, PATTERNS_BY_CELL, cells_of,
                                mask_of, parse_cell)
from teeko.engine.rules import (apply_move, has_winning_move, is_legal, legal_moves, new_game,
                                winning_moves)
from teeko.engine.state import PLACE, STEP


class BoardGeometryTests(unittest.TestCase):
    def test_pattern_count_is_44(self):
        kinds = [p.kind for p in PATTERNS]
        self.assertEqual(len(PATTERNS), 44)
        self.assertEqual(kinds.count("row"), 10)
        self.assertEqual(kinds.count("column"), 10)
        self.assertEqual(kinds.count("diagonal") + kinds.count("anti-diagonal"), 8)
        self.assertEqual(kinds.count("square"), 16)
        self.assertEqual(len({p.mask for p in PATTERNS}), 44)
        for p in PATTERNS:
            self.assertEqual(p.mask.bit_count(), 4)

    def test_neighbour_counts(self):
        self.assertEqual(NEIGHBORS[parse_cell("A1")].bit_count(), 3)   # corner
        self.assertEqual(NEIGHBORS[parse_cell("C1")].bit_count(), 5)   # edge
        self.assertEqual(NEIGHBORS[parse_cell("C3")].bit_count(), 8)   # centre
        # diagonal neighbours are included
        self.assertTrue(NEIGHBORS[parse_cell("C3")] & mask_of(parse_cell("B2"), parse_cell("D4")))

    def test_center_region(self):
        self.assertEqual(CENTER_MASK.bit_count(), 9)
        self.assertEqual({c for c in cells_of(CENTER_MASK)},
                         {parse_cell(n) for n in "B2 C2 D2 B3 C3 D3 B4 C4 D4".split()})

    def test_patterns_by_cell(self):
        for cell in range(25):
            for idx in PATTERNS_BY_CELL[cell]:
                self.assertIn(cell, PATTERNS[idx].cells)


class PlacementTests(unittest.TestCase):
    def test_new_game(self):
        s = new_game()
        self.assertEqual(s.turn, 0)
        self.assertEqual(s.phase, "placement")
        self.assertEqual(len(legal_moves(s)), 25)
        self.assertTrue(all(m[0] == PLACE for m in legal_moves(s)))

    def test_alternation_and_switch_to_movement(self):
        s = new_game()
        for i, name in enumerate("A1 E5 C1 A5 E1 C5 B3 D4".split()):
            self.assertEqual(s.turn, i % 2)
            self.assertEqual(s.phase, "placement")
            s = play(s, f"place {name}")
        self.assertEqual(s.phase, "movement")
        self.assertEqual(s.turn, 0, "P1 moves first in the movement phase")
        self.assertEqual(s.move_counts, (0, 0), "placements do not count as movement turns")
        self.assertTrue(all(m[0] == STEP for m in legal_moves(s)))

    def test_cannot_place_on_occupied_cell(self):
        s = play(new_game(), "place C3")
        self.assertNotIn(mv("place C3"), legal_moves(s))
        self.assertFalse(is_legal(s, mv("place C3")))

    def test_win_during_placement_line(self):
        s = play(new_game(), "place A1", "place A5", "place B1", "place B5", "place C1", "place E5")
        s = play(s, "place D1")
        self.assertEqual(s.result.winner, 0)
        self.assertEqual(s.result.reason, "line")

    def test_win_during_placement_square(self):
        s = play(new_game(), "place A1", "place C3", "place B1", "place D3", "place A2", "place E3",
                 "place E5", "place B2")
        self.assertIsNone(s.result)
        s = play(new_game(), "place A5", "place B2", "place E1", "place C2", "place E5", "place B3",
                 "place A1", "place C3")
        self.assertEqual(s.result.winner, 1)
        self.assertEqual(s.result.reason, "square")


class MovementTests(unittest.TestCase):
    def setUp(self):
        self.s = make_state(["R . . . R",
                             ". . B . .",
                             ". B . B .",
                             ". . B . .",
                             "R . . . R"])

    def test_steps_are_adjacent_and_empty(self):
        moves = legal_moves(self.s)
        self.assertTrue(all(m[0] == STEP for m in moves))
        for _, f, t in moves:
            self.assertTrue(NEIGHBORS[f] >> t & 1)
            self.assertFalse((self.s.boards[0] | self.s.boards[1]) >> t & 1)
        # corner A1 has 3 neighbours, all empty
        self.assertEqual(sum(1 for m in moves if m[1] == parse_cell("A1")), 3)

    def test_cannot_move_onto_occupied_or_far(self):
        self.assertFalse(is_legal(self.s, mv("A1-C1")))
        s = play(self.s, "A1-B2")
        self.assertFalse(is_legal(s, mv("B3-B2")))

    def test_move_does_not_mutate_previous_state(self):
        before = (self.s.boards, self.s.turn, self.s.move_counts)
        play(self.s, "A1-B1")
        self.assertEqual((self.s.boards, self.s.turn, self.s.move_counts), before)

    def test_movement_counts(self):
        s = play(self.s, "A1-B1")
        self.assertEqual(s.move_counts, (1, 0))
        s = play(s, "C2-C1")
        self.assertEqual(s.move_counts, (1, 1))


class WinDetectionTests(unittest.TestCase):
    def check_win(self, rows, move, winner, reason):
        s = play(make_state(rows), move)
        self.assertIsNotNone(s.result, rows)
        self.assertEqual(s.result.winner, winner)
        self.assertEqual(s.result.reason, reason)
        self.assertEqual(legal_moves(s), [])
        self.assertEqual(winning_moves(s), [])
        return s

    def test_row(self):
        self.check_win([". . . . .",
                        "R R R . .",
                        ". . . R .",
                        "B . B . .",
                        "B . . . B"], "D3-D2", 0, "line")

    def test_column(self):
        self.check_win(["R . . . .",
                        "R . . . B",
                        "R . . . B",
                        ". R . . .",
                        "B . . . B"], "B4-A4", 0, "line")

    def test_diagonal(self):
        self.check_win(["R . . . .",
                        ". R . . B",
                        "B . R . .",
                        ". . . . B",
                        ". . . R B"], "D5-D4", 0, "line")

    def test_anti_diagonal(self):
        self.check_win(["B . . . R",
                        ". . . R B",
                        ". . R . .",
                        ". . . . B",
                        "R . . . B"], "A5-B4", 0, "line")

    def test_square(self):
        self.check_win([". . . . .",
                        ". R R . .",
                        ". R . . .",
                        ". . . R .",
                        "B B . B B"], "D4-C3", 0, "square")

    def test_no_false_wins(self):
        # big square corners, a broken line and an L-shape are not wins
        for rows, move in [
            (["R . R . .", ". . . . .", "R . . . B", "B . . R .", ". . B . B"], "D4-C3"),
            (["R R R . .", ". . . . R", ". . . . .", "B B . . .", ". . B B ."], "E2-E1"),
            ([". R . . .", ". R . . .", ". R . . .", ". . . R .", "B B . B B"], "D4-C4"),
        ]:
            s = make_state(rows)
            s = play(s, move)
            self.assertIsNone(s.result, rows)


class WinPrecedenceTests(unittest.TestCase):
    """Mover's patterns are checked first, then the opponent's, for every action type."""

    def test_swap_completing_both_patterns_mover_wins(self):
        # Red: A1 B1 C1 + E5; Blue: D1 + B5 C5 D5. Red swaps E5<->D1:
        # Red completes A1-D1 and Blue completes B5-E5. The mover (Red) wins.
        s = make_state(["R R R B .",
                        ". . . . .",
                        ". . . . .",
                        ". . . . .",
                        ". B B B R"], unlocked=(True, False))
        s = play(s, "swap E5 D1")
        self.assertEqual(s.result.winner, 0)

    def test_swap_completing_only_opponent_pattern_opponent_wins(self):
        # Blue holds B5 C5 D5; Red's E5 is swapped with Blue's C3, moving Blue onto E5.
        s = make_state(["R . . . R",
                        ". . . . .",
                        ". . B R .",
                        ". . . . .",
                        ". B B B R"], unlocked=(True, False))
        s = play(s, "swap E5 C3")
        self.assertEqual(s.result.winner, 1)
        self.assertEqual(s.result.reason, "line")

    def test_step_and_fly_wins_belong_to_mover(self):
        rows = ["R R R . .",
                ". . . . .",
                ". . . . R",
                "B B B . .",
                ". . . . B"]
        s = play(make_state(rows, unlocked=(True, False)), "fly E3 D1")
        self.assertEqual(s.result.winner, 0)
        s = play(make_state(rows, turn=1), "E5-D4")
        self.assertEqual(s.result.winner, 1)

    def test_win_takes_precedence_over_limit(self):
        s = make_state(["R R R . .",
                        ". . . . R",
                        ". . . . .",
                        "B B . . .",
                        ". . B B ."], turn=1, move_counts=(24, 23))
        s = play(s, "D5-C4")
        self.assertTrue(s.result.by_limit, "a non-winning final turn ends with limit scoring")
        s = make_state(["R R R . .",
                        ". . . . R",
                        ". . . . .",
                        "B B B . .",
                        ". . . B ."], turn=1, move_counts=(24, 23))
        s = play(s, "D5-D4")
        self.assertEqual(s.result.reason, "line")
        self.assertEqual(s.result.winner, 1)


class TacticalHelperTests(unittest.TestCase):
    def test_winning_moves_exact_on_random_positions(self):
        for s in random_states(400, seed=7):
            legal = legal_moves(s)
            brute = {m for m in legal if apply_move(s, m).result is not None
                     and apply_move(s, m).result.winner == s.turn
                     and apply_move(s, m).result.reason in ("line", "square")}
            found = winning_moves(s)
            self.assertEqual(len(found), len(set(found)))
            self.assertTrue(set(found) <= set(legal), "winning_moves must be legal")
            self.assertEqual(set(found), brute, repr(s))
            self.assertEqual(has_winning_move(s), bool(brute), repr(s))

    def test_random_games_keep_invariants(self):
        rng = random.Random(3)
        for _ in range(150):
            s = new_game(limit=rng.choice([4, 10, 24]))
            while s.result is None:
                check_invariants(self, s)
                moves = legal_moves(s)
                self.assertTrue(moves, "a non-terminal state always has a legal move")
                s = apply_move(s, rng.choice(moves))
            check_invariants(self, s)

    def test_state_key_distinguishes_specials_and_counts(self):
        rows = ["R . . . R", ". . B . .", ". B . B .", ". . B . .", "R . . . R"]
        base = make_state(rows)
        variants = [make_state(rows, unlocked=(True, False)),
                    make_state(rows, unlocked=(True, False), swap_used=(True, False)),
                    make_state(rows, unlocked=(True, False), fly_used=(True, False)),
                    make_state(rows, move_counts=(3, 3)),
                    make_state(rows, limit=10),
                    make_state(rows, streak=(2, 0), last_step=(mv("A2-A1"), None))]
        keys = {base.state_key()} | {v.state_key() for v in variants}
        self.assertEqual(len(keys), len(variants) + 1)
        self.assertEqual(len({base.position_key()} | {v.position_key() for v in variants}), 1)


class NeverBlockedTests(unittest.TestCase):
    def test_four_pieces_always_have_five_free_neighbours(self):
        """Exhaustive: any 4 cells have >= 5 neighbouring cells, so 4 opponents can't block them."""
        for cells in itertools.combinations(range(25), 4):
            own = mask_of(*cells)
            around = 0
            for c in cells:
                around |= NEIGHBORS[c]
            self.assertGreaterEqual((around & ~own).bit_count(), 5, cells)


if __name__ == "__main__":
    unittest.main()
