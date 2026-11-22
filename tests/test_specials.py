import unittest

from helpers import make_state, mv, play

from teeko.engine.board import parse_cell
from teeko.engine.rules import legal_moves, new_game, special_status
from teeko.engine.state import FLY, PLACE, STEP, SWAP

START = ["R . . . R",
         ". . B . .",
         ". B . B .",
         ". . B . .",
         "R . . . R"]


def kinds(state):
    return {m[0] for m in legal_moves(state)}


class ShuttleTriggerTests(unittest.TestCase):
    def test_specials_start_locked(self):
        s = make_state(START)
        self.assertEqual(special_status(s, 0), ("locked", "locked"))
        self.assertEqual(special_status(s, 1), ("locked", "locked"))
        self.assertEqual(kinds(s), {STEP})

    def test_unlocks_on_exactly_the_fourth_shuttle_move(self):
        s = make_state(START)
        s = play(s, "A1-A2", "C2-C1", "A2-A1", "B3-B2", "A1-A2", "C4-D4")
        self.assertEqual(s.streak[0], 3)
        self.assertEqual(s.unlocked, (False, False), "three shuttle moves are not enough")
        s = play(s, "A2-A1")                      # A->B->A->B->A completed
        self.assertEqual(s.streak[0], 4)
        self.assertEqual(s.unlocked, (False, True), "the opponent (Blue) unlocks")
        self.assertEqual(special_status(s, 1), ("available", "available"))
        self.assertEqual(special_status(s, 0), ("locked", "locked"))
        self.assertEqual(kinds(s), {STEP, SWAP, FLY})
        moves = legal_moves(s)
        self.assertEqual(sum(1 for m in moves if m[0] == SWAP), 16)        # 4 own x 4 opponent
        self.assertEqual(sum(1 for m in moves if m[0] == FLY), 4 * 17)     # 4 own x 17 empty

    def test_shuffler_does_not_gain_specials(self):
        s = play(make_state(START), "A1-A2", "C2-C1", "A2-A1", "B3-B2", "A1-A2", "C4-D4", "A2-A1",
                 "C1-C2")
        self.assertEqual(s.turn, 0)
        self.assertEqual(kinds(s), {STEP})

    def test_different_piece_breaks_sequence(self):
        s = play(make_state(START), "A1-A2", "C2-C1", "A2-A1", "C1-C2", "E1-E2")
        self.assertEqual(s.streak[0], 1)

    def test_different_cell_pair_breaks_sequence(self):
        s = play(make_state(START), "A1-A2", "C2-C1", "A2-A1", "C1-C2", "A1-B1")
        self.assertEqual(s.streak[0], 1)
        s = play(s, "C2-C1", "B1-A1", "C1-C2", "A1-B1", "C2-C1", "B1-A1")
        self.assertEqual(s.streak[0], 4)
        self.assertTrue(s.unlocked[1])

    def test_opponent_turns_do_not_break_and_streaks_are_separate(self):
        s = make_state(START)
        s = play(s, "A1-A2", "C2-C1", "A2-A1", "C1-C2", "A1-A2", "C2-C1", "A2-A1")
        self.assertEqual(s.streak, (4, 3))
        self.assertEqual(s.unlocked, (False, True))
        s = play(s, "C1-C2")
        self.assertEqual(s.streak, (4, 4))
        self.assertEqual(s.unlocked, (True, True))

    def test_own_special_breaks_the_shuttle(self):
        rows = [". . . . R",
                "R . B . .",      # Red has just shuttled A1 -> A2 for the third time
                ". B . B .",
                ". . B . .",
                "R . . . R"]
        state = make_state(rows, unlocked=(True, False), streak=(3, 0),
                           last_step=(mv("A1-A2"), None))
        # Without the special, the next reversal would be the 4th shuttle move.
        self.assertTrue(play(state, "A2-A1").unlocked[1])
        s = play(state, "fly E5 C5")
        self.assertEqual(s.streak[0], 0)
        self.assertIsNone(s.last_step[0])
        s = play(s, "C2-C1", "A2-A1")
        self.assertEqual(s.streak[0], 1)
        self.assertFalse(s.unlocked[1])


class SpecialMoveTests(unittest.TestCase):
    def unlocked_for_blue(self):
        s = play(make_state(START), "A1-A2", "C2-C1", "A2-A1", "B3-B2", "A1-A2", "C4-D4", "A2-A1")
        self.assertEqual(s.turn, 1)
        return s

    def test_swap_exchanges_pieces_and_uses_turn(self):
        s = self.unlocked_for_blue()
        before = s.move_counts
        red, blue = s.boards
        s2 = play(s, "swap D4 E5")
        self.assertEqual(s2.turn, 0, "a special move consumes the turn")
        self.assertEqual(s2.move_counts, (before[0], before[1] + 1), "counts as a movement turn")
        self.assertTrue(s2.boards[1] >> parse_cell("E5") & 1)
        self.assertTrue(s2.boards[0] >> parse_cell("D4") & 1)
        self.assertEqual(s2.boards[0].bit_count(), 4)
        self.assertEqual(s2.boards[1].bit_count(), 4)
        self.assertEqual(red | blue, s2.boards[0] | s2.boards[1])
        self.assertEqual(special_status(s2, 1), ("used", "available"))

    def test_swap_once_then_fly_independently(self):
        s = play(self.unlocked_for_blue(), "swap D4 E5", "E1-D1")
        self.assertEqual(kinds(s), {STEP, FLY})
        s2 = play(s, "fly B2 E3")                 # far, non-adjacent destination
        self.assertTrue(s2.boards[1] >> parse_cell("E3") & 1)
        self.assertEqual(special_status(s2, 1), ("used", "used"))
        s2 = play(s2, "D1-E1")
        self.assertEqual(kinds(s2), {STEP})

    def test_fly_then_swap_still_available(self):
        s = play(self.unlocked_for_blue(), "fly B2 E3")
        self.assertEqual(special_status(s, 1), ("available", "used"))
        s = play(s, "E1-D1")
        self.assertEqual(kinds(s), {STEP, SWAP})

    def test_repeated_trigger_does_not_regrant(self):
        s = play(self.unlocked_for_blue(), "swap D4 E5", "E1-D1", "fly B2 E3")
        for _ in range(2):
            s = play(s, "D1-E1", "C1-C2", "E1-D1", "C2-C1")
        self.assertGreaterEqual(s.streak[0], 4)
        self.assertEqual(special_status(s, 1), ("used", "used"))
        s = play(s, "D1-E1")
        self.assertEqual(s.turn, 1)
        self.assertEqual(kinds(s), {STEP})

    def test_specials_never_offered_in_placement(self):
        s = play(new_game(), "place A1", "place B1")
        from teeko.engine.state import GameState
        forced = GameState(s.boards, s.turn, s.move_counts, s.last_step, s.streak, (True, True),
                           s.swap_used, s.fly_used, s.limit, s.ply, None)
        self.assertEqual(kinds(forced), {PLACE})


if __name__ == "__main__":
    unittest.main()
