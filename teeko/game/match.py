"""Match controller: turn flow, AI scheduling and Start/Pause/Resume/Step/Restart.

The controller is frame-driven and pygame-free: the UI calls ``update()`` once
per frame and reads ``state``, ``history`` and ``pop_events()``.

Threading rules: only the thread that calls ``update()`` (the main thread)
mutates the match. An AI turn hands the runner an immutable ``GameState``, a
``frozenset`` snapshot of the visited positions and the current game token.
Results carrying an old token (from before a restart) are ignored.
"""

import random
import time
from dataclasses import dataclass
from typing import Optional

from ..ai.presets import short_label
from ..engine.notation import move_text
from ..engine.rules import apply_move, is_legal, legal_moves, new_game
from ..engine.state import DEFAULT_LIMIT, SWAP
from .runner import AIRequest, ThreadedRunner
from .tournament import TournamentStats, derive_seed


class IllegalMoveError(RuntimeError):
    pass


@dataclass(frozen=True)
class PlayerSpec:
    kind: str                       # "human" or "ai"
    agent: Optional[dict] = None    # agent config for AI players
    agent_id: Optional[str] = None  # identity used in series statistics

    @staticmethod
    def human() -> "PlayerSpec":
        return PlayerSpec("human")

    @staticmethod
    def ai(config: dict, agent_id: Optional[str] = None) -> "PlayerSpec":
        return PlayerSpec("ai", config, agent_id)

    @property
    def is_ai(self) -> bool:
        return self.kind == "ai"

    @property
    def label(self) -> str:
        return short_label(self.agent) if self.is_ai else "Human"


@dataclass
class MoveRecord:
    number: int                 # 1-based action number in the game
    player: int
    move: tuple
    text: str
    phase: str                  # phase before the action
    source: str                 # "human", "ai" or "opening"
    think_time: Optional[float]
    stats: Optional[dict]
    repeated: bool              # recreates an earlier (board, player-to-move) position
    unlocked: Optional[int]     # player whose Swap/Fly this action unlocked


class Match:
    def __init__(self, players, limit: int = DEFAULT_LIMIT, delay: float = 0.6, runner=None,
                 seed: int = 0, opening_plies: int = 0, autostart: bool = True, clock=None):
        self.players = tuple(players)
        assert len(self.players) == 2
        self.limit = limit
        self.delay = delay
        self.seed = seed
        self.opening_plies = opening_plies
        self.autostart = autostart
        self.runner = runner if runner is not None else ThreadedRunner()
        self.clock = clock or time.monotonic
        self.token = 0
        self._reset()

    def _reset(self) -> None:
        self.state = new_game(self.limit)
        self.visited = {self.state.position_key()}
        self.history = []
        self.events = []
        self.status = "running" if self.autostart else "ready"
        self.thinking = False
        self.think_started = None
        self.decision_times = ([], [])
        self.last_stats = [None, None]
        self._decision = None
        self._think_time = None
        self._last_move_at = None
        self._step_pending = False
        self._rng = random.Random(self.seed)

    # ------------------------------------------------------------- queries
    @property
    def over(self) -> bool:
        return self.state.result is not None

    def is_ai_turn(self) -> bool:
        return not self.over and self.players[self.state.turn].is_ai

    def is_human_turn(self) -> bool:
        return not self.over and not self.players[self.state.turn].is_ai

    @property
    def all_ai(self) -> bool:
        return all(p.is_ai for p in self.players)

    def progress(self) -> Optional[dict]:
        return self.runner.progress() if self.thinking else None

    def pop_events(self) -> list:
        events, self.events = self.events, []
        return events

    # ------------------------------------------------------------ controls
    def start(self) -> None:
        if self.status == "ready":
            self.status = "running"

    def pause(self) -> None:
        if self.status == "running":
            self.status = "paused"

    def resume(self) -> None:
        if self.status in ("paused", "ready"):
            self.status = "running"

    def toggle_pause(self) -> None:
        if self.status == "running":
            self.pause()
        else:
            self.resume()

    def step(self) -> None:
        """Play exactly one move, then stay paused."""
        if self.status in ("ready", "paused") and not self.over:
            self.status = "paused"
            self._step_pending = True

    def restart(self) -> None:
        self.runner.cancel()
        self.token += 1
        self._reset()
        self.events.append({"type": "restart"})

    def set_delay(self, seconds: float) -> None:
        self.delay = max(0.0, seconds)

    def cancel(self) -> None:
        """Stop any search (e.g. when leaving the screen)."""
        self.runner.cancel()
        self.token += 1
        self.thinking = False

    # ------------------------------------------------------------- driving
    def update(self, now: Optional[float] = None) -> None:
        if self.over or not self.is_ai_turn():
            return
        now = self.clock() if now is None else now
        active = self.status == "running" or self._step_pending
        ready_to_show = self._step_pending or self._last_move_at is None \
            or now - self._last_move_at >= self.delay

        if self.state.ply < self.opening_plies:        # random opening (series variety)
            if active and ready_to_show:
                self._apply(self._rng.choice(legal_moves(self.state)), "opening", None, None, now)
            return

        if self._decision is None:
            if not self.thinking:
                if not active:
                    return
                spec = self.players[self.state.turn]
                self.runner.start(AIRequest(self.state, frozenset(self.visited), spec.agent,
                                            derive_seed(self.seed, self.state.ply), self.token))
                self.thinking = True
                self.think_started = now
            result = self.runner.poll()
            if result is not None:
                token, decision = result
                if token == self.token:
                    self._decision = decision
                    self._think_time = now - self.think_started
                    self.thinking = False
        if self._decision is not None and active and ready_to_show:
            decision, self._decision = self._decision, None
            self._apply(decision.move, "ai", decision.stats, self._think_time, now)

    def submit_human_move(self, move) -> bool:
        if not self.is_human_turn() or not is_legal(self.state, move):
            return False
        self._apply(tuple(move), "human", None, None, self.clock())
        return True

    def _apply(self, move, source, stats, think_time, now) -> None:
        before = self.state
        if move not in legal_moves(before):     # nobody, AI included, bypasses validation
            raise IllegalMoveError(f"illegal move {move} in {before!r}")
        after = apply_move(before, move)
        key = after.position_key()
        repeated = key in self.visited
        self.visited.add(key)
        unlocked = next((p for p in (0, 1) if after.unlocked[p] and not before.unlocked[p]), None)
        if stats is not None:
            stats = dict(stats, think_time=think_time)
            self.last_stats[before.turn] = stats
            self.decision_times[before.turn].append(stats.get("time", think_time or 0.0))
        record = MoveRecord(len(self.history) + 1, before.turn, move, move_text(move), before.phase,
                            source, think_time, stats, repeated, unlocked)
        self.history.append(record)
        self.state = after
        self._last_move_at = now
        self._step_pending = False
        self.events.append({"type": "move", "record": record, "before": before, "after": after})
        if unlocked is not None:
            self.events.append({"type": "unlock", "player": unlocked, "by": before.turn})
        if after.result is not None:
            self.status = "over"
            self.events.append({"type": "over", "result": after.result})

    def summary(self) -> dict:
        """A tournament-style record of the finished game."""
        r = self.state.result
        return {
            "seed": self.seed,
            "agents": tuple(p.agent_id or p.label for p in self.players),
            "labels": tuple(p.label for p in self.players),
            "algorithms": tuple(p.agent["algorithm"] if p.is_ai else "human" for p in self.players),
            "winner": r.winner if r else None,
            "reason": r.reason if r else "unfinished",
            "plies": self.state.ply,
            "movement_turns": self.state.move_counts,
            "times": (tuple(self.decision_times[0]), tuple(self.decision_times[1])),
            "specials": tuple(sum(1 for h in self.history if h.player == p and h.move[0] >= SWAP)
                              for p in (0, 1)),
            "scores": r.scores if r else None,
        }


