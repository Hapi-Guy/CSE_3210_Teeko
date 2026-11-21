"""Minimax with alpha-beta pruning (negamax form).

* Iterative deepening up to ``depth`` plies. When the time budget runs out the
  deepest *fully completed* iteration is used; depth 1 always completes.
* Transposition table keyed by ``GameState.state_key()`` (bounds + best move).
* Move ordering: TT move, blocks of opponent threats, killer moves, history
  heuristic, then a cheap pattern-gain score. Specials are tried late.
* Score convention: every value is from the point of view of the player to
  move at that node. Wins are ``WIN_SCORE - ply`` (faster is better).
* Repetition penalty: an action whose resulting position (board + player to
  move) already occurred in the actual game is worth ``-v - REP`` to the player
  who chose it, where ``v`` is the child's negamax value. The child is searched
  with the alpha-beta window shifted by ``REP`` so pruning stays exact. Only
  real game history is penalised (fixed during a decision), so the TT stays valid.
"""

import random
from operator import itemgetter

from ..engine.board import BIT, PATTERN_MASKS, PATTERNS_BY_CELL
from ..engine.rules import (apply_move, has_winning_move, legal_moves, threat_targets,
                            winning_moves)
from ..engine.state import SWAP, GameState
from .base import Budget, Decision, SearchCancelled
from .evaluation import MATE_THRESHOLD, WIN_SCORE, evaluate

INF = 10 ** 9
EXACT, LOWER, UPPER = 0, 1, 2
MAX_PLY = 64

GAIN = (1, 4, 18, 60)       # moving into an open pattern that already holds 0-3 own pieces
BLOCK = (0, 1, 6, 40)       # moving into an opponent pattern holding 1-3 of their pieces


class _TimeUp(Exception):
    pass


