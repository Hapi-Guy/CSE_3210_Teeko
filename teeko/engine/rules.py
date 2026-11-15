"""The rules of Teeko with the custom Swap/Fly abilities and the movement limit.

This module is the single source of truth for the game: the GUI, the match
controller and both AI agents generate and apply moves only through
``legal_moves`` and ``apply_move`` (and the helpers built on top of them).
"""

from .board import (BIT, CENTER_MASK, FULL_MASK, NEIGHBORS, PATTERN_MASKS, PATTERNS,
                    cells_of, find_pattern_through, lowest_cell)
from .state import (DEFAULT_LIMIT, FLY, PIECES_PER_PLAYER, PLACE, SHUTTLE_TRIGGER, STEP,
                    SWAP, GameResult, GameState)

LIMIT_POINTS = (0, 1, 3, 10, 0)  # open pattern with 1, 2, 3 own pieces (4 = a win)

_NO_SPECIALS = (False, False)


def new_game(limit: int = DEFAULT_LIMIT) -> GameState:
    if limit < 1:
        raise ValueError("movement limit must be at least 1")
    return GameState(boards=(0, 0), turn=0, move_counts=(0, 0), last_step=(None, None),
                     streak=(0, 0), unlocked=_NO_SPECIALS, swap_used=_NO_SPECIALS,
                     fly_used=_NO_SPECIALS, limit=limit, ply=0, result=None)


def _with(pair: tuple, index: int, value) -> tuple:
    return (value, pair[1]) if index == 0 else (pair[0], value)


# --- move generation --------------------------------------------------------
def legal_moves(s: GameState) -> list:
    """All legal actions for the player to move (empty once the game is over)."""
    if s.result is not None:
        return []
    p = s.turn
    own = s.boards[p]
    opp = s.boards[1 - p]
    empty = FULL_MASK & ~(own | opp)

    if own.bit_count() < PIECES_PER_PLAYER:           # placement phase
        return [(PLACE, -1, c) for c in cells_of(empty)]

    moves = []
    own_cells = cells_of(own)
    for f in own_cells:
        for t in cells_of(NEIGHBORS[f] & empty):
            moves.append((STEP, f, t))
    if s.unlocked[p]:
        if not s.swap_used[p]:
            opp_cells = cells_of(opp)
            moves.extend([(SWAP, f, t) for f in own_cells for t in opp_cells])
        if not s.fly_used[p]:
            empty_cells = cells_of(empty)
            moves.extend([(FLY, f, t) for f in own_cells for t in empty_cells])
    return moves


def is_legal(s: GameState, move) -> bool:
    try:
        move = tuple(move)
    except TypeError:
        return False
    return move in legal_moves(s)


# --- applying moves ---------------------------------------------------------
def apply_move(s: GameState, move) -> GameState:
    """Return the state after ``move``. The move must come from ``legal_moves(s)``.

    Win check (identical for every action type): first the mover's patterns,
    then the opponent's. Only patterns through cells that changed can have
    been completed, because the game ends at the first completed pattern.
    A win always takes precedence over movement-limit scoring.
    """
    kind, frm, to = move
    p = s.turn
    o = 1 - p
    own = s.boards[p]
    opp = s.boards[o]
    move_counts = s.move_counts
    last_step = s.last_step
    streak = s.streak
    unlocked = s.unlocked
    swap_used = s.swap_used
    fly_used = s.fly_used
    opp_changed = -1                       # opponent cell that received a piece (Swap only)

    if kind == PLACE:
        own |= BIT[to]
    else:
        move_counts = _with(move_counts, p, move_counts[p] + 1)
        if kind == STEP:
            own ^= BIT[frm] | BIT[to]
            prev = last_step[p]
            # A shuttle continues when this step exactly reverses the previous one.
            run = streak[p] + 1 if prev is not None and prev[1] == to and prev[2] == frm else 1
            last_step = _with(last_step, p, move)
            streak = _with(streak, p, run)
            if run >= SHUTTLE_TRIGGER and not unlocked[o]:
                unlocked = _with(unlocked, o, True)
        else:
            if kind == SWAP:
                both = BIT[frm] | BIT[to]
                own ^= both
                opp ^= both
                swap_used = _with(swap_used, p, True)
                opp_changed = frm
            elif kind == FLY:
                own ^= BIT[frm] | BIT[to]
                fly_used = _with(fly_used, p, True)
            else:
                raise ValueError(f"unknown move kind {kind!r}")
            last_step = _with(last_step, p, None)      # a special breaks the shuttle
            streak = _with(streak, p, 0)

    boards = (own, opp) if p == 0 else (opp, own)

    result = None
    pattern = find_pattern_through(own, to)
    if pattern >= 0:
        result = _pattern_result(p, pattern)
    elif opp_changed >= 0:
        pattern = find_pattern_through(opp, opp_changed)
        if pattern >= 0:
            result = _pattern_result(o, pattern)
    if result is None and kind != PLACE and move_counts[0] >= s.limit and move_counts[1] >= s.limit:
        result = limit_result(boards)

    return GameState(boards, o, move_counts, last_step, streak, unlocked,
                     swap_used, fly_used, s.limit, s.ply + 1, result)


def _pattern_result(winner: int, pattern: int) -> GameResult:
    reason = "square" if PATTERNS[pattern].kind == "square" else "line"
    return GameResult(winner, reason, pattern)