class Series:
    """Auto-play: successive AI-vs-AI games between agent A and agent B.

    With ``alternate`` the agents swap seats every game, and each pair of games
    (A as P1, then B as P1) shares a seed: the same random opening, mirrored.
    """

    def __init__(self, agent_a: dict, agent_b: dict, games: int, alternate: bool = True,
                 opening_plies: int = 2, limit: int = DEFAULT_LIMIT, delay: float = 0.6,
                 seed: int = 1, runner_factory=ThreadedRunner, gap: float = 1.5, clock=None):
        self.agents = {"A": agent_a, "B": agent_b}
        self.games = games
        self.alternate = alternate
        self.opening_plies = opening_plies
        self.limit = limit
        self.delay = delay
        self.seed = seed
        self.runner_factory = runner_factory
        self.gap = gap
        self.clock = clock or time.monotonic
        self.stats = TournamentStats()
        self.index = 0
        self.paused = False
        self.match = self._new_match(autostart=False)
        self._recorded = False
        self._next_at = None

    # Start / Pause / Resume / Step apply to the series as a whole.
    def start(self) -> None:
        self.paused = False
        self.match.start()

    def pause(self) -> None:
        self.paused = True
        self.match.pause()

    def resume(self) -> None:
        self.paused = False
        self.match.resume()

    def toggle_pause(self) -> None:
        if self.paused or self.match.status in ("ready", "paused"):
            self.resume()
        else:
            self.pause()

    def step(self) -> None:
        self.paused = True
        if self._recorded and not self.finished:      # between games: open the next one
            self._advance(autostart=False)
        self.match.step()

    def seats(self, index: int) -> tuple:
        return ("B", "A") if self.alternate and index % 2 else ("A", "B")

    def _new_match(self, autostart: bool) -> Match:
        ids = self.seats(self.index)
        players = [PlayerSpec.ai(self.agents[i], f"Agent {i}") for i in ids]
        pair = self.index // 2 if self.alternate else self.index
        return Match(players, self.limit, self.delay, self.runner_factory(),
                     derive_seed(self.seed, pair), self.opening_plies, autostart, self.clock)

    @property
    def finished(self) -> bool:
        return self._recorded and self.index + 1 >= self.games

    def update(self, now: Optional[float] = None) -> bool:
        """Advance; returns True when a new game has just started."""
        now = self.clock() if now is None else now
        self.match.update(now)
        if self.match.over and not self._recorded:
            self.stats.add(self.match.summary())
            self._recorded = True
            self._next_at = now + self.gap
        if self._recorded and not self.finished and not self.paused and now >= self._next_at:
            self._advance(autostart=True)
            return True
        return False

    def _advance(self, autostart: bool) -> None:
        self.index += 1
        self.match = self._new_match(autostart)
        self._recorded = False

    def set_delay(self, seconds: float) -> None:
        self.delay = max(0.0, seconds)
        self.match.set_delay(self.delay)

    def restart(self) -> None:
        self.match.cancel()
        self.stats = TournamentStats()
        self.index = 0
        self.paused = False
        self.match = self._new_match(autostart=False)
        self._recorded = False
