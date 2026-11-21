"""Monte Carlo Tree Search with UCT selection and an MCTS-Solver.

Each iteration performs the four standard steps:

1. Selection       descend from the root choosing the child that maximises
                   UCT = Q/N - pen + C * sqrt(ln N_parent / N)
                   where Q/N is the mean reward from the point of view of the
                   player who chose that child's move, and ``pen`` is the
                   repetition penalty (``REP_MCTS``, in reward units 0-1) when
                   the child's position already occurred in the real game.
2. Expansion       add one untried legal move as a new child.
3. Simulation      play the game out with ``rollout_policy_move`` (all rules,
                   specials, the movement limit and limit scoring apply).
4. Backpropagation add 1 (win), 0.5 (draw) or 0 (loss) to every node on the path,
                   from the point of view of the player who moved into it.

MCTS-Solver (Winands, Bjornsson & Saito, 2008): plain UCT averages converge
slowly to the value of sharp tactical lines, so proven results are tracked
explicitly. A node is *proven* when its game is over, or when the player to
move there has an immediate win (exact, via the rules engine). Proofs are
propagated upwards: a node is lost for its mover if the opponent has a proven
winning reply, and won if every reply is a proven loss for the opponent.
Selection never enters a proven-lost child while an alternative exists, and
the final move prefers proven wins and avoids proven losses.

The search stops when either the simulation budget or the time budget is
exhausted (or the root is proven) and plays the most-visited root child.
An immediate win at the root is played directly without simulating (the
``shortcut`` stop).
"""

import math
import random

from ..engine.rules import apply_move, has_winning_move, legal_moves, winning_moves
from ..engine.state import STEP, GameState
from .base import Budget, Decision, SearchCancelled

WIN, LOSS = 1, -1          # proof values, from the node mover's point of view


def rollout_policy_move(s: GameState, rng: random.Random, special_bias: float = 0.1):
    """Rollout policy, driven entirely by the shared rules engine.

    1. Play an immediate win if there is one.
    2. Otherwise try candidate actions in random order and play the first *safe*
       one: after it the opponent has no immediate winning reply (by placement,
       step, Swap or Fly, including specials this very action unlocks), and the
       action does not itself end the game in the opponent's favour. Normal moves
       are tried before specials except with probability ``special_bias``.
    3. If no action is safe, play a random legal action.
    """
    wins = winning_moves(s)
    if wins:
        return wins[0] if len(wins) == 1 else wins[int(rng.random() * len(wins))]
    moves = legal_moves(s)
    p = s.turn
    if s.unlocked[p] and not (s.swap_used[p] and s.fly_used[p]):
        normal = [m for m in moves if m[0] <= STEP]
        special = [m for m in moves if m[0] > STEP]
        groups = (special, normal) if rng.random() < special_bias else (normal, special)
    else:
        groups = (list(moves),)
    for pool in groups:
        n = len(pool)
        while n:
            i = int(rng.random() * n)
            m = pool[i]
            n -= 1
            pool[i] = pool[n]
            child = apply_move(s, m)
            result = child.result
            if result is not None:
                if result.winner is None or result.winner == p:
                    return m              # a draw or a win at the movement limit
                continue                  # this action loses on the spot
            if not has_winning_move(child):
                return m
    return moves[int(rng.random() * len(moves))]


class _Node:
    __slots__ = ("move", "parent", "mover", "state", "children", "untried",
                 "visits", "reward", "penalty", "proven")

    def __init__(self, move, parent, mover, state):
        self.move = move
        self.parent = parent
        self.mover = mover            # player who made ``move`` (None at the root)
        self.state = state
        self.children = []
        self.untried = []
        self.visits = 0
        self.reward = 0.0             # total reward from ``mover``'s point of view
        self.penalty = 0.0
        self.proven = None            # WIN / LOSS for ``mover`` once proven

    def proven_winner(self):
        """The player who wins from this node, if proven."""
        if self.proven is None:
            return None
        return self.mover if self.proven == WIN else 1 - self.mover


