import random
import unittest

from helpers import make_state, play

from teeko.engine.board import BIT, CENTER_MASK, PATTERNS, mask_of, parse_cell
from teeko.engine.rules import (apply_move, center_counts, legal_moves, limit_result,
                                limit_scores, new_game)


def cells(*names):
    return mask_of(*(parse_cell(n) for n in names))


def reference_score(own, opp):
    """Independent re-implementation using pattern cell lists."""
    points = {1: 1, 2: 3, 3: 10}
    total = 0
    for p in PATTERNS:
        if any(opp >> c & 1 for c in p.cells):
            continue
        k = sum(own >> c & 1 for c in p.cells)
        total += points.get(k, 0)
    return total


class LimitScoreTests(unittest.TestCase):
    def test_single_piece_scores_one_per_pattern(self):
        (s0, s1), _ = limit_scores((cells("A1"), 0))
        self.assertEqual((s0, s1), (4, 0))     # row, column, diagonal, square

    def test_hand_computed_example(self):
        (s0, s1), breakdown = limit_scores((cells("A1", "B1"), 0))
        self.assertEqual(s0, 12)
        self.assertEqual(breakdown[0], (6, 2, 0))
        # A blue piece on C1 removes every pattern through C1 from Red's score
        (s0, s1), _ = limit_scores((cells("A1", "B1"), cells("C1")))
        self.assertEqual((s0, s1), (7, 2))

    def test_three_in_pattern_scores_ten(self):
        (s0, _), breakdown = limit_scores((cells("A1", "B1", "C1"), cells("E5")))
        self.assertEqual(breakdown[0][2], 1)
        self.assertEqual(s0, reference_score(cells("A1", "B1", "C1"), cells("E5")))

    def test_matches_reference_on_random_boards(self):
        rng = random.Random(11)
        for _ in range(500):
            chosen = rng.sample(range(25), 8)
            red = mask_of(*chosen[:4])
            blue = mask_of(*chosen[4:])
            (s0, s1), _ = limit_scores((red, blue))
            self.assertEqual(s0, reference_score(red, blue))
            self.assertEqual(s1, reference_score(blue, red))

    def test_center_tiebreak_and_draw(self):
        rng = random.Random(5)
        found_center = found_draw = False
        for _ in range(20000):
            chosen = rng.sample(range(25), 8)
            boards = (mask_of(*chosen[:4]), mask_of(*chosen[4:]))
            (s0, s1), _ = limit_scores(boards)
            if s0 != s1:
                continue
            c0, c1 = center_counts(boards)
            res = limit_result(boards)
            if c0 != c1:
                self.assertEqual(res.reason, "limit_center")
                self.assertEqual(res.winner, 0 if c0 > c1 else 1)
                found_center = True
            else:
                self.assertEqual(res.reason, "draw")
                self.assertIsNone(res.winner)
                found_draw = True
            if found_center and found_draw:
                break
        self.assertTrue(found_center and found_draw)

    def test_mirror_position_is_a_draw(self):
        red = cells("A1", "B3", "D2", "B5")
        mirror = 0
        for c in range(25):
            if red >> c & 1:
                r, col = divmod(c, 5)
                mirror |= BIT[r * 5 + (4 - col)]
        res = limit_result((red, mirror))
        self.assertEqual(res.scores[0], res.scores[1])
        self.assertEqual(res.center[0], res.center[1])
        self.assertEqual(res.reason, "draw")
        self.assertEqual(CENTER_MASK.bit_count(), 9)

    def test_higher_score_wins(self):
        res = limit_result((cells("B2", "C2", "B3", "E5"), cells("A1", "E1", "A5", "C4")))
        self.assertEqual(res.reason, "limit_score")
        self.assertEqual(res.winner, 0 if res.scores[0] > res.scores[1] else 1)


class MovementLimitTests(unittest.TestCase):
    ROWS = ["R . . . R",
            ". . B . .",
            ". B . B .",
            ". . B . .",
            "R . . . R"]

    def test_p1_at_limit_p2_one_short_continues(self):
        s = make_state(self.ROWS, move_counts=(23, 23))
        s = play(s, "A1-B1")
        self.assertEqual(s.move_counts, (24, 23))
        self.assertIsNone(s.result, "P2 still has a movement turn left")
        self.assertEqual(s.turn, 1)
        s = play(s, "C2-C1")
        self.assertEqual(s.move_counts, (24, 24))
        self.assertIsNotNone(s.result)
        self.assertTrue(s.result.by_limit)

    def test_special_moves_count_toward_limit(self):
        s = make_state(self.ROWS, move_counts=(24, 23), turn=1, unlocked=(False, True))
        s = play(s, "fly C4 E3")
        self.assertIsNotNone(s.result)
        self.assertEqual(s.move_counts, (24, 24))

    def test_configurable_limit_and_full_game_length(self):
        rng = random.Random(2)
        for limit in (1, 3, 8):
            for _ in range(20):
                s = new_game(limit)
                while s.result is None:
                    s = apply_move(s, rng.choice(legal_moves(s)))
                if s.result.by_limit:
                    self.assertEqual(s.move_counts, (limit, limit))
                    self.assertEqual(s.ply, 8 + 2 * limit)
                else:
                    self.assertLessEqual(s.ply, 8 + 2 * limit)


if __name__ == "__main__":
    unittest.main()
