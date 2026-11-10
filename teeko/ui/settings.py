"""What the start screen configures and the game screen plays (pygame-free)."""

import copy
from dataclasses import dataclass, field

from ..ai.presets import CUSTOM_DEFAULTS, agent_config
from ..engine.state import DEFAULT_LIMIT
from ..game.match import PlayerSpec

MODE_NAMES = {"hva": "Human vs AI", "ava": "AI vs AI", "hvh": "Human vs Human"}


def _custom_defaults():
    return {alg: dict(params) for alg, params in CUSTOM_DEFAULTS.items()}


@dataclass
class SeatConfig:
    algorithm: str = "minimax"
    level: str = "medium"
    custom: dict = field(default_factory=_custom_defaults)

    def config(self) -> dict:
        extra = self.custom[self.algorithm] if self.level == "custom" else {}
        return agent_config(self.algorithm, self.level, **extra)


@dataclass
class GameSettings:
    mode: str = "hva"
    human_side: int = 0                     # Human vs AI: 0 = Red (moves first), 1 = Blue
    ai: SeatConfig = field(default_factory=lambda: SeatConfig("minimax"))
    seats: list = field(default_factory=lambda: [SeatConfig("minimax"), SeatConfig("mcts")])
    delay: float = 0.6                      # seconds between AI moves
    series: bool = False                    # AI vs AI auto-play
    series_games: int = 10
    alternate: bool = True
    openings: int = 2                       # random opening plies in a series
    limit: int = DEFAULT_LIMIT

    def players(self) -> list:
        if self.mode == "hvh":
            return [PlayerSpec.human(), PlayerSpec.human()]
        if self.mode == "hva":
            ai = PlayerSpec.ai(self.ai.config())
            return [PlayerSpec.human(), ai] if self.human_side == 0 else [ai, PlayerSpec.human()]
        return [PlayerSpec.ai(seat.config()) for seat in self.seats]

    def copy(self) -> "GameSettings":
        return copy.deepcopy(self)
