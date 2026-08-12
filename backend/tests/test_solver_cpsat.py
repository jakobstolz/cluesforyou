import random

from backend.app.core.clues import CountConstraintClue, DirectRevealClue
from backend.app.core.grid import random_grid_layout
from backend.app.core.solver_cpsat import cpsat_is_unique, cpsat_solve_any
from backend.app.core.types import ALL_CELLS, Person, ScopeKind, row_cells

NAMES = [
    "Alice", "Bob", "Carl", "Dana", "Eli", "Fay", "Gus", "Hana", "Ivo", "Jill",
    "Kian", "Lea", "Milo", "Nia", "Omar", "Pia", "Quinn", "Rex", "Sara", "Theo",
]  # 20 distinct names, matches NUM_CELLS - a generated grid never repeats a name
PROFESSIONS = ["Chef", "Cop", "Doctor", "Teacher", "Engineer"]
POOL = [Person(NAMES[i], PROFESSIONS[i % len(PROFESSIONS)]) for i in range(len(NAMES))]


def grid_fixture():
    return random_grid_layout(POOL, random.Random(3))


def make_solution(criminal_cells):
    criminal_cells = set(criminal_cells)
    return {c: (c in criminal_cells) for c in ALL_CELLS}


def test_all_direct_clues_is_unique():
    grid = grid_fixture()
    solution = make_solution(ALL_CELLS[:9])
    clues = [DirectRevealClue(c, solution[c], grid) for c in ALL_CELLS]
    assert cpsat_is_unique(clues) is True
    assert cpsat_solve_any(clues) == solution


def test_no_clues_is_not_unique():
    assert cpsat_is_unique([]) is False


def test_single_partial_clue_is_not_unique():
    grid = grid_fixture()
    row0 = row_cells(0)
    clue = CountConstraintClue(row0, ScopeKind.ROW, target=2, grid=grid, index=0)
    assert cpsat_is_unique([clue]) is False


def test_contradictory_clues_are_unsatisfiable():
    grid = grid_fixture()
    cell = (0, 0)
    clue_a = DirectRevealClue(cell, True, grid)
    clue_b = DirectRevealClue(cell, False, grid)
    assert cpsat_solve_any([clue_a, clue_b]) is None
    assert cpsat_is_unique([clue_a, clue_b]) is False


def test_almost_full_direct_clues_still_not_unique():
    # All but one cell pinned directly -> the last is still free (2 solutions).
    grid = grid_fixture()
    solution = make_solution(ALL_CELLS[:9])
    clues = [DirectRevealClue(c, solution[c], grid) for c in ALL_CELLS[:-1]]
    assert cpsat_is_unique(clues) is False
