"""Heuristic evaluation used by Minimax at the search horizon.

Scores are from the point of view of the player to move (negamax convention).
Terminal positions are handled by the search itself, never here.
"""

from ..engine.board import CENTER_MASK, FULL_MASK, NEIGHBORS, PATTERN_MASKS, cells_of, lowest_cell
from ..engine.rules import LIMIT_POINTS
from ..engine.state import PIECES_PER_PLAYER, SHUTTLE_TRIGGER, GameState

WIN_SCORE = 1_000_000
MATE_THRESHOLD = WIN_SCORE - 10_000       # |score| above this means a forced result

# Open pattern (no opponent pieces) holding 1, 2 or 3 own pieces.
PATTERN_WEIGHTS = (0, 2, 9, 45)
DOUBLE_THREAT = 6_000      # opponent can complete two different patterns next turn
SINGLE_THREAT = 120        # opponent has one winning target we must spend our move blocking
CENTER_WEIGHT = 4
MOBILITY_WEIGHT = 2
SPECIAL_AVAILABLE = 55     # an unlocked, unused Swap or Fly
SPECIAL_POTENTIAL = 6      # still unused, but locked
STREAK_PENALTY = (0, 0, 12, 45, 45)  # by shuttle streak length; the 4th move unlocks the opponent
LIMIT_WEIGHT = 30          # weight of the real limit-score difference near the end


def _mobility(own: int, empty: int) -> int:
    total = 0
    for f in cells_of(own):
        total += (NEIGHBORS[f] & empty).bit_count()
    return total


def evaluate(s: GameState) -> int:
    me = s.turn
    op = 1 - me
    own = s.boards[me]
    opp = s.boards[op]
    empty = FULL_MASK & ~(own | opp)

    opp_placing = opp.bit_count() < PIECES_PER_PLAYER
    opp_fly = s.unlocked[op] and not s.fly_used[op]
    opp_swap = s.unlocked[op] and not s.swap_used[op]

    pattern_score = 0
    limit_diff = 0
    opp_targets = 0
    for m in PATTERN_MASKS:
        a = (own & m).bit_count()
        c = (opp & m).bit_count()
        if c == 0:
            if a:
                pattern_score += PATTERN_WEIGHTS[a]
                limit_diff += LIMIT_POINTS[a]
        elif a == 0:
            pattern_score -= PATTERN_WEIGHTS[c]
            limit_diff -= LIMIT_POINTS[c]
        if c == 3:
            # Can the opponent complete this pattern on their next turn?
            inside = opp & m
            rest = m ^ inside
            if rest & empty:
                if opp_placing or opp_fly or NEIGHBORS[lowest_cell(opp ^ inside)] & rest:
                    opp_targets |= rest
            elif opp_swap:
                opp_targets |= rest

    score = pattern_score

    # Threats: the player to move has no immediate win (the search checks that first),
    # so every opponent target must be answered by this move.
    n_threats = opp_targets.bit_count()
    if n_threats >= 2:
        score -= DOUBLE_THREAT
    elif n_threats == 1:
        score -= SINGLE_THREAT

    score += CENTER_WEIGHT * ((own & CENTER_MASK).bit_count() - (opp & CENTER_MASK).bit_count())

    if not s.in_placement:
        score += MOBILITY_WEIGHT * (_mobility(own, empty) - _mobility(opp, empty))

        # Special abilities.
        for player, sign in ((me, 1), (op, -1)):
            for used in (s.swap_used[player], s.fly_used[player]):
                if not used:
                    score += sign * (SPECIAL_AVAILABLE if s.unlocked[player] else SPECIAL_POTENTIAL)

        # Shuttling towards the trigger hands the opponent Swap and Fly.
        if not s.unlocked[op]:
            score -= STREAK_PENALTY[min(s.streak[me], SHUTTLE_TRIGGER)]
        if not s.unlocked[me]:
            score += STREAK_PENALTY[min(s.streak[op], SHUTTLE_TRIGGER)]

        # As the movement limit approaches, the real limit score matters more.
        used = s.move_counts[0] + s.move_counts[1]
        progress = used / (2 * s.limit)
        score += int(LIMIT_WEIGHT * progress * progress * limit_diff)

    return score
