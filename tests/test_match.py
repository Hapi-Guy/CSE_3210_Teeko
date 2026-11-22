import threading
import time
import unittest

from helpers import mv

from teeko.ai.base import Decision
from teeko.ai.presets import agent_config
from teeko.engine.rules import legal_moves
from teeko.game.match import IllegalMoveError, Match, PlayerSpec, Series
from teeko.game.runner import AIRequest, SyncRunner, ThreadedRunner
from teeko.game.tournament import (COMBOS, TournamentStats, benchmark_jobs, build_report,
                                   play_game, play_game_job, run_benchmark)

FAST = {"minimax": agent_config("minimax", "custom", depth=1, time_limit=None),
        "mcts": agent_config("mcts", "custom", simulations=20, time_limit=None)}


class FakeRunner:
    """A runner the test completes by hand, to control timing precisely."""

    def __init__(self):
        self.requests = []
        self.ready = None
        self.cancelled = 0

    @property
    def busy(self):
        return bool(self.requests)

    def start(self, request):
        self.requests.append(request)

    def finish(self, move=None):
        req = self.requests[-1]
        move = move or legal_moves(req.state)[0]
        self.ready = (req.token, Decision(move, {"algorithm": "fake", "time": 0.0}))

    def poll(self):
        r, self.ready = self.ready, None
        return r

    def progress(self):
        return None

    def cancel(self):
        self.cancelled += 1


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def ai_vs_ai(runner, **kw):
    players = [PlayerSpec.ai(FAST["minimax"]), PlayerSpec.ai(FAST["mcts"])]
    return Match(players, runner=runner, autostart=False, delay=0.0, **kw)


class MatchControlTests(unittest.TestCase):
    def test_all_four_combinations_finish(self):
        for a, b in COMBOS:
            m = Match([PlayerSpec.ai(FAST[a]), PlayerSpec.ai(FAST[b])], runner=SyncRunner(),
                      delay=0.0, seed=3)
            for _ in range(500):
                if m.over:
                    break
                m.update()
            self.assertTrue(m.over, (a, b))
            self.assertEqual(len(m.history), m.state.ply)
            self.assertEqual(m.status, "over")

    def test_ready_until_start(self):
        runner = FakeRunner()
        m = ai_vs_ai(runner)
        m.update()
        self.assertEqual(runner.requests, [])
        m.start()
        m.update()
        self.assertEqual(len(runner.requests), 1)

    def test_pause_holds_result_and_resume_applies_it(self):
        runner, clock = FakeRunner(), Clock()
        m = ai_vs_ai(runner, clock=clock)
        m.start()
        m.update()
        m.pause()
        runner.finish()
        m.update()
        self.assertEqual(m.state.ply, 0, "result is held while paused")
        m.resume()
        m.update()
        self.assertEqual(m.state.ply, 1)

    def test_step_plays_exactly_one_move(self):
        runner = FakeRunner()
        m = ai_vs_ai(runner)
        m.step()
        m.update()
        runner.finish()
        m.update()
        self.assertEqual(m.state.ply, 1)
        self.assertEqual(m.status, "paused")
        m.update()
        self.assertEqual(len(runner.requests), 1, "no new search after the stepped move")

    def test_restart_drops_stale_results(self):
        runner = FakeRunner()
        m = ai_vs_ai(runner)
        m.start()
        m.update()
        old_token = runner.requests[-1].token
        m.restart()
        self.assertGreaterEqual(runner.cancelled, 1)
        runner.ready = (old_token, Decision(mv("place C3"), {}))   # late result from old game
        m.start()
        m.update()
        self.assertEqual(m.state.ply, 0, "stale result must be ignored")
        self.assertEqual(len(m.history), 0)
        self.assertNotEqual(runner.requests[-1].token, old_token)

    def test_delay_between_moves(self):
        runner, clock = FakeRunner(), Clock()
        players = [PlayerSpec.ai(FAST["minimax"]), PlayerSpec.ai(FAST["mcts"])]
        m = Match(players, runner=runner, delay=1.0, clock=clock)
        m.update()
        runner.finish()
        m.update()
        self.assertEqual(m.state.ply, 1)
        m.update()
        runner.finish()
        clock.t = 0.5
        m.update()
        self.assertEqual(m.state.ply, 1, "waits for the delay")
        clock.t = 1.0
        m.update()
        self.assertEqual(m.state.ply, 2)

    def test_human_moves_are_validated(self):
        m = Match([PlayerSpec.human(), PlayerSpec.ai(FAST["minimax"])], runner=SyncRunner(), delay=0.0)
        self.assertFalse(m.submit_human_move((9, 9, 9)))
        self.assertTrue(m.submit_human_move(mv("place C3")))
        self.assertFalse(m.submit_human_move(mv("place D3")), "not the human's turn")
        m.update()
        self.assertEqual(m.state.ply, 2)
        self.assertFalse(m.submit_human_move(mv("place C3")), "occupied")

    def test_ai_cannot_bypass_validation(self):
        runner = FakeRunner()
        m = ai_vs_ai(runner)
        m.start()
        m.update()
        runner.finish(move=(1, 0, 1))      # a STEP during placement is illegal
        with self.assertRaises(IllegalMoveError):
            m.update()

    def test_runner_gets_immutable_snapshots(self):
        runner = FakeRunner()
        m = Match([PlayerSpec.human(), PlayerSpec.ai(FAST["minimax"])], runner=runner, delay=0.0)
        m.submit_human_move(mv("place C3"))
        m.update()
        req = runner.requests[-1]
        self.assertIsInstance(req.visited, frozenset)
        snapshot_board = req.state.boards
        runner.finish()
        m.update()
        m.submit_human_move(mv("place A1"))
        self.assertEqual(req.state.boards, snapshot_board, "the search's state never changes")
        self.assertNotIn(m.state.position_key(), req.visited)

    def test_threaded_runner_and_cancel(self):
        runner = ThreadedRunner()
        from teeko.engine.rules import new_game
        s = new_game()
        runner.start(AIRequest(s, frozenset({s.position_key()}), FAST["mcts"], 1, 7))
        deadline = time.time() + 10
        result = None
        while result is None and time.time() < deadline:
            result = runner.poll()
            time.sleep(0.01)
        self.assertIsNotNone(result)
        self.assertEqual(result[0], 7)
        self.assertIn(result[1].move, legal_moves(s))
        slow = agent_config("mcts", "custom", simulations=10 ** 7, time_limit=None)
        runner.start(AIRequest(s, frozenset(), slow, 1, 8))
        runner.cancel()
        self.assertIsNone(runner.poll())
        time.sleep(0.3)
        self.assertFalse(any(t.name == "teeko-ai" and t.is_alive() for t in threading.enumerate()),
                         "cancelled search thread should exit promptly")