class MCTSAgent:
    algorithm = "mcts"

    def __init__(self, simulations=600, time_limit=None, exploration=math.sqrt(2),
                 rep_penalty=0.05, special_bias=0.1, seed=None):
        if simulations < 1:
            raise ValueError("simulations must be >= 1")
        self.simulations = simulations
        self.time_limit = time_limit
        self.exploration = exploration
        self.rep_penalty = rep_penalty
        self.special_bias = special_bias
        self.seed = seed

    def choose(self, state: GameState, visited=frozenset(), should_stop=None,
               on_progress=None) -> Decision:
        moves = legal_moves(state)
        if not moves:
            raise ValueError("no legal moves: the game is over")
        budget = Budget(self.time_limit, should_stop)
        rng = random.Random(self.seed)

        wins = winning_moves(state)
        if wins:
            return Decision(wins[0], self._stats(budget, 0, "shortcut", None, 1, 0, None))
        if len(moves) == 1:
            return Decision(moves[0], self._stats(budget, 0, "single", None, 1, 0, None))

        root = _Node(None, None, None, state)
        root.untried = list(moves)
        rng.shuffle(root.untried)
        c = self.exploration
        sims = max_depth = 0
        tree_size = 1
        last_report = 0.0
        stop = "iterations"

        while sims < self.simulations:
            if budget.cancelled():
                raise SearchCancelled()
            if budget.expired():
                stop = "time"
                break
            if root.proven is not None:
                stop = "proven"
                break

            # 1. Selection (never into a proven loss while an alternative exists)
            node = root
            depth = 0
            while not node.untried and node.children and node.proven is None:
                log_n = math.log(node.visits)
                best_val = -1e18
                chosen = None
                for ch in node.children:
                    if ch.proven == WIN:
                        chosen = ch
                        break
                    if ch.proven == LOSS:
                        continue
                    n = ch.visits
                    val = ch.reward / n - ch.penalty + c * math.sqrt(log_n / n)
                    if val > best_val:
                        best_val = val
                        chosen = ch
                if chosen is None:        # every child is lost (proof pending): any will do
                    chosen = max(node.children, key=lambda ch: ch.visits)
                node = chosen
                depth += 1

            # 2. Expansion
            if node.untried and node.proven is None:
                m = node.untried.pop()
                child_state = apply_move(node.state, m)
                child = _Node(m, node, node.state.turn, child_state)
                result = child_state.result
                if result is not None:
                    if result.winner is not None:
                        child.proven = WIN if result.winner == child.mover else LOSS
                elif has_winning_move(child_state):
                    child.proven = LOSS   # the opponent of the mover wins immediately
                else:
                    child.untried = legal_moves(child_state)
                    rng.shuffle(child.untried)
                    if child_state.position_key() in visited:
                        child.penalty = self.rep_penalty
                node.children.append(child)
                node = child
                depth += 1
                tree_size += 1
            if depth > max_depth:
                max_depth = depth

            # 3. Simulation (a proven node's outcome is already known)
            winner = node.proven_winner()
            if winner is None:
                s = node.state
                while s.result is None:
                    s = apply_move(s, rollout_policy_move(s, rng, self.special_bias))
                winner = s.result.winner

            # 4. Backpropagation, with solver proof propagation
            while node is not None:
                node.visits += 1
                if winner is None:
                    node.reward += 0.5
                elif winner == node.mover:
                    node.reward += 1.0
                parent = node.parent
                if parent is not None and parent.proven is None and node.proven is not None:
                    if node.proven == WIN:
                        parent.proven = LOSS      # the player to move at parent wins with node
                    elif not parent.untried and all(ch.proven == LOSS for ch in parent.children):
                        parent.proven = WIN       # every reply loses for the player to move
                node = parent
            sims += 1

            if on_progress is not None and budget.elapsed() - last_report >= 0.25:
                last_report = budget.elapsed()
                best = self._best_child(root)
                on_progress({"algorithm": "MCTS", "simulations": sims,
                             "max_simulations": self.simulations, "time": last_report,
                             "best": best.move, "win_rate": best.reward / best.visits})

        if not root.children:          # budget expired before a single simulation
            move = rollout_policy_move(state, rng, self.special_bias)
            return Decision(move, self._stats(budget, 0, "fallback", None, tree_size, 0, None))

        best = self._best_child(root)
        return Decision(best.move, self._stats(budget, sims, stop, best, tree_size, max_depth, root))

    @staticmethod
    def _best_child(root):
        """Proven win first; otherwise the most-visited child that is not proven lost."""
        for ch in root.children:
            if ch.proven == WIN:
                return ch
        candidates = [ch for ch in root.children if ch.proven != LOSS] or root.children
        return max(candidates, key=lambda ch: (ch.visits, ch.reward / ch.visits))

    def _stats(self, budget, sims, stop, best, tree_size, max_depth, root):
        elapsed = budget.elapsed()
        top = []
        proven = None
        if root is not None:
            ranked = sorted(root.children, key=lambda ch: ch.visits, reverse=True)[:5]
            top = [(ch.move, ch.visits, ch.reward / ch.visits) for ch in ranked]
            if best.proven == WIN:
                proven = "win"
            elif all(ch.proven == LOSS for ch in root.children) and not root.untried:
                proven = "loss"
        return {
            "algorithm": "MCTS", "simulations": sims, "max_simulations": self.simulations,
            "root_visits": root.visits if root is not None else 0,
            "time": elapsed, "sims_per_sec": sims / elapsed if elapsed > 0 else 0.0,
            "stop": stop, "tree_size": tree_size, "max_depth": max_depth,
            "win_rate": best.reward / best.visits if best is not None else None,
            "proven": proven, "top": top, "exploration": self.exploration,
            "time_limit": self.time_limit,
        }
