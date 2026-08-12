import random

import pytest
from ortools.sat.python import cp_model

from backend.app.core.clues import (
    CompareCountClue,
    ContradictionError,
    CountConstraintClue,
    DirectRevealClue,
)
from backend.app.core.grid import random_grid_layout
from backend.app.core.types import (
    ALL_CELLS,
    Person,
    ScopeKind,
    all_neighbor_cells,
    col_cells,
    corner_cells,
    edge_cells,
    interior_cells,
    name_cells,
    row_cells,
)

NAMES = [
    "Alice", "Bob", "Carl", "Dana", "Eli", "Fay", "Gus", "Hana", "Ivo", "Jill",
    "Kian", "Lea", "Milo", "Nia", "Omar", "Pia", "Quinn", "Rex", "Sara", "Theo",
]  # 20 distinct names, matches NUM_CELLS - a generated grid never repeats a name
PROFESSIONS = ["Chef", "Cop", "Doctor", "Teacher", "Engineer"]
POOL = [Person(NAMES[i], PROFESSIONS[i % len(PROFESSIONS)]) for i in range(len(NAMES))]


@pytest.fixture
def grid():
    return random_grid_layout(POOL, random.Random(1))


def make_solution(criminal_cells):
    criminal_cells = set(criminal_cells)
    return {c: (c in criminal_cells) for c in ALL_CELLS}


def cpsat_agrees(clue, solution) -> bool:
    """Build a model with all cell vars fixed to `solution`, add the clue's
    constraint, and check feasibility - this must match clue.evaluate()."""
    model = cp_model.CpModel()
    cell_vars = {c: model.NewBoolVar(f"c{c[0]}_{c[1]}") for c in ALL_CELLS}
    for c in ALL_CELLS:
        model.Add(cell_vars[c] == int(solution[c]))
    clue.add_to_model(model, cell_vars)
    solver = cp_model.CpSolver()
    status = solver.Solve(model)
    return status in (cp_model.OPTIMAL, cp_model.FEASIBLE)


# ---------- DirectRevealClue ----------


def test_direct_reveal_evaluate(grid):
    cell = (0, 0)
    clue = DirectRevealClue(cell, True, grid)
    assert clue.evaluate(make_solution([cell])) is True
    assert clue.evaluate(make_solution([])) is False
    assert clue.tier == 0
    assert grid[0][0].name in clue.text


def test_direct_reveal_propagate(grid):
    cell = (1, 1)
    clue = DirectRevealClue(cell, False, grid)
    assert clue.propagate({}) == {cell: False}
    assert clue.propagate({cell: False}) == {}
    with pytest.raises(ContradictionError):
        clue.propagate({cell: True})


def test_direct_reveal_cpsat_agreement(grid):
    cell = (2, 3)
    clue = DirectRevealClue(cell, True, grid)
    sol_match = make_solution([cell])
    sol_mismatch = make_solution([])
    assert cpsat_agrees(clue, sol_match) == clue.evaluate(sol_match) == True
    assert cpsat_agrees(clue, sol_mismatch) == clue.evaluate(sol_mismatch) == False


# ---------- CountConstraintClue ----------


def test_count_row_evaluate_and_tier(grid):
    scope = row_cells(0)
    clue = CountConstraintClue(scope, ScopeKind.ROW, target=2, grid=grid, index=0)
    assert clue.tier == 2
    sol = make_solution(scope[:2])
    assert clue.evaluate(sol) is True
    assert "Reihe 1" in clue.text


def test_count_extreme_is_tier_1(grid):
    scope = col_cells(0)
    clue_zero = CountConstraintClue(scope, ScopeKind.COL, target=0, grid=grid, index=0)
    clue_full = CountConstraintClue(scope, ScopeKind.COL, target=len(scope), grid=grid, index=0)
    assert clue_zero.tier == 1
    assert clue_full.tier == 1


def test_count_propagate_tight_case_all_innocent(grid):
    scope = row_cells(2)
    clue = CountConstraintClue(scope, ScopeKind.ROW, target=1, grid=grid, index=2)
    known = {scope[0]: True}  # already 1 criminal found -> rest must be innocent
    new_facts = clue.propagate(known)
    assert new_facts == {c: False for c in scope[1:]}


