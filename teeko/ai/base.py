"""Types shared by the AI agents."""

import time
from typing import Callable, NamedTuple, Optional


class Decision(NamedTuple):
    move: tuple        # a move from rules.legal_moves(state)
    stats: dict        # search statistics for the UI and benchmarks


class SearchCancelled(Exception):
    """Raised inside a search when its caller asked it to stop (e.g. Restart)."""


StopCheck = Optional[Callable[[], bool]]
ProgressCallback = Optional[Callable[[dict], None]]


class Budget:
    """Wall-clock budget plus cooperative cancellation for one decision."""

    def __init__(self, time_limit: Optional[float], should_stop: StopCheck = None):
        self.start = time.perf_counter()
        self.time_limit = time_limit
        self.deadline = None if not time_limit else self.start + time_limit
        self.should_stop = should_stop

    def elapsed(self) -> float:
        return time.perf_counter() - self.start

    def expired(self) -> bool:
        return self.deadline is not None and time.perf_counter() >= self.deadline

    def cancelled(self) -> bool:
        return self.should_stop is not None and self.should_stop()
