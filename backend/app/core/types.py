"""Core data types shared across the puzzle engine.

A `Cell` is a (row, col) coordinate on the grid (GRID_ROWS x GRID_COLS).
A `Person` is the (name, profession) pair shown to the player at a given
cell. A `Solution` maps every cell to a boolean: True means criminal,
False means innocent.
"""

from __future__ import annotations

from enum import Enum
from typing import NamedTuple

from backend.app.config import GRID_COLS, GRID_ROWS

Cell = tuple[int, int]


class Person(NamedTuple):
    name: str
    profession: str


Grid = list[list[Person]]
Solution = dict[Cell, bool]
KnownState = dict[Cell, bool]

ALL_CELLS: list[Cell] = [(r, c) for r in range(GRID_ROWS) for c in range(GRID_COLS)]


class ScopeKind(str, Enum):
    ROW = "row"
    COL = "col"
    NAME = "name"
    PROFESSION = "profession"
    GLOBAL = "global"
    NEIGHBOR = "neighbor"  # unified 8-neighborhood (was ADJACENT/ADJACENT_DIAGONAL/ADJACENT_ALL)
    ROW_NEIGHBOR = "row_neighbor"  # intersection: a row AND neighboring some anchor person
    COL_NEIGHBOR = "col_neighbor"  # intersection: a column AND neighboring some anchor person
    CUSTOM_PAIR = "custom_pair"
    CORNER = "corner"
    EDGE = "edge"
    INTERIOR = "interior"
    ABOVE = "above"  # person-relative, same COLUMN only - "über/unter/links/rechts von X" phrasing
    BELOW = "below"
    LEFT_OF = "left_of"
    RIGHT_OF = "right_of"
    NORTH_OF = "north_of"  # person-relative, whole half-grid - "nördlich/südlich/westlich/östlich von X" phrasing
    SOUTH_OF = "south_of"
    WEST_OF = "west_of"
    EAST_OF = "east_of"


def row_cells(row: int) -> list[Cell]:
    return [(row, c) for c in range(GRID_COLS)]


def col_cells(col: int) -> list[Cell]:
    return [(r, col) for r in range(GRID_ROWS)]


def name_cells(grid: Grid, name: str) -> list[Cell]:
    return [(r, c) for r in range(GRID_ROWS) for c in range(GRID_COLS) if grid[r][c].name == name]


def profession_cells(grid: Grid, profession: str) -> list[Cell]:
    return [
        (r, c)
        for r in range(GRID_ROWS)
        for c in range(GRID_COLS)
        if grid[r][c].profession == profession
    ]


def profession_group_key(profession: str) -> str:
    """German female profession nouns are formed by appending '-in' to the
    male form (Politiker/Politikerin, Mathematiker/Mathematikerin, ...) -
    strip it so both spellings group as one profession for clue purposes.
    Words that don't end in '-in' (Comedian, DJ, ...) pass through as-is."""
    return profession[:-2] if profession.endswith("in") and len(profession) > 3 else profession


def profession_group_cells(grid: Grid, group_key: str) -> list[Cell]:
    """Every cell whose profession shares `group_key` once gendered
    endings are normalized away - see profession_group_key."""
    return [
        (r, c)
        for r in range(GRID_ROWS)
        for c in range(GRID_COLS)
        if profession_group_key(grid[r][c].profession) == group_key
    ]


def profession_group_label(grid: Grid, group_key: str) -> str:
    """A player-facing label for a profession group: the bare spelling if
    only one variant appears in this grid (e.g. "Comedian"), or a neutral
    "{base}(in)" form if both a male and female spelling are both present
    (e.g. "Politiker(in)")."""
    spellings = {p.profession for row in grid for p in row if profession_group_key(p.profession) == group_key}
    if len(spellings) == 1:
        return next(iter(spellings))
    return f"{group_key}(innen)"


def neighbor_cells(cell: Cell) -> list[Cell]:
    """Orthogonal (up/down/left/right) neighbors within grid bounds."""
    r, c = cell
    candidates = [(r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)]
    return [(rr, cc) for rr, cc in candidates if 0 <= rr < GRID_ROWS and 0 <= cc < GRID_COLS]


