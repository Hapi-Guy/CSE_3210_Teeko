"""Headless games, AI-vs-AI statistics and the four-combination benchmark.

Fairness: the Minimax-vs-MCTS comparison pools the "Minimax v MCTS" and
"MCTS v Minimax" combinations, so each algorithm plays the same number of games
as P1 and as P2. Game ``i`` of both combinations uses the same seed (same random
opening, same agent RNG streams) - a mirrored pair with sides swapped. Results
are reported per algorithm and per seat, so a first-player advantage is visible
instead of being mistaken for AI strength.

Everything here is pygame-free. ``play_game_job`` is a top-level function with
plain-data arguments so it can be sent to ``multiprocessing`` workers (spawn).
"""

import multiprocessing
import random
import time
from collections import Counter

from ..ai.presets import ALGORITHM_NAMES, make_agent, short_label
from ..engine.rules import apply_move, legal_moves, new_game
from ..engine.state import DEFAULT_LIMIT, SWAP, FLY

COMBOS = (("minimax", "minimax"), ("minimax", "mcts"), ("mcts", "minimax"), ("mcts", "mcts"))
REASON_NAMES = {"line": "line", "square": "square", "limit_score": "limit score",
                "limit_center": "limit centre", "draw": "draw"}


def derive_seed(master: int, *parts: int) -> int:
    x = master & 0xFFFFFFFF
    for p in parts:
        x = (x * 1_000_003 + p + 0x9E3779B9) & 0xFFFFFFFF
    return x


def play_game(p1: dict, p2: dict, limit: int = DEFAULT_LIMIT, seed: int = 0,
              opening_plies: int = 0, agent_ids=("P1", "P2"), should_stop=None) -> dict:
    """Play one complete AI-vs-AI game and return a plain-data record."""
    configs = (p1, p2)
    rng = random.Random(seed)
    s = new_game(limit)
    visited = {s.position_key()}
    times = ([], [])
    specials = [0, 0]
    while s.result is None:
        if should_stop is not None and should_stop():
            return None
        moves = legal_moves(s)
        if s.ply < opening_plies:
            move = rng.choice(moves)
        else:
            agent = make_agent(configs[s.turn], seed=derive_seed(seed, s.ply))
            t0 = time.perf_counter()
            move = agent.choose(s, frozenset(visited)).move
            times[s.turn].append(time.perf_counter() - t0)
            if move not in moves:
                raise RuntimeError(f"{configs[s.turn]['algorithm']} returned an illegal move {move}")
        if move[0] in (SWAP, FLY):
            specials[s.turn] += 1
        s = apply_move(s, move)
        visited.add(s.position_key())
    r = s.result
    return {
        "seed": seed,
        "agents": tuple(agent_ids),
        "labels": (short_label(p1), short_label(p2)),
        "algorithms": (p1["algorithm"], p2["algorithm"]),
        "winner": r.winner,
        "reason": r.reason,
        "plies": s.ply,
        "movement_turns": s.move_counts,
        "times": (tuple(times[0]), tuple(times[1])),
        "specials": tuple(specials),
        "scores": r.scores,
    }


def play_game_job(job: dict) -> dict:
    """Multiprocessing entry point (must stay top-level and picklable)."""
    record = play_game(job["p1"], job["p2"], job["limit"], job["seed"], job["opening_plies"],
                       job["agent_ids"])
    record["combo"] = job["combo"]
    record["index"] = job["index"]
    return record


class TournamentStats:
    """Aggregates game records by seat (P1/P2) and by agent id."""

    def __init__(self):
        self.records = []

    def add(self, record: dict) -> None:
        self.records.append(record)

    @property
    def games(self) -> int:
        return len(self.records)

    def seat_summary(self) -> dict:
        n = self.games
        p1 = sum(1 for r in self.records if r["winner"] == 0)
        p2 = sum(1 for r in self.records if r["winner"] == 1)
        draws = n - p1 - p2
        pct = (lambda k: 100.0 * k / n) if n else (lambda k: 0.0)
        return {"games": n, "p1_wins": p1, "p2_wins": p2, "draws": draws,
                "p1_pct": pct(p1), "p2_pct": pct(p2), "draw_pct": pct(draws)}

    def agent_summary(self) -> dict:
        out = {}
        for r in self.records:
            for seat in (0, 1):
                aid = r["agents"][seat]
                a = out.setdefault(aid, {"label": r["labels"][seat], "games": 0, "wins": 0,
                                         "losses": 0, "draws": 0, "as_p1": 0, "as_p2": 0,
                                         "wins_as_p1": 0, "wins_as_p2": 0, "times": []})
                a["games"] += 1
                a["as_p1" if seat == 0 else "as_p2"] += 1
                if r["winner"] is None:
                    a["draws"] += 1
                elif r["winner"] == seat:
                    a["wins"] += 1
                    a["wins_as_p1" if seat == 0 else "wins_as_p2"] += 1
                else:
                    a["losses"] += 1
                a["times"].extend(r["times"][seat])
        for a in out.values():
            t = a.pop("times")
            a["avg_time"] = sum(t) / len(t) if t else 0.0
            a["win_pct"] = 100.0 * a["wins"] / a["games"] if a["games"] else 0.0
            # draws count half, so the score is comparable to a win rate
            a["score_pct"] = 100.0 * (a["wins"] + 0.5 * a["draws"]) / a["games"] if a["games"] else 0.0
        return out

    def avg_plies(self) -> float:
        return sum(r["plies"] for r in self.records) / self.games if self.games else 0.0

    def avg_movement_turns(self) -> float:
        if not self.games:
            return 0.0
        return sum(sum(r["movement_turns"]) for r in self.records) / self.games

    def seat_times(self) -> tuple:
        out = []
        for seat in (0, 1):
            t = [x for r in self.records for x in r["times"][seat]]
            out.append(sum(t) / len(t) if t else 0.0)
        return tuple(out)

    def reasons(self) -> Counter:
        return Counter(r["reason"] for r in self.records)


