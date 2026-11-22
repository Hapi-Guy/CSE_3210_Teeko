"""Benchmark: Minimax vs MCTS over all four seat combinations.

Examples:
    python bench.py --games 10 --level medium --jobs 8
    python bench.py --games 20 --mm-level hard --mcts-level hard --time 1.0 --csv results.csv

Each algorithm plays the same number of games as P1 and as P2 (mirrored pairs share
a seed and random opening), and results are reported per algorithm and per seat.
Reproducibility: the same --seed replays the same games exactly when budgets are
depth/simulation limited; wall-clock time caps can introduce small variations.
"""

import argparse
import csv
import json
import os
import sys
import time

from teeko.ai.presets import LEVELS, agent_config, describe
from teeko.engine.state import DEFAULT_LIMIT
from teeko.game.tournament import format_report, run_benchmark


def build_configs(args) -> dict:
    mm_level = args.mm_level or args.level
    mcts_level = args.mcts_level or args.level
    mm_extra, mcts_extra = {}, {}
    if args.time is not None:
        mm_extra["time_limit"] = args.time
        mcts_extra["time_limit"] = args.time
    if args.mm_depth:
        mm_extra["depth"] = args.mm_depth
    if args.mcts_sims:
        mcts_extra["simulations"] = args.mcts_sims
    return {"minimax": agent_config("minimax", mm_level, **mm_extra),
            "mcts": agent_config("mcts", mcts_level, **mcts_extra)}


def write_csv(path: str, report: dict) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["combo", "index", "seed", "p1", "p2", "winner", "reason", "plies",
                    "p1_moves", "p2_moves", "p1_avg_time", "p2_avg_time", "p1_specials",
                    "p2_specials"])
        for r in report["results"]:
            avg = [sum(t) / len(t) if t else 0.0 for t in r["times"]]
            winner = {0: "P1", 1: "P2", None: "draw"}[r["winner"]]
            w.writerow(["-".join(r["combo"]), r["index"], r["seed"], r["labels"][0], r["labels"][1],
                        winner, r["reason"], r["plies"], r["movement_turns"][0],
                        r["movement_turns"][1], f"{avg[0]:.4f}", f"{avg[1]:.4f}",
                        r["specials"][0], r["specials"][1]])


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--games", type=int, default=6, help="games per seat combination (default 6)")
    p.add_argument("--level", choices=LEVELS, default="easy", help="difficulty for both algorithms")
    p.add_argument("--mm-level", choices=LEVELS, help="override the Minimax level")
    p.add_argument("--mcts-level", choices=LEVELS, help="override the MCTS level")
    p.add_argument("--mm-depth", type=int, help="override the Minimax search depth")
    p.add_argument("--mcts-sims", type=int, help="override the MCTS simulation budget")
    p.add_argument("--time", type=float, help="equal per-move time cap (s) for both algorithms")
    p.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="movement turns per player")
    p.add_argument("--openings", type=int, default=2, help="random opening placements per game")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--jobs", type=int, default=max(1, min(8, (os.cpu_count() or 2) - 1)),
                   help="parallel worker processes")
    p.add_argument("--csv", help="write one row per game to this CSV file")
    p.add_argument("--json", help="write the summary to this JSON file")
    args = p.parse_args(argv)

    configs = build_configs(args)
    print("Teeko AI benchmark")
    for cfg in configs.values():
        print("  " + describe(cfg))
    print(f"  {args.games} games per combination, limit {args.limit}, "
          f"{args.openings} random opening plies, seed {args.seed}, {args.jobs} worker(s)\n")

    started = time.perf_counter()
    total = 4 * args.games

    def progress(done, total_jobs, record):
        sys.stdout.write(f"\r  finished {done}/{total_jobs} games")
        sys.stdout.flush()

    report = run_benchmark(configs, args.games, args.limit, args.openings, args.seed,
                           jobs=args.jobs, on_progress=progress)
    print(f"\r  finished {len(report['results'])}/{total} games in "
          f"{time.perf_counter() - started:.1f} s\n")
    print(format_report(report))

    if args.csv:
        write_csv(args.csv, report)
        print(f"\nPer-game results written to {args.csv}")
    if args.json:
        summary = {
            "settings": report["settings"],
            "combos": {"-".join(c): {**st.seat_summary(), "avg_plies": st.avg_plies(),
                                     "avg_movement_turns": st.avg_movement_turns(),
                                     "avg_time_p1": st.seat_times()[0], "avg_time_p2": st.seat_times()[1],
                                     "reasons": dict(st.reasons())}
                       for c, st in report["by_combo"].items()},
            "minimax_vs_mcts": report["cross"].agent_summary(),
        }
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=2)
        print(f"Summary written to {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