def diagonal_neighbor_cells(cell: Cell) -> list[Cell]:
    """The up-to-4 diagonal neighbors within grid bounds."""
    r, c = cell
    candidates = [(r - 1, c - 1), (r - 1, c + 1), (r + 1, c - 1), (r + 1, c + 1)]
    return [(rr, cc) for rr, cc in candidates if 0 <= rr < GRID_ROWS and 0 <= cc < GRID_COLS]


def all_neighbor_cells(cell: Cell) -> list[Cell]:
    """The full neighborhood: orthogonal + diagonal - up to 8 for an
    interior cell, 5 on an edge, 3 in a corner. This is the *only*
    neighbor concept clues use (see ScopeKind.NEIGHBOR) - orthogonal-only
    and diagonal-only are kept as internal helpers, not separate clue
    flavors."""
    return neighbor_cells(cell) + diagonal_neighbor_cells(cell)


def corner_cells() -> list[Cell]:
    last_row, last_col = GRID_ROWS - 1, GRID_COLS - 1
    return [(0, 0), (0, last_col), (last_row, 0), (last_row, last_col)]


def edge_cells() -> list[Cell]:
    """Border cells that aren't corners."""
    last_row, last_col = GRID_ROWS - 1, GRID_COLS - 1
    border = set(row_cells(0)) | set(row_cells(last_row)) | set(col_cells(0)) | set(col_cells(last_col))
    return sorted(border - set(corner_cells()))


def interior_cells() -> list[Cell]:
    """Cells not on the border at all."""
    return [(r, c) for r in range(1, GRID_ROWS - 1) for c in range(1, GRID_COLS - 1)]


def cells_above(cell: Cell) -> list[Cell]:
    """Cells strictly above `cell`, same column only (a straight line
    north - matches cluesbysam's convention). Phrased "über X" -
    contrast with cells_north_of, the whole-half-grid version."""
    r, c = cell
    return [(rr, c) for rr in range(r)]


def cells_below(cell: Cell) -> list[Cell]:
    """Same column, strictly below. Phrased "unter X"."""
    r, c = cell
    return [(rr, c) for rr in range(r + 1, GRID_ROWS)]


def cells_left_of(cell: Cell) -> list[Cell]:
    """Same row, strictly to the left. Phrased "links von X"."""
    r, c = cell
    return [(r, cc) for cc in range(c)]


def cells_right_of(cell: Cell) -> list[Cell]:
    """Same row, strictly to the right. Phrased "rechts von X"."""
    r, c = cell
    return [(r, cc) for cc in range(c + 1, GRID_COLS)]


def cells_north_of(cell: Cell) -> list[Cell]:
    """Every cell with a strictly smaller row index than `cell`, across
    *all* columns (the whole half-grid above it, not just its own
    column - contrast with cells_above). Phrased "nördlich von X"."""
    r, _ = cell
    return [(rr, c) for rr in range(r) for c in range(GRID_COLS)]


def cells_south_of(cell: Cell) -> list[Cell]:
    """Whole half-grid below. Phrased "südlich von X"."""
    r, _ = cell
    return [(rr, c) for rr in range(r + 1, GRID_ROWS) for c in range(GRID_COLS)]


def cells_west_of(cell: Cell) -> list[Cell]:
    """Whole half-grid to the left. Phrased "westlich von X"."""
    _, c = cell
    return [(r, cc) for r in range(GRID_ROWS) for cc in range(c)]


def cells_east_of(cell: Cell) -> list[Cell]:
    """Whole half-grid to the right. Phrased "östlich von X"."""
    _, c = cell
    return [(r, cc) for r in range(GRID_ROWS) for cc in range(c + 1, GRID_COLS)]


def person_at(grid: Grid, cell: Cell) -> Person:
    r, c = cell
    return grid[r][c]


def identity_text(grid: Grid, cell: Cell) -> str:
    """Human-readable identity for a cell, e.g. 'Alice (Chef)'. Avoids
    German gendered articles (der/die/das) entirely rather than guessing."""
    person = person_at(grid, cell)
    return f"{person.name}"
