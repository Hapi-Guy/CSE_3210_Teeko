import random
import unittest

from helpers import check_invariants, make_state, mv, play, random_states

from teeko.ai.base import SearchCancelled
from teeko.ai.mcts import MCTSAgent, rollout_policy_move
from teeko.engine.board import PATTERNS
from teeko.engine.rules import (apply_move, has_winning_move, legal_moves, limit_result,
                                new_game, winning_moves)

BLOCK_POSITION = ["R . . . .",
                  ". B B B .",
                  "B . . . .",
                  ". . . . R",
                  ". . . R R"]


def is_safe(s, m):
    child = apply_move(s, m)
    if child.result is not None:
        return child.result.winner in (None, s.turn)
    return not has_winning_move(child)


class MCTSTests(unittest.TestCase):
    def test_root_visits_equal_completed_simulations(self):
        s = make_state(["R . . . R",
                        ". . B . .",
                        ". B . B .",
                        ". . B . .",
                        "R . . . R"])
        d = MCTSAgent(simulations=300, seed=1).choose(s)
        self.assertEqual(d.stats["stop"], "iterations")
        self.assertEqual(d.stats["simulations"], 300)
        self.assertEqual(d.stats["root_visits"], 300)
        self.assertEqual(sum(v for _, v, _ in d.stats["top"]) <= 300, True)

    def test_time_budget_stops_early_and_counts_completed_simulations(self):
        d = MCTSAgent(simulations=10 ** 6, time_limit=0.2, seed=2).choose(new_game())
        self.assertEqual(d.stats["stop"], "time")
        self.assertLess(d.stats["simulations"], 10 ** 6)
        self.assertEqual(d.stats["root_visits"], d.stats["simulations"])
        self.assertEqual(d.stats["max_simulations"], 10 ** 6)
        self.assertLess(d.stats["time"], 0.6)

    def test_tiny_time_budget_still_returns_legal_move(self):
        s = make_state(["R . . . R",
                        ". . B . .",
                        ". B . B .",
                        ". . B . .",
                        "R . . . R"], unlocked=(True, True))
        d = MCTSAgent(simulations=5000, time_limit=1e-9, seed=3).choose(s)
        self.assertIn(d.move, legal_moves(s))

    def test_immediate_win_shortcut(self):
        s = make_state([". . . . .",
                        "R R R . .",
                        ". . . R .",
                        "B . B . .",
                        "B . . . B"])
        d = MCTSAgent(simulations=500, seed=4).choose(s)
        self.assertEqual(d.move, mv("D3-D2"))
        self.assertEqual(d.stats["stop"], "shortcut")
        self.assertEqual(d.stats["simulations"], 0)

    def test_blocks_single_threat(self):
        s = make_state(BLOCK_POSITION)
        for seed in range(3):
            d = MCTSAgent(simulations=800, seed=seed).choose(s)
            self.assertEqual(d.move, mv("A1-A2"))

    def test_avoids_repeated_position(self):
        s = make_state(["R . . . R",
                        ". . B . .",
                        ". R . R .",
                        ". . B . .",
                        "B . . . B"])
        first = MCTSAgent(simulations=400, seed=5).choose(s)
        visited = frozenset({apply_move(s, first.move).position_key()})
        second = MCTSAgent(simulations=400, rep_penalty=1.0, seed=5).choose(s, visited)
        self.assertNotEqual(second.move, first.move)
        self.assertNotIn(apply_move(s, second.move).position_key(), visited)

    def test_cancellation(self):
        with self.assertRaises(SearchCancelled):
            MCTSAgent(simulations=1000).choose(new_game(), should_stop=lambda: True)

    def test_solver_blocks_placement_threat(self):
        # Blue (A4 B4 B3) threatens A3 for a 2x2 square; plain UCT averages missed this.
        s = play(new_game(), "place E1", "place A4", "place D3", "place B4", "place E3", "place B3")
        for seed in range(3):
            d = MCTSAgent(simulations=400, seed=seed).choose(s)
            self.assertEqual(d.move, mv("place A3"))

    def test_solver_proves_forced_win(self):
        # Placing D1 makes an open three (A1 and E1 both win): a forced win in 3 plies.
        s = play(new_game(), "place B1", "place A5", "place C1", "place E5")
        d = MCTSAgent(simulations=5000, seed=1).choose(s)
        self.assertEqual(d.move, mv("place D1"))
        self.assertEqual(d.stats["proven"], "win")
        self.assertEqual(d.stats["stop"], "proven")
        self.assertEqual(d.stats["root_visits"], d.stats["simulations"])

    def test_solver_recognises_lost_position_and_still_moves(self):
        # Blue has an open three B2-C2-D2 with Fly available: A2 and E2 both win next turn.
        s = make_state(["R . . . .",
                        ". B B B .",
                        ". . . . .",
                        ". . . . R",
                        "B . . R R"], unlocked=(False, True))
        d = MCTSAgent(simulations=3000, seed=2).choose(s)
        self.assertIn(d.move, legal_moves(s))
        self.assertEqual(d.stats["proven"], "loss")


class RolloutPolicyTests(unittest.TestCase):
    def test_policy_prefers_wins_and_never_picks_unsafe_when_safe_exists(self):
        rng = random.Random(9)
        checked = 0
        for s in random_states(500, seed=12, unlock_prob=0.6):
            m = rollout_policy_move(s, rng)
            legal = legal_moves(s)
            self.assertIn(m, legal)
            wins = winning_moves(s)
            if wins:
                self.assertIn(m, wins)
                continue
            if any(is_safe(s, x) for x in legal):
                self.assertTrue(is_safe(s, m), f"{m} unsafe in {s!r}")
                checked += 1
        self.assertGreater(checked, 300)

    def test_policy_blocks_threats_created_by_specials(self):
        # Blue has Fly: any open three (B2 C2 D2 with A2/E2 empty) is a threat. Red must block
        # a cell that removes every immediate Blue win, which the policy finds via the engine.
        s = make_state(["R . . . .",
                        ". B B B .",
                        ". . . . .",
                        ". . . . R",
                        "B . . R R"], unlocked=(False, True))
        rng = random.Random(1)
        for _ in range(20):
            m = rollout_policy_move(s, rng)
            if any(is_safe(s, x) for x in legal_moves(s)):
                self.assertTrue(is_safe(s, m))

    def test_rollouts_respect_all_rules(self):
        rng = random.Random(10)
        for s in random_states(1000, seed=14, unlock_prob=0.3, limit=12):
            used_before = (s.swap_used, s.fly_used)
            while s.result is None:
                m = rollout_policy_move(s, rng)
                self.assertIn(m, legal_moves(s))
                nxt = apply_move(s, m)
                for p in (0, 1):   # one-use abilities can only go from unused to used
                    self.assertTrue(nxt.swap_used[p] or not s.swap_used[p])
                    self.assertTrue(nxt.fly_used[p] or not s.fly_used[p])
                s = nxt
                check_invariants(self, s)
            self.assertIsNotNone(used_before)
            r = s.result
            if r.reason in ("line", "square"):
                mask = PATTERNS[r.pattern].mask
                self.assertEqual(s.boards[r.winner] & mask, mask)
            else:
                self.assertEqual(s.move_counts, (s.limit, s.limit))
                self.assertEqual(r, limit_result(s.boards))


if __name__ == "__main__":
    unittest.main()
