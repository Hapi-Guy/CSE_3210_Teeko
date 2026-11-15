"""Board geometry: cells, neighbours and the 44 winning patterns.

Cells are numbered 0-24 as ``row * 5 + col``. Columns are lettered A-E (left to
right) and rows are numbered 1-5 (top to bottom), matching the proposal mockup.
One side of the board is stored as a 25-bit integer: bit ``i`` is set when
cell ``i`` holds one of that side's pieces.
"""

from typing import NamedTuple

SIZE = 5
NUM_CELLS = SIZE * SIZE
FULL_MASK = (1 << NUM_CELLS) - 1
COLUMNS = "ABCDE"

BIT = tuple(1 << i for i in range(NUM_CELLS))


def cell_index(row: int, col: int) -> int:
    return row * SIZE + col


def cell_row(cell: int) -> int:
    return cell // SIZE


def cell_col(cell: int) -> int:
    return cell % SIZE


CELL_NAMES = tuple(f"{COLUMNS[c]}{r + 1}" for r in range(SIZE) for c in range(SIZE))
_NAME_TO_CELL = {name: i for i, name in enumerate(CELL_NAMES)}


def cell_name(cell: int) -> str:
    return CELL_NAMES[cell]


def parse_cell(name: str) -> int:
    """'C3' -> 12. Raises KeyError for an unknown name."""
    return _NAME_TO_CELL[name.strip().upper()]


def mask_of(*cells: int) -> int:
    mask = 0
    for c in cells:
        mask |= BIT[c]
    return mask


# --- fast iteration over set bits -------------------------------------------
# A 25-bit mask is split into a 13-bit low half and a 12-bit high half; each
# half is looked up in a precomputed table of cell tuples.
_LOW_TABLE = tuple(tuple(i for i in range(13) if m >> i & 1) for m in range(1 << 13))
_HIGH_TABLE = tuple(tuple(i + 13 for i in range(12) if m >> i & 1) for m in range(1 << 12))


def cells_of(mask: int) -> tuple:
    """The cells whose bits are set in ``mask``, in ascending order."""
    return _LOW_TABLE[mask & 0x1FFF] + _HIGH_TABLE[mask >> 13]


def lowest_cell(mask: int) -> int:
    """Index of the lowest set bit (mask must be non-zero)."""
    return (mask & -mask).bit_length() - 1


# --- neighbours (8 directions) ----------------------------------------------
def _neighbour_mask(cell: int) -> int:
    r, c = cell_row(cell), cell_col(cell)
    mask = 0
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            rr, cc = r + dr, c + dc
            if 0 <= rr < SIZE and 0 <= cc < SIZE:
                mask |= BIT[cell_index(rr, cc)]
    return mask


NEIGHBORS = tuple(_neighbour_mask(i) for i in range(NUM_CELLS))


# --- winning patterns -------------------------------------------------------
class Pattern(NamedTuple):
    mask: int
    cells: tuple
    kind: str  # "row", "column", "diagonal", "anti-diagonal" or "square"

    @property
    def is_line(self) -> bool:
        return self.kind != "square"


def _build_patterns() -> tuple:
    patterns = []

    def add(cells, kind):
        patterns.append(Pattern(mask_of(*cells), tuple(cells), kind))

    for r in range(SIZE):                      # 10 horizontal
        for c in range(SIZE - 3):
            add([cell_index(r, c + i) for i in range(4)], "row")
    for c in range(SIZE):                      # 10 vertical
        for r in range(SIZE - 3):
            add([cell_index(r + i, c) for i in range(4)], "column")
    for r in range(SIZE - 3):                  # 4 down-right diagonals
        for c in range(SIZE - 3):
            add([cell_index(r + i, c + i) for i in range(4)], "diagonal")
    for r in range(SIZE - 3):                  # 4 down-left diagonals
        for c in range(3, SIZE):
            add([cell_index(r + i, c - i) for i in range(4)], "anti-diagonal")
    for r in range(SIZE - 1):                  # 16 2x2 squares
        for c in range(SIZE - 1):
            add([cell_index(r, c), cell_index(r, c + 1),
                 cell_index(r + 1, c), cell_index(r + 1, c + 1)], "square")
    return tuple(patterns)


PATTERNS = _build_patterns()
PATTERN_MASKS = tuple(p.mask for p in PATTERNS)
NUM_PATTERNS = len(PATTERNS)  # 10 + 10 + 4 + 4 + 16 = 44

# For every cell: the indices of the patterns that contain it.
PATTERNS_BY_CELL = tuple(
    tuple(i for i, p in enumerate(PATTERNS) if p.mask & BIT[cell]) for cell in range(NUM_CELLS)
)

# The central 3x3 region (B2-D4), used by the limit-scoring tie-break.
CENTER_MASK = mask_of(*(cell_index(r, c) for r in range(1, 4) for c in range(1, 4)))


def find_pattern_through(mask: int, cell: int) -> int:
    """Index of a pattern that contains ``cell`` and is fully covered by ``mask``, or -1."""
    for idx in PATTERNS_BY_CELL[cell]:
        m = PATTERN_MASKS[idx]
        if mask & m == m:
            return idx
    return -1


def find_pattern(mask: int) -> int:
    """Index of any pattern fully covered by ``mask``, or -1."""
    for idx, m in enumerate(PATTERN_MASKS):
        if mask & m == m:
            return idx
    return -1