# --- scoring at the movement limit ------------------------------------------
def limit_scores(boards: tuple):
    """Score every pattern that contains no opponent piece: +1/+3/+10 for 1/2/3 own pieces.

    Returns ``(scores, breakdown)`` where ``breakdown[p] = (n1, n2, n3)`` counts the
    open patterns holding 1, 2 and 3 of player p's pieces.
    """
    b0, b1 = boards
    s0 = s1 = 0
    bd0 = [0, 0, 0, 0, 0]
    bd1 = [0, 0, 0, 0, 0]
    for m in PATTERN_MASKS:
        a = (b0 & m).bit_count()
        c = (b1 & m).bit_count()
        if c == 0 and a:
            s0 += LIMIT_POINTS[a]
            bd0[a] += 1
        elif a == 0 and c:
            s1 += LIMIT_POINTS[c]
            bd1[c] += 1
    return (s0, s1), (tuple(bd0[1:4]), tuple(bd1[1:4]))


def center_counts(boards: tuple) -> tuple:
    return ((boards[0] & CENTER_MASK).bit_count(), (boards[1] & CENTER_MASK).bit_count())


def limit_result(boards: tuple) -> GameResult:
    """Outcome when both players have used all movement turns without a win."""
    scores, breakdown = limit_scores(boards)
    center = center_counts(boards)
    if scores[0] != scores[1]:
        winner, reason = (0 if scores[0] > scores[1] else 1), "limit_score"
    elif center[0] != center[1]:
        winner, reason = (0 if center[0] > center[1] else 1), "limit_center"
    else:
        winner, reason = None, "draw"
    return GameResult(winner, reason, None, scores, center, breakdown)


# --- tactical helpers (all derived from the rules above) ---------------------
def winning_moves(s: GameState) -> list:
    """Every legal action that wins immediately for the player to move."""
    if s.result is not None:
        return []
    p = s.turn
    own = s.boards[p]
    opp = s.boards[1 - p]
    empty = FULL_MASK & ~(own | opp)
    wins = []
    if own.bit_count() < PIECES_PER_PLAYER:
        for m in PATTERN_MASKS:
            if (own & m).bit_count() == 3:
                rest = m & ~own
                if rest & empty:
                    wins.append((PLACE, -1, lowest_cell(rest)))
        return list(dict.fromkeys(wins))

    can_swap = s.unlocked[p] and not s.swap_used[p]
    can_fly = s.unlocked[p] and not s.fly_used[p]
    for m in PATTERN_MASKS:
        inside = own & m
        if inside.bit_count() != 3:
            continue
        rest = m ^ inside                       # the one missing cell of the pattern
        f = lowest_cell(own ^ inside)           # the player's fourth piece (outside the pattern)
        e = lowest_cell(rest)
        if rest & empty:
            if NEIGHBORS[f] & rest:
                wins.append((STEP, f, e))
            if can_fly:
                wins.append((FLY, f, e))
        elif can_swap:                          # the missing cell holds an opponent piece
            wins.append((SWAP, f, e))
    return list(dict.fromkeys(wins))


def has_winning_move(s: GameState) -> bool:
    """True when the player to move can win with their next action (fast check)."""
    if s.result is not None:
        return False
    p = s.turn
    own = s.boards[p]
    opp = s.boards[1 - p]
    empty = FULL_MASK & ~(own | opp)
    if own.bit_count() < PIECES_PER_PLAYER:
        for m in PATTERN_MASKS:
            if (own & m).bit_count() == 3 and m & empty & ~own:
                return True
        return False
    can_swap = s.unlocked[p] and not s.swap_used[p]
    can_fly = s.unlocked[p] and not s.fly_used[p]
    for m in PATTERN_MASKS:
        inside = own & m
        if inside.bit_count() != 3:
            continue
        rest = m ^ inside
        if rest & empty:
            if can_fly or NEIGHBORS[lowest_cell(own ^ inside)] & rest:
                return True
        elif can_swap:
            return True
    return False


def threat_targets(s: GameState, player: int) -> int:
    """Mask of cells where ``player`` could complete a pattern on their next turn.

    Ignores whose turn it is; uses ``player``'s own placement/step/special
    abilities. Swap targets are opponent-occupied cells. Used by the heuristic
    evaluation and move ordering only.
    """
    own = s.boards[player]
    opp = s.boards[1 - player]
    empty = FULL_MASK & ~(own | opp)
    targets = 0
    if own.bit_count() < PIECES_PER_PLAYER:
        for m in PATTERN_MASKS:
            if (own & m).bit_count() == 3:
                targets |= m & empty
        return targets
    can_swap = s.unlocked[player] and not s.swap_used[player]
    can_fly = s.unlocked[player] and not s.fly_used[player]
    for m in PATTERN_MASKS:
        inside = own & m
        if inside.bit_count() != 3:
            continue
        rest = m ^ inside
        if rest & empty:
            if can_fly or NEIGHBORS[lowest_cell(own ^ inside)] & rest:
                targets |= rest
        elif can_swap:
            targets |= rest
    return targets


def special_status(s: GameState, player: int) -> tuple:
    """('locked'|'available'|'used') for Swap and for Fly."""
    def status(used: bool) -> str:
        if used:
            return "used"
        return "available" if s.unlocked[player] else "locked"
    return status(s.swap_used[player]), status(s.fly_used[player])


def shuttle_cells(s: GameState, player: int):
    """The two cells of the player's current shuttle, or None (for display)."""
    last = s.last_step[player]
    if last is None:
        return None
    return last[1], last[2]