class SeriesTests(unittest.TestCase):
    def test_series_alternates_seats_and_records_games(self):
        clock = Clock()
        series = Series(FAST["minimax"], FAST["mcts"], games=4, alternate=True, opening_plies=2,
                        delay=0.0, gap=0.0, runner_factory=SyncRunner, clock=clock)
        series.start()
        for _ in range(3000):
            series.update()
            if series.finished:
                break
        self.assertTrue(series.finished)
        self.assertEqual(series.stats.games, 4)
        agents = series.stats.agent_summary()
        self.assertEqual(agents["Agent A"]["as_p1"], 2)
        self.assertEqual(agents["Agent A"]["as_p2"], 2)
        self.assertEqual(agents["Agent B"]["as_p1"], 2)


class TournamentTests(unittest.TestCase):
    def test_cross_matchups_are_side_balanced_and_mirrored(self):
        jobs = benchmark_jobs(FAST, games=3, seed=5)
        self.assertEqual(len(jobs), 12)
        mm_mcts = [j for j in jobs if j["combo"] == ("minimax", "mcts")]
        mcts_mm = [j for j in jobs if j["combo"] == ("mcts", "minimax")]
        self.assertEqual([j["seed"] for j in mm_mcts], [j["seed"] for j in mcts_mm])
        report = build_report([play_game_job(j) for j in jobs])
        agents = report["cross"].agent_summary()
        for alg in ("Minimax", "MCTS"):
            self.assertEqual(agents[alg]["as_p1"], 3)
            self.assertEqual(agents[alg]["as_p2"], 3)

    def test_same_seed_same_results(self):
        a = play_game(FAST["mcts"], FAST["minimax"], seed=42, opening_plies=2)
        b = play_game(FAST["mcts"], FAST["minimax"], seed=42, opening_plies=2)
        for key in ("winner", "reason", "plies", "movement_turns", "scores"):
            self.assertEqual(a[key], b[key])

    def test_tallies_add_up(self):
        report = run_benchmark(FAST, games=2, seed=9, jobs=1)
        self.assertEqual(len(report["results"]), 8)
        for st in report["by_combo"].values():
            s = st.seat_summary()
            self.assertEqual(s["p1_wins"] + s["p2_wins"] + s["draws"], st.games)
        cross = report["cross"]
        agents = cross.agent_summary()
        total_wins = sum(a["wins"] for a in agents.values())
        total_draw_slots = sum(a["draws"] for a in agents.values())
        s = cross.seat_summary()
        self.assertEqual(total_wins, s["p1_wins"] + s["p2_wins"])
        self.assertEqual(total_draw_slots, 2 * s["draws"])
        self.assertEqual(sum(a["games"] for a in agents.values()), 2 * cross.games)

    def test_parallel_benchmark_matches_serial(self):
        serial = run_benchmark(FAST, games=1, seed=4, jobs=1)
        parallel = run_benchmark(FAST, games=1, seed=4, jobs=2)
        key = lambda r: (r["combo"], r["index"], r["winner"], r["plies"])  # noqa: E731
        self.assertEqual(sorted(map(key, serial["results"])), sorted(map(key, parallel["results"])))

    def test_empty_stats(self):
        st = TournamentStats()
        self.assertEqual(st.seat_summary()["games"], 0)
        self.assertEqual(st.avg_plies(), 0.0)


if __name__ == "__main__":
    unittest.main()