class MinimaxAgent:
    algorithm = "minimax"

    def __init__(self, depth=3, time_limit=None, rep_penalty=8, randomness=0, seed=None):
        if depth < 1:
            raise ValueError("depth must be >= 1")
        self.depth = depth
        self.time_limit = time_limit
        self.rep_penalty = rep_penalty
        self.randomness = randomness      # Easy: pick among root moves within this many points
        self.rng = random.Random(seed)

    # ------------------------------------------------------------------ public
    def choose(self, state: GameState, visited=frozenset(), should_stop=None,
               on_progress=None) -> Decision:
        moves = legal_moves(state)
        if not moves:
            raise ValueError("no legal moves: the game is over")
        self._prepare(visited, should_stop, on_progress)

        wins = winning_moves(state)
        if wins:
            return self._decision(wins[0], WIN_SCORE - 1, 1, "win", {}, [wins[0]])
        if len(moves) == 1:
            return self._decision(moves[0], None, 0, "single", {}, [moves[0]])

        root_moves = self._order(state, moves, None, 0, True)
        best_move, best_score, completed, scores, stop = root_moves[0], None, 0, {}, "depth"
        for depth in range(1, self.depth + 1):
            self.iter_depth = depth
            try:
                score, move, iter_scores = self._search_root(state, root_moves, depth)
            except _TimeUp:
                stop = "time"
                break
            completed, best_move, best_score, scores = depth, move, score, iter_scores
            root_moves.sort(key=lambda m: iter_scores[m], reverse=True)
            self._report(force=True, best=best_move, score=best_score, depth=depth)
            if abs(score) >= MATE_THRESHOLD:
                stop = "forced"
                break
            # The next iteration usually takes several times longer: don't start one
            # that is very unlikely to finish within the budget.
            if (depth < self.depth and self.time_limit
                    and self.budget.elapsed() > 0.5 * self.time_limit):
                stop = "time"
                break

        if self.randomness and scores:
            top = max(scores.values())
            near = [m for m, v in scores.items()
                    if v >= top - self.randomness and v > -MATE_THRESHOLD]
            if near:
                best_move = self.rng.choice(near)
                best_score = scores[best_move]

        pv = [best_move] + self._pv(apply_move(state, best_move), completed - 1)
        return self._decision(best_move, best_score, completed, stop, scores, pv)

    def evaluate_moves(self, state: GameState, visited=frozenset()) -> dict:
        """Exact score of every root move at ``self.depth`` (no root pruning, no time cap).

        Scores are from the point of view of the player to move in ``state``.
        """
        self._prepare(visited, None, None)
        moves = self._order(state, legal_moves(state), None, 0, True)
        scores = {}
        for depth in range(1, self.depth + 1):
            self.iter_depth = depth
            _, _, scores = self._search_root(state, moves, depth, exact_all=True)
            moves.sort(key=lambda m: scores[m], reverse=True)
        return scores

    def _prepare(self, visited, should_stop, on_progress):
        self.budget = Budget(self.time_limit, should_stop)
        self.visited = visited
        self.on_progress = on_progress
        self.tt = {}
        self.killers = [[None, None] for _ in range(MAX_PLY)]
        self.history = {}
        self.nodes = self.tt_hits = self.cutoffs = 0
        self.iter_depth = 0
        self.last_report = 0.0

    # ------------------------------------------------------------------ search
    def _search_root(self, s, moves, depth, exact_all=None):
        alpha, beta = -INF, INF
        best, best_move, scores = -INF, moves[0], {}
        if exact_all is None:
            exact_all = self.randomness > 0
        for m in moves:
            child = apply_move(s, m)
            rep = self._rep(child)
            lo = -INF if exact_all else alpha
            score = -self._negamax(child, depth - 1, -beta - rep, -lo - rep, 1) - rep
            scores[m] = score
            if score > best:
                best, best_move = score, m
            if score > alpha:
                alpha = score
        return best, best_move, scores

    def _negamax(self, s, depth, alpha, beta, ply):
        self.nodes += 1
        if not self.nodes & 1023:
            self._check()

        result = s.result
        if result is not None:
            if result.winner is None:
                return 0
            return WIN_SCORE - ply if result.winner == s.turn else ply - WIN_SCORE
        if has_winning_move(s):               # exact: the player to move wins next ply
            return WIN_SCORE - ply - 1
        if depth <= 0:
            return evaluate(s)

        key = s.state_key()
        entry = self.tt.get(key)
        tt_move = None
        if entry is not None:
            e_depth, e_flag, e_value, tt_move = entry
            if e_depth >= depth:
                v = _from_tt(e_value, ply)
                if (e_flag == EXACT or (e_flag == LOWER and v >= beta)
                        or (e_flag == UPPER and v <= alpha)):
                    self.tt_hits += 1
                    return v

        alpha0 = alpha
        best, best_move = -INF, None
        for m in self._order(s, legal_moves(s), tt_move, ply, depth >= 2):
            child = apply_move(s, m)
            rep = self._rep(child)
            v = -self._negamax(child, depth - 1, -beta - rep, -alpha - rep, ply + 1) - rep
            if v > best:
                best, best_move = v, m
                if v > alpha:
                    alpha = v
                    if alpha >= beta:
                        self.cutoffs += 1
                        self._record_cutoff(m, ply, depth)
                        break

        flag = UPPER if best <= alpha0 else (LOWER if best >= beta else EXACT)
        self.tt[key] = (depth, flag, _to_tt(best, ply), best_move)
        return best

    def _rep(self, child) -> int:
        if child.result is None and child.position_key() in self.visited:
            return self.rep_penalty
        return 0

    # --------------------------------------------------------------- ordering
    def _order(self, s, moves, tt_move, ply, full):
        p = s.turn
        own = s.boards[p]
        opp = s.boards[1 - p]
        threats = threat_targets(s, 1 - p)
        killers = self.killers[ply] if ply < MAX_PLY else (None, None)
        history = self.history
        scored = []
        for m in moves:
            if m == tt_move:
                scored.append((1 << 40, m))
                continue
            kind, f, t = m
            sc = history.get(m, 0)
            if m == killers[0] or m == killers[1]:
                sc += 1 << 28
            if threats and kind != SWAP and BIT[t] & threats:
                sc += 1 << 34                  # occupy a cell the opponent would win on
            if full:
                sc += _gain(own, opp, f, t)
            if kind >= SWAP:
                sc -= 2_000                    # keep single-use specials for when they matter
            scored.append((sc, m))
        scored.sort(key=itemgetter(0), reverse=True)
        return [m for _, m in scored]

    def _record_cutoff(self, m, ply, depth):
        if ply < MAX_PLY:
            k = self.killers[ply]
            if k[0] != m:
                k[1] = k[0]
                k[0] = m
        self.history[m] = self.history.get(m, 0) + depth * depth

    # ----------------------------------------------------------------- budget
    def _check(self):
        if self.budget.cancelled():
            raise SearchCancelled()
        if self.iter_depth > 1 and self.budget.expired():
            raise _TimeUp()
        self._report()

    def _report(self, force=False, **extra):
        if self.on_progress is None:
            return
        now = self.budget.elapsed()
        if not force and now - self.last_report < 0.25:
            return
        self.last_report = now
        info = {"algorithm": "Minimax", "nodes": self.nodes, "time": now,
                "depth": extra.get("depth", self.iter_depth - 1), "searching": self.iter_depth}
        info.update(extra)
        self.on_progress(info)

    # ------------------------------------------------------------------ stats
    def _pv(self, s, length):
        pv = []
        for _ in range(max(0, length)):
            if s.result is not None:
                break
            entry = self.tt.get(s.state_key())
            if entry is None or entry[3] is None or entry[3] not in legal_moves(s):
                break
            pv.append(entry[3])
            s = apply_move(s, entry[3])
        return pv

    def _decision(self, move, score, depth, stop, scores, pv):
        elapsed = self.budget.elapsed()
        top = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:5]
        stats = {
            "algorithm": "Minimax", "depth": depth, "max_depth": self.depth,
            "nodes": self.nodes, "time": elapsed,
            "nps": self.nodes / elapsed if elapsed > 0 else 0.0,
            "score": score, "pv": pv, "top": top, "stop": stop,
            "tt_hits": self.tt_hits, "cutoffs": self.cutoffs,
            "time_limit": self.time_limit,
        }
        return Decision(move, stats)


def _gain(own, opp, f, t):
    g = 0
    for idx in PATTERNS_BY_CELL[t]:
        m = PATTERN_MASKS[idx]
        if not opp & m:
            g += GAIN[(own & m).bit_count()]
        elif not own & m:
            g += BLOCK[(opp & m).bit_count()]
    if f >= 0:
        for idx in PATTERNS_BY_CELL[f]:
            m = PATTERN_MASKS[idx]
            if not opp & m:
                g -= GAIN[(own & m).bit_count() - 1]
    return g


def _to_tt(v, ply):
    if v > MATE_THRESHOLD:
        return v + ply
    if v < -MATE_THRESHOLD:
        return v - ply
    return v


def _from_tt(v, ply):
    if v > MATE_THRESHOLD:
        return v - ply
    if v < -MATE_THRESHOLD:
        return v + ply
    return v
