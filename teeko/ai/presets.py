"""Difficulty presets and agent construction.

An *agent config* is plain data (picklable, safe to send to worker processes):
``{"algorithm": "minimax" | "mcts", "level": "easy" | ... | "custom", "params": {...}}``.

Time budgets are limits, not guarantees: Medium (the default) targets about
2 s per move, Hard is capped at 4 s and Expert at 8 s. Minimax returns the
deepest fully completed iterative-deepening result; MCTS stops at whichever of
its simulation or time budget runs out first.
"""

import math

from .mcts import MCTSAgent
from .minimax import MinimaxAgent

ALGORITHMS = ("minimax", "mcts")
ALGORITHM_NAMES = {"minimax": "Minimax", "mcts": "MCTS"}
LEVELS = ("easy", "medium", "hard", "expert")
LEVEL_NAMES = {"easy": "Easy", "medium": "Medium", "hard": "Hard", "expert": "Expert",
               "custom": "Custom"}
DEFAULT_LEVEL = "medium"

# Repetition penalties have different scales on purpose:
REP_MM = 8          # Minimax: heuristic evaluation points
REP_MCTS = 0.05     # MCTS: reward units (a win is 1.0)

# Calibrated on an i7-13620H (Python 3.12): Minimax searches ~50-140k nodes/s and
# MCTS completes ~2,500 simulations/s over a whole game. Depth 8 normally takes
# 1-2 s, but with Swap/Fly unlocked (~100 moves per position) depth 7 can take
# 15 s - the time caps and iterative deepening keep every level within budget.
MINIMAX_LEVELS = {
    "easy":   {"depth": 1, "time_limit": 1.0, "randomness": 60},
    "medium": {"depth": 4, "time_limit": 2.0},
    "hard":   {"depth": 6, "time_limit": 4.0},
    "expert": {"depth": 8, "time_limit": 8.0},
}
MCTS_LEVELS = {
    "easy":   {"simulations": 300, "time_limit": 1.0},
    "medium": {"simulations": 3000, "time_limit": 2.0},
    "hard":   {"simulations": 8000, "time_limit": 4.0},
    "expert": {"simulations": 20000, "time_limit": 8.0},
}
CUSTOM_DEFAULTS = {
    "minimax": {"depth": 6, "time_limit": 4.0},
    "mcts": {"simulations": 8000, "time_limit": 4.0, "exploration": round(math.sqrt(2), 2)},
}


def agent_config(algorithm: str, level: str = DEFAULT_LEVEL, **params) -> dict:
    if algorithm not in ALGORITHMS:
        raise ValueError(f"unknown algorithm {algorithm!r}")
    if level == "custom":
        base = dict(CUSTOM_DEFAULTS[algorithm])
    else:
        base = dict((MINIMAX_LEVELS if algorithm == "minimax" else MCTS_LEVELS)[level])
    base.update(params)
    return {"algorithm": algorithm, "level": level, "params": base}


def make_agent(config: dict, seed=None):
    params = dict(config["params"])
    if config["algorithm"] == "minimax":
        params.setdefault("rep_penalty", REP_MM)
        return MinimaxAgent(seed=seed, **params)
    params.setdefault("rep_penalty", REP_MCTS)
    return MCTSAgent(seed=seed, **params)


def _seconds(t) -> str:
    if not t:
        return "no time cap"
    return f"≤{t:g} s"


def budget_text(config: dict) -> str:
    p = config["params"]
    if config["algorithm"] == "minimax":
        extra = ", randomised" if p.get("randomness") else ""
        return f"depth {p['depth']}, {_seconds(p.get('time_limit'))}{extra}"
    text = f"{p['simulations']:,} sims, {_seconds(p.get('time_limit'))}"
    if config["level"] == "custom":
        text += f", C={p.get('exploration', math.sqrt(2)):.2f}"
    return text


def short_label(config: dict) -> str:
    """'Minimax (Medium)'"""
    return f"{ALGORITHM_NAMES[config['algorithm']]} ({LEVEL_NAMES[config['level']]})"


def describe(config: dict) -> str:
    """'Minimax · Medium (depth 3, ≤2 s)'"""
    return (f"{ALGORITHM_NAMES[config['algorithm']]} · {LEVEL_NAMES[config['level']]} "
            f"({budget_text(config)})")