def combo_name(combo) -> str:
    return f"{ALGORITHM_NAMES[combo[0]]} v {ALGORITHM_NAMES[combo[1]]}"


def benchmark_jobs(configs: dict, games: int, limit: int = DEFAULT_LIMIT,
                   opening_plies: int = 2, seed: int = 1) -> list:
    """Jobs for the four seat combinations. ``configs`` maps algorithm -> agent config."""
    jobs = []
    for combo in COMBOS:
        a, b = combo
        if a == b:
            ids = (f"{ALGORITHM_NAMES[a]} (P1 seat)", f"{ALGORITHM_NAMES[b]} (P2 seat)")
        else:
            ids = (ALGORITHM_NAMES[a], ALGORITHM_NAMES[b])
        for i in range(games):
            jobs.append({"combo": combo, "index": i, "p1": configs[a], "p2": configs[b],
                         "limit": limit, "opening_plies": opening_plies,
                         "seed": derive_seed(seed, i),        # same seed => mirrored pairs
                         "agent_ids": ids})
    return jobs


def run_benchmark(configs: dict, games: int, limit: int = DEFAULT_LIMIT, opening_plies: int = 2,
                  seed: int = 1, jobs: int = 1, on_progress=None, should_stop=None) -> dict:
    """Play every job (optionally in parallel) and return ``build_report`` output.

    ``should_stop`` is polled between finished games; when it returns True the
    worker pool is terminated and the partial report is returned.
    """
    job_list = benchmark_jobs(configs, games, limit, opening_plies, seed)
    total = len(job_list)
    results = []
    stopped = False
    if jobs <= 1:
        for job in job_list:
            record = play_game(job["p1"], job["p2"], job["limit"], job["seed"], job["opening_plies"],
                               job["agent_ids"], should_stop=should_stop)
            if record is None:
                stopped = True
                break
            record["combo"], record["index"] = job["combo"], job["index"]
            results.append(record)
            if on_progress is not None:
                on_progress(len(results), total, record)
    else:
        ctx = multiprocessing.get_context("spawn")
        pool = ctx.Pool(processes=min(jobs, total))
        try:
            it = pool.imap_unordered(play_game_job, job_list)
            while len(results) < total:
                if should_stop is not None and should_stop():
                    stopped = True
                    break
                try:
                    record = it.next(timeout=0.2)
                except multiprocessing.TimeoutError:
                    continue
                results.append(record)
                if on_progress is not None:
                    on_progress(len(results), total, record)
        finally:
            pool.terminate()
            pool.join()
    report = build_report(results)
    report["stopped"] = stopped
    report["total_jobs"] = total
    report["settings"] = {"games": games, "limit": limit, "opening_plies": opening_plies,
                          "seed": seed, "configs": configs}
    return report


def build_report(results: list) -> dict:
    results = sorted(results, key=lambda r: (COMBOS.index(tuple(r["combo"])), r["index"]))
    by_combo = {}
    for combo in COMBOS:
        stats = TournamentStats()
        for r in results:
            if tuple(r["combo"]) == combo:
                stats.add(r)
        by_combo[combo] = stats
    cross = TournamentStats()          # Minimax v MCTS + MCTS v Minimax, sides balanced
    for r in results:
        if r["combo"][0] != r["combo"][1]:
            cross.add(r)
    return {"by_combo": by_combo, "cross": cross, "results": results}


def format_report(report: dict) -> str:
    lines = []
    header = (f"{'Matchup (P1 v P2)':<20}{'Games':>6}{'P1 win':>8}{'P2 win':>8}{'Draw':>7}"
              f"{'Avg plies':>10}{'Avg moves':>10}{'P1 time':>9}{'P2 time':>9}  End reasons")
    lines.append(header)
    lines.append("-" * len(header))
    for combo, st in report["by_combo"].items():
        if not st.games:
            continue
        s = st.seat_summary()
        t1, t2 = st.seat_times()
        reasons = ", ".join(f"{REASON_NAMES[k]} {v}" for k, v in st.reasons().most_common())
        lines.append(f"{combo_name(combo):<20}{s['games']:>6}{s['p1_pct']:>7.0f}%{s['p2_pct']:>7.0f}%"
                     f"{s['draw_pct']:>6.0f}%{st.avg_plies():>10.1f}{st.avg_movement_turns():>10.1f}"
                     f"{t1:>8.2f}s{t2:>8.2f}s  {reasons}")
    cross = report["cross"]
    if cross.games:
        lines.append("")
        lines.append("Minimax vs MCTS, sides balanced (both cross matchups pooled):")
        for aid, a in sorted(cross.agent_summary().items()):
            lines.append(f"  {aid:<8} {a['wins']:>3} W {a['losses']:>3} L {a['draws']:>3} D"
                         f"   win {a['win_pct']:5.1f}%   score {a['score_pct']:5.1f}%"
                         f"   (as P1 {a['wins_as_p1']}/{a['as_p1']}, as P2 {a['wins_as_p2']}/{a['as_p2']})"
                         f"   avg decision {a['avg_time']:.2f}s")
        s = cross.seat_summary()
        lines.append(f"  by seat: P1 {s['p1_pct']:.0f}%  P2 {s['p2_pct']:.0f}%  draws {s['draw_pct']:.0f}%")
    return "\n".join(lines)