def test_count_propagate_tight_case_all_criminal(grid):
    scope = row_cells(3)
    target = len(scope) - 1  # tight but not extreme, still tier 2
    clue = CountConstraintClue(scope, ScopeKind.ROW, target=target, grid=grid, index=3)
    known = {scope[0]: False}  # target needed among remaining unknowns
    new_facts = clue.propagate(known)
    assert new_facts == {c: True for c in scope[1:]}


def test_count_propagate_ambiguous_case_no_facts(grid):
    scope = row_cells(1)
    clue = CountConstraintClue(scope, ScopeKind.ROW, target=2, grid=grid, index=1)
    assert clue.propagate({}) == {}


def test_count_propagate_contradiction(grid):
    scope = row_cells(4)
    clue = CountConstraintClue(scope, ScopeKind.ROW, target=1, grid=grid, index=4)
    known = {scope[0]: True, scope[1]: True}  # already 2 criminals, target is 1
    with pytest.raises(ContradictionError):
        clue.propagate(known)


def test_count_name_and_profession_scopes():
    # A generated grid never repeats a name (see core/grid.py), so the
    # generator no longer produces NAME-scope clues - but the underlying
    # clue mechanics should still work correctly if constructed directly.
    # Build a small grid with a deliberate duplicate name to exercise it.
    dup_grid = [
        [Person("Alice", "Chef"), Person("Alice", "Cop"), Person("Bob", "Doctor"), Person("Carl", "Teacher")],
        [Person("Dana", "Engineer"), Person("Eli", "Chef"), Person("Fay", "Cop"), Person("Gus", "Doctor")],
        [Person("Hana", "Teacher"), Person("Ivo", "Engineer"), Person("Jill", "Chef"), Person("Kian", "Cop")],
        [Person("Lea", "Doctor"), Person("Milo", "Teacher"), Person("Nia", "Engineer"), Person("Omar", "Chef")],
        [Person("Pia", "Cop"), Person("Quinn", "Doctor"), Person("Rex", "Teacher"), Person("Sara", "Engineer")],
    ]
    scope = name_cells(dup_grid, "Alice")
    clue = CountConstraintClue(scope, ScopeKind.NAME, target=1, grid=dup_grid, index="Alice")
    assert "Alice" in clue.text
    assert len(scope) == 2


def test_count_custom_pair_scope(grid):
    a, b = (0, 0), (1, 1)
    clue = CountConstraintClue([a, b], ScopeKind.CUSTOM_PAIR, target=1, grid=grid)
    assert clue.evaluate(make_solution([a])) is True
    assert clue.evaluate(make_solution([a, b])) is False
    new_facts = clue.propagate({a: False})
    assert new_facts == {b: True}


def test_count_cpsat_agreement(grid):
    scope = row_cells(0)
    clue = CountConstraintClue(scope, ScopeKind.ROW, target=2, grid=grid, index=0)
    sol_match = make_solution(scope[:2])
    sol_mismatch = make_solution(scope[:1])
    assert cpsat_agrees(clue, sol_match) == clue.evaluate(sol_match) == True
    assert cpsat_agrees(clue, sol_mismatch) == clue.evaluate(sol_mismatch) == False


# ---------- CountConstraintClue: regions ----------


def test_count_corner_scope(grid):
    scope = corner_cells()
    clue = CountConstraintClue(scope, ScopeKind.CORNER, target=2, grid=grid)
    assert len(scope) == 4
    assert "Ecke" in clue.text
    assert clue.evaluate(make_solution(scope[:2])) is True


def test_count_edge_scope(grid):
    scope = edge_cells()
    clue = CountConstraintClue(scope, ScopeKind.EDGE, target=3, grid=grid)
    assert len(scope) == 10
    assert "Rand" in clue.text
    assert clue.evaluate(make_solution(scope[:3])) is True


def test_count_interior_scope(grid):
    scope = interior_cells()
    clue = CountConstraintClue(scope, ScopeKind.INTERIOR, target=4, grid=grid)
    assert len(scope) == 6
    assert "Inneren" in clue.text
    assert clue.evaluate(make_solution(scope[:4])) is True


# ---------- CountConstraintClue: unified neighbor scope ----------


