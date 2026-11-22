import random
import unittest

from helpers import make_state, mv, play, random_states

from teeko.ai.base import SearchCancelled
from teeko.ai.evaluation import MATE_THRESHOLD, WIN_SCORE, evaluate
from teeko.ai.minimax import MinimaxAgent
from teeko.engine.rules import apply_move, has_winning_move, legal_moves, new_game, winning_moves
from teeko.engine.state import FLY, PLACE, SWAP


def reference_negamax(s, depth, ply, visited, rep):
    """Plain negamax: no pruning, no TT, no ordering; same conventions as the agent."""
    if s.result is not None:
        if s.result.winner is None:
            return 0
        return WIN_SCORE - ply if s.result.winner == s.turn else ply - WIN_SCORE
    if has_winning_move(s):
        return WIN_SCORE - ply - 1
    if depth <= 0:
        return evaluate(s)
    best = -10 ** 9
    for m in legal_moves(s):
        child = apply_move(s, m)
        penalty = rep if child.result is None and child.position_key() in visited else 0
        best = max(best, -reference_negamax(child, depth - 1, ply + 1, visited, rep) - penalty)
    return best


def mirror_cell(c):
    r, col = divmod(c, 5)
    return r * 5 + (4 - col)


def mirror_move(m):
    kind, f, t = m
    return (kind, -1 if f < 0 else mirror_cell(f), mirror_cell(t))


class MinimaxTests(unittest.TestCase):
    def test_always_returns_legal_moves(self):
        for i, s in enumerate(random_states(40, seed=21)):
            d = MinimaxAgent(depth=2, seed=i).choose(s)
            self.assertIn(d.move, legal_moves(s))

    def test_takes_immediate_win(self):
        s = make_state([". . . . .",
                        "R R R . .",
                        ". . . R .",
                        "B . B . .",
                        "B . . . B"])
        d = MinimaxAgent(depth=3).choose(s)
        self.assertEqual(d.move, mv("D3-D2"))
        self.assertGreater(d.stats["score"], MATE_THRESHOLD)

    def test_blocks_single_threat(self):
        # Blue threatens A3 -> A2 completing A2-D2... and Red must occupy A2.
        s = make_state(["R . . . .",
                        ". B B B .",
                        "B . . . .",
                        ". . . . R",
                        ". . . R R"])
        for depth in (1, 2, 4):
            d = MinimaxAgent(depth=depth).choose(s)
            self.assertEqual(d.move, mv("A1-A2"), f"depth {depth}")

    def test_finds_forced_three_ply_win(self):
        s = play(new_game(), "place B1", "place A5", "place C1", "place E5")
        d = MinimaxAgent(depth=3).choose(s)
        self.assertEqual(d.move, mv("place D1"))       # open three: A1 and E1 both win
        self.assertGreater(d.stats["score"], MATE_THRESHOLD)

    def test_uses_fly_when_it_is_the_only_win(self):
        s = make_state(["R R R . .",
                        ". . . . .",
                        ". B . B .",
                        ". . B . B",
                        ". . . . R"], unlocked=(True, False))
        self.assertEqual(winning_moves(s), [mv("fly E5 D1")])
        d = MinimaxAgent(depth=2).choose(s)
        self.assertEqual(d.move[0], FLY)

    def test_uses_swap_when_it_is_the_only_win(self):
        s = make_state(["R R R B .",
                        ". . . . .",
                        ". B . B .",
                        ". . B . .",
                        ". . . . R"], unlocked=(True, False))
        d = MinimaxAgent(depth=2).choose(s)
        self.assertEqual(d.move, (SWAP, 24, 3))

    def test_alpha_beta_equals_plain_minimax_with_repetition_penalties(self):
        rng = random.Random(4)
        checked = 0
        for s in random_states(60, seed=8, unlock_prob=0.3, min_ply=6):
            moves = legal_moves(s)
            if len(moves) > 40 or len(moves) < 2 or winning_moves(s):
                continue
            # Mark some children and grandchildren as already visited in the real game.
            visited = set()
            for m in moves:
                child = apply_move(s, m)
                if rng.random() < 0.35:
                    visited.add(child.position_key())
                if child.result is None and rng.random() < 0.3:
                    for m2 in legal_moves(child)[:6]:
                        visited.add(apply_move(child, m2).position_key())
            visited = frozenset(visited)
            depth = 2 if len(moves) > 20 else 3
            rep = 8
            agent = MinimaxAgent(depth=depth, rep_penalty=rep)
            d = agent.choose(s, visited)
            if d.stats["stop"] != "depth":
                continue
            expected = max(-reference_negamax(c, depth - 1, 1, visited, rep)
                           - (rep if c.result is None and c.position_key() in visited else 0)
                           for c in (apply_move(s, m) for m in moves))
            self.assertEqual(d.stats["score"], expected, repr(s))
            checked += 1
            if checked >= 12:
                break
        self.assertGreaterEqual(checked, 8)

    def test_prefers_non_repeating_move_over_equal_repeating_one(self):
        # Mirror-symmetric position: a move and its mirror image have equal value.
        s = make_state(["R . . . R",
                        ". . B . .",
                        ". R . R .",
                        ". . B . .",
                        "B . . . B"])
        first = MinimaxAgent(depth=2).choose(s)
        twin = mirror_move(first.move)
        self.assertNotEqual(first.move, twin, "test needs a move off the mirror axis")
        visited = frozenset({apply_move(s, first.move).position_key()})
        second = MinimaxAgent(depth=2).choose(s, visited)
        self.assertNotEqual(second.move, first.move)
        self.assertNotIn(apply_move(s, second.move).position_key(), visited)
        self.assertEqual(second.stats["score"], first.stats["score"])

    def test_repetition_penalty_sign(self):
        """A repeated position lowers that action's score by exactly REP, for its chooser."""
        s = make_state(["R . . . R",
                        ". . B . .",
                        ". R . R .",
                        ". . B . .",
                        "B . . . B"])
        for depth in (1, 2):
            base = MinimaxAgent(depth=depth, rep_penalty=50).evaluate_moves(s)
            for m in list(base)[:6]:
                visited = frozenset({apply_move(s, m).position_key()})
                penalised = MinimaxAgent(depth=depth, rep_penalty=50).evaluate_moves(s, visited)
                self.assertEqual(penalised[m], base[m] - 50)
                for other in base:
                    if other != m:
                        self.assertEqual(penalised[other], base[other])

    def test_tiny_time_budget_still_returns_legal_move(self):
        s = make_state(["R . . . R",
                        ". . B . .",
                        ". B . B .",
                        ". . B . .",
                        "R . . . R"], unlocked=(True, True))
        d = MinimaxAgent(depth=8, time_limit=0.001).choose(s)
        self.assertIn(d.move, legal_moves(s))
        self.assertGreaterEqual(d.stats["depth"], 1)

    def test_time_cap_respected(self):
        s = make_state(["R . . . R",
                        ". . B . .",
                        ". B . B .",
                        ". . B . .",
                        "R . . . R"], unlocked=(True, True))
        d = MinimaxAgent(depth=12, time_limit=0.5).choose(s)
        self.assertLess(d.stats["time"], 1.0)
        self.assertEqual(d.stats["stop"], "time")

    def test_cancellation(self):
        with self.assertRaises(SearchCancelled):
            MinimaxAgent(depth=8).choose(new_game(), should_stop=lambda: True)

    def test_placement_moves_from_opening(self):
        d = MinimaxAgent(depth=2).choose(new_game())
        self.assertEqual(d.move[0], PLACE)


if __name__ == "__main__":
    unittest.main()
