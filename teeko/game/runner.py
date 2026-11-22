"""Run an AI decision without blocking the caller.

``ThreadedRunner`` is used by the GUI: the search runs in a daemon thread on an
immutable ``GameState`` snapshot plus a frozen snapshot of the visited
positions. The worker only writes its own job slot (under a lock); the main
thread polls it every frame. ``cancel()`` asks the search to stop at its next
check and drops the job, so a late result can never be delivered.

``SyncRunner`` computes the decision immediately (tests and the CLI).
"""

import threading
import traceback
from typing import NamedTuple, Optional

from ..ai.base import Decision, SearchCancelled
from ..ai.presets import make_agent
from ..engine.state import GameState


class AIRequest(NamedTuple):
    state: GameState          # immutable snapshot
    visited: frozenset        # snapshot of positions seen in the real game
    config: dict              # agent config (see ai.presets)
    seed: int
    token: int                # identifies the game; stale results are discarded


class AIWorkerError(RuntimeError):
    pass


class _Job:
    __slots__ = ("request", "cancel", "lock", "result", "progress", "error")

    def __init__(self, request: AIRequest):
        self.request = request
        self.cancel = threading.Event()
        self.lock = threading.Lock()
        self.result: Optional[Decision] = None
        self.progress: Optional[dict] = None
        self.error: Optional[str] = None

    def set_progress(self, info: dict) -> None:
        with self.lock:
            self.progress = info


def _compute(job: _Job) -> None:
    req = job.request
    try:
        agent = make_agent(req.config, seed=req.seed)
        decision = agent.choose(req.state, req.visited, should_stop=job.cancel.is_set,
                                on_progress=job.set_progress)
    except SearchCancelled:
        return
    except Exception:  # surfaced to the main thread by poll()
        with job.lock:
            job.error = traceback.format_exc()
        return
    with job.lock:
        job.result = decision


class ThreadedRunner:
    def __init__(self):
        self._job: Optional[_Job] = None

    @property
    def busy(self) -> bool:
        return self._job is not None

    def start(self, request: AIRequest) -> None:
        self.cancel()
        job = _Job(request)
        self._job = job
        threading.Thread(target=_compute, args=(job,), name="teeko-ai", daemon=True).start()

    def poll(self):
        """``(token, Decision)`` once the search has finished, else None."""
        job = self._job
        if job is None:
            return None
        with job.lock:
            if job.error is not None:
                self._job = None
                raise AIWorkerError("AI search failed:\n" + job.error)
            if job.result is None:
                return None
            self._job = None
            return job.request.token, job.result

    def progress(self) -> Optional[dict]:
        job = self._job
        if job is None:
            return None
        with job.lock:
            return job.progress

    def cancel(self) -> None:
        job = self._job
        if job is not None:
            job.cancel.set()
            self._job = None


class SyncRunner:
    """Computes on ``start``; ``poll`` then returns the result once."""

    def __init__(self):
        self._pending = None

    @property
    def busy(self) -> bool:
        return self._pending is not None

    def start(self, request: AIRequest) -> None:
        agent = make_agent(request.config, seed=request.seed)
        self._pending = (request.token, agent.choose(request.state, request.visited))

    def poll(self):
        result, self._pending = self._pending, None
        return result

    def progress(self):
        return None

    def cancel(self) -> None:
        self._pending = None