def test_count_neighbor_scope(grid):
    center = (2, 1)  # interior cell -> full 8-neighborhood
    scope = all_neighbor_cells(center)
    clue = CountConstraintClue(scope, ScopeKind.NEIGHBOR, target=2, grid=grid, index=center)
    assert len(scope) == 8
    assert "neben" in clue.text
    assert clue.evaluate(make_solution(scope[:2])) is True


def test_count_neighbor_scope_corner_has_three_neighbors(grid):
    corner = (0, 0)
    scope = all_neighbor_cells(corner)
    clue = CountConstraintClue(scope, ScopeKind.NEIGHBOR, target=1, grid=grid, index=corner)
    assert len(scope) == 3
    assert clue.evaluate(make_solution(scope[:1])) is True


def test_count_region_cpsat_agreement(grid):
    scope = corner_cells()
    clue = CountConstraintClue(scope, ScopeKind.CORNER, target=1, grid=grid)
    sol_match = make_solution(scope[:1])
    sol_mismatch = make_solution(scope[:2])
    assert cpsat_agrees(clue, sol_match) == clue.evaluate(sol_match) == True
    assert cpsat_agrees(clue, sol_mismatch) == clue.evaluate(sol_mismatch) == False


# ---------- CompareCountClue ----------


def test_compare_gt_evaluate(grid):
    row0, row1 = row_cells(0), row_cells(1)
    clue = CompareCountClue(row0, row1, "GT", "row 1", "row 2", grid)
    sol = make_solution(row0[:2])  # row0 has 2, row1 has 0 -> row0 > row1
    assert clue.evaluate(sol) is True
    assert "mehr Kriminelle" in clue.text or "weniger Unschuldige" in clue.text


def test_compare_lt_evaluate(grid):
    row0, row1 = row_cells(0), row_cells(1)
    clue = CompareCountClue(row0, row1, "LT", "row 1", "row 2", grid)
    sol = make_solution(row1[:2])  # row1 has 2, row0 has 0 -> row0 < row1
    assert clue.evaluate(sol) is True


def test_compare_eq_evaluate(grid):
    row0, row1 = row_cells(0), row_cells(1)
    clue = CompareCountClue(row0, row1, "EQ", "row 1", "row 2", grid)
    sol = make_solution(row0[:2] + row1[:2])  # both have 2 -> equal
    assert clue.evaluate(sol) is True
    assert "gleiche Anzahl" in clue.text or "genauso viele Kriminelle" in clue.text


def test_compare_propagate_forces_bound(grid):
    row0, row1 = row_cells(0), row_cells(1)
    clue = CompareCountClue(row0, row1, "GT", "row 1", "row 2", grid)
    # row1 (lesser) fully known one short of its full length (min_l=max_l);
    # row0 (greater) is fully unknown, so max_g == len(row0) -> the gap is
    # exactly 1 -> every row0 unknown is forced True.
    tight = len(row1) - 1
    known = {c: True for c in row1[:tight]}
    known.update({c: False for c in row1[tight:]})
    facts = clue.propagate(known)
    assert facts == {c: True for c in row0}


def test_compare_propagate_contradiction(grid):
    row0, row1 = row_cells(0), row_cells(1)
    clue = CompareCountClue(row0, row1, "GT", "row 1", "row 2", grid)
    known = {c: False for c in row0}  # row0 forced to 0, can't be > anything >= 0... row1 all innocent too is fine (0>0 false)
    known.update({c: True for c in row1[:1]})  # row1 has at least 1 -> row0(max 0) > row1(min 1) impossible
    with pytest.raises(ContradictionError):
        clue.propagate(known)


def test_compare_cpsat_agreement(grid):
    row0, row1 = row_cells(0), row_cells(1)
    clue = CompareCountClue(row0, row1, "GT", "row 1", "row 2", grid)
    sol_match = make_solution(row0[:2])
    sol_mismatch = make_solution(row1[:2])
    assert cpsat_agrees(clue, sol_match) == clue.evaluate(sol_match) == True
    assert cpsat_agrees(clue, sol_mismatch) == clue.evaluate(sol_mismatch) == False


def test_clue_ids_are_unique(grid):
    c1 = DirectRevealClue((0, 0), True, grid)
    c2 = DirectRevealClue((0, 1), True, grid)
    assert c1.id != c2.id
