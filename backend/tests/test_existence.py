import random

import pytest
from ortools.sat.python import cp_model

from backend.app.config import GRID_COLS, GRID_ROWS
from backend.app.core.clues import AtLeastOneCriminalClue, ContradictionError
from backend.app.core.grid import random_grid_layout
from backend.app.core.types import ALL_CELLS, Person, ScopeKind, col_cells, row_cells

NAMES = [
    "Alice", "Bob", "Carl", "Dana", "Eli", "Fay", "Gus", "Hana", "Ivo", "Jill",
    "Kian", "Lea", "Milo", "Nia", "Omar", "Pia", "Quinn", "Rex", "Sara", "Theo",
]  # 20 distinct names, matches NUM_CELLS - a generated grid never repeats a name
PROFESSIONS = ["Chef", "Cop", "Doctor", "Teacher", "Engineer"]
POOL = [Person(NAMES[i], PROFESSIONS[i % len(PROFESSIONS)]) for i in range(len(NAMES))]


@pytest.fixture
def grid():
    return random_grid_layout(POOL, random.Random(5))


def make_solution(criminal_cells):
    criminal_cells = set(criminal_cells)
    return {c: (c in criminal_cells) for c in ALL_CELLS}


def cpsat_agrees(clue, solution) -> bool:
    model = cp_model.CpModel()
    cell_vars = {c: model.NewBoolVar(f"c{c[0]}_{c[1]}") for c in ALL_CELLS}
    for c in ALL_CELLS:
        model.Add(cell_vars[c] == int(solution[c]))
    clue.add_to_model(model, cell_vars)
    solver = cp_model.CpSolver()
    status = solver.Solve(model)
    return status in (cp_model.OPTIMAL, cp_model.FEASIBLE)


def test_evaluate_true_when_every_row_has_a_criminal(grid):
    groups = [row_cells(r) for r in range(GRID_ROWS)]
    clue = AtLeastOneCriminalClue(groups, ScopeKind.ROW, grid)
    assert clue.tier == 2
    assert "reihe" in clue.text.lower()

    solution = make_solution([row_cells(r)[0] for r in range(GRID_ROWS)])  # one criminal per row
    assert clue.evaluate(solution) is True


def test_evaluate_false_when_a_group_has_no_criminal(grid):
    groups = [row_cells(r) for r in range(GRID_ROWS)]
    clue = AtLeastOneCriminalClue(groups, ScopeKind.ROW, grid)
    solution = make_solution([row_cells(r)[0] for r in range(GRID_ROWS - 1)])  # last row gets none
    assert clue.evaluate(solution) is False


def test_propagate_forces_last_unknown_when_group_otherwise_innocent(grid):
    groups = [[(0, 0), (0, 1), (0, 2)]]
    clue = AtLeastOneCriminalClue(groups, ScopeKind.ROW, grid)
    known = {(0, 0): False, (0, 1): False}  # first two innocent, last is the only hope
    assert clue.propagate(known) == {(0, 2): True}


def test_propagate_no_facts_when_multiple_unknowns_remain(grid):
    groups = [[(0, 0), (0, 1), (0, 2)]]
    clue = AtLeastOneCriminalClue(groups, ScopeKind.ROW, grid)
    assert clue.propagate({}) == {}
    assert clue.propagate({(0, 0): False}) == {}  # still 2 unknowns - not forced yet


def test_propagate_no_facts_once_group_already_satisfied(grid):
    groups = [[(0, 0), (0, 1), (0, 2)]]
    clue = AtLeastOneCriminalClue(groups, ScopeKind.ROW, grid)
    assert clue.propagate({(0, 0): True}) == {}  # already has a criminal, nothing more to force


def test_propagate_contradiction_when_group_fully_innocent(grid):
    groups = [[(0, 0), (0, 1)]]
    clue = AtLeastOneCriminalClue(groups, ScopeKind.ROW, grid)
    with pytest.raises(ContradictionError):
        clue.propagate({(0, 0): False, (0, 1): False})


def test_multiple_groups_force_independently(grid):
    groups = [[(0, 0), (0, 1)], [(1, 0), (1, 1)]]
    clue = AtLeastOneCriminalClue(groups, ScopeKind.ROW, grid)
    known = {(0, 0): False, (1, 0): False}
    facts = clue.propagate(known)
    assert facts == {(0, 1): True, (1, 1): True}


def test_cpsat_agreement(grid):
    groups = [col_cells(c) for c in range(GRID_COLS)]
    clue = AtLeastOneCriminalClue(groups, ScopeKind.COL, grid)
    solution_ok = make_solution([col_cells(c)[0] for c in range(GRID_COLS)])
    solution_bad = make_solution([col_cells(c)[0] for c in range(GRID_COLS - 1)])  # last col has none
    assert cpsat_agrees(clue, solution_ok) == clue.evaluate(solution_ok) == True
    assert cpsat_agrees(clue, solution_bad) == clue.evaluate(solution_bad) == False
