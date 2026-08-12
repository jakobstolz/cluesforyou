import random

import pytest

from backend.app.core.clues import ContradictionError, CountConstraintClue, DirectRevealClue
from backend.app.core.grid import random_grid_layout
from backend.app.core.reasoner import propagate_to_fixpoint, run_reasoner
from backend.app.core.types import ALL_CELLS, Person, ScopeKind, row_cells

NAMES = [
    "Alice", "Bob", "Carl", "Dana", "Eli", "Fay", "Gus", "Hana", "Ivo", "Jill",
    "Kian", "Lea", "Milo", "Nia", "Omar", "Pia", "Quinn", "Rex", "Sara", "Theo",
]  # 20 distinct names, matches NUM_CELLS - a generated grid never repeats a name
PROFESSIONS = ["Chef", "Cop", "Doctor", "Teacher", "Engineer"]
POOL = [Person(NAMES[i], PROFESSIONS[i % len(PROFESSIONS)]) for i in range(len(NAMES))]


@pytest.fixture
def grid():
    return random_grid_layout(POOL, random.Random(2))


def make_solution(criminal_cells):
    criminal_cells = set(criminal_cells)
    return {c: (c in criminal_cells) for c in ALL_CELLS}


def test_propagate_to_fixpoint_single_direct_clue(grid):
    clue = DirectRevealClue((0, 0), True, grid)
    known, steps = propagate_to_fixpoint([clue], {})
    assert known == {(0, 0): True}
    assert len(steps) == 1
    assert steps[0].tier == 0


def test_propagate_to_fixpoint_reaches_stable_fixpoint(grid):
    clue = DirectRevealClue((0, 0), True, grid)
    known1, steps1 = propagate_to_fixpoint([clue], {})
    known2, steps2 = propagate_to_fixpoint([clue], known1)
    assert known1 == known2
    assert steps2 == []  # nothing new the second time around


def test_propagate_to_fixpoint_chains_across_clues(grid):
    # A direct clue pins (0,0) criminal; a row clue with target=1 then
    # forces the rest of row 0 innocent in the same fixpoint pass.
    row0 = row_cells(0)
    direct = DirectRevealClue(row0[0], True, grid)
    row_clue = CountConstraintClue(row0, ScopeKind.ROW, target=1, grid=grid, index=0)
    known, steps = propagate_to_fixpoint([direct, row_clue], {})
    assert known == {row0[0]: True, **{c: False for c in row0[1:]}}
    assert {s.clue_id for s in steps} == {direct.id, row_clue.id}


def test_propagate_to_fixpoint_raises_on_contradiction(grid):
    direct = DirectRevealClue((0, 0), True, grid)
    row0 = row_cells(0)
    row_clue = CountConstraintClue(row0, ScopeKind.ROW, target=0, grid=grid, index=0)  # says NO criminals in row 0
    with pytest.raises(ContradictionError):
        propagate_to_fixpoint([direct, row_clue], {})


def test_run_reasoner_full_solve_with_direct_clues_only(grid):
    solution = make_solution(ALL_CELLS[:10])
    clues = [DirectRevealClue(c, solution[c], grid) for c in ALL_CELLS]
    trace = run_reasoner(clues)
    assert trace.solved is True
    assert trace.known == solution
    assert trace.max_tier == 0


def test_run_reasoner_incomplete_clue_set_not_solved(grid):
    solution = make_solution(ALL_CELLS[:10])
    clues = [DirectRevealClue(c, solution[c], grid) for c in ALL_CELLS[:-1]]  # missing one cell
    trace = run_reasoner(clues)
    assert trace.solved is False
    assert len(trace.known) == len(ALL_CELLS) - 1


def test_run_reasoner_respects_initial_known(grid):
    row0 = row_cells(0)
    row_clue = CountConstraintClue(row0, ScopeKind.ROW, target=2, grid=grid, index=0)
    # Without any starting info, an ambiguous row-count clue deduces nothing.
    trace_cold = run_reasoner([row_clue])
    assert row0[0] not in trace_cold.known
    # Seed the two remaining unknowns to their tight case via initial_known.
    seeded = {row0[0]: True, row0[1]: True}
    trace_seeded = run_reasoner([row_clue], initial_known=seeded)
    assert trace_seeded.known == {**seeded, **{c: False for c in row0[2:]}}


def test_tier4_hypothesis_testing_resolves_stuck_case(grid):
    # Three cells with a pairwise-XOR + total-count clue set that tiers 0-3
    # alone cannot crack (every clue is ambiguous from empty known), but
    # single-level hypothesis testing on one cell resolves the rest.
    a, b, c = (0, 0), (0, 1), (0, 2)
    clue_ab = CountConstraintClue([a, b], ScopeKind.CUSTOM_PAIR, target=1, grid=grid)
    clue_bc = CountConstraintClue([b, c], ScopeKind.CUSTOM_PAIR, target=1, grid=grid)
    clue_total = CountConstraintClue([a, b, c], ScopeKind.GLOBAL, target=2, grid=grid)
    clues = [clue_ab, clue_bc, clue_total]

    stuck_known, stuck_steps = propagate_to_fixpoint(clues, {})
    assert stuck_known == {}
    assert stuck_steps == []

    trace_no_tier4 = run_reasoner(clues, allow_tier4=False)
    assert a not in trace_no_tier4.known
    assert trace_no_tier4.solved is False

    trace = run_reasoner(clues, allow_tier4=True)
    assert trace.known[a] is True
    assert trace.known[b] is False
    assert trace.known[c] is True
    assert trace.max_tier == 4

    # The failing hypothesis (a=False) forces b then c (2 steps) before
    # clue_total detects the contradiction - chain depth should be 2.
    hypothesis_steps = [s for s in trace.steps if s.clue_id == "hypothesis"]
    assert len(hypothesis_steps) == 1
    assert hypothesis_steps[0].depth == 2
    assert trace.max_chain_depth == 2


# ---------- pairwise count-clue combination ----------


def test_combination_forces_difference_region_when_tight(grid):
    # A (2 cells, target=1) is a strict subset of B (row0, 4 cells,
    # target=3) - neither clue alone forces anything from empty known, but
    # diff_target = 3 - 1 = 2 = len(diff), so the 2 cells in B\A must both
    # be criminal - exactly the "subtract one clue from another" reasoning
    # a single clue's own propagate() can never produce.
    row0 = row_cells(0)
    a = CountConstraintClue(row0[:2], ScopeKind.CUSTOM_PAIR, target=1, grid=grid)
    b = CountConstraintClue(row0, ScopeKind.ROW, target=3, grid=grid, index=0)

    known_off, steps_off = propagate_to_fixpoint([a, b], {}, allow_combination=False)
    assert known_off == {}  # neither clue alone is tight enough

    known_on, steps_on = propagate_to_fixpoint([a, b], {}, allow_combination=True)
    assert known_on == {row0[2]: True, row0[3]: True}
    assert all(s.clue_id.startswith("combine:") for s in steps_on)
    assert all(s.tier == 3 for s in steps_on)


def test_combination_forces_all_innocent_when_diff_target_zero(grid):
    row0 = row_cells(0)
    a = CountConstraintClue(row0[:2], ScopeKind.CUSTOM_PAIR, target=1, grid=grid)
    b = CountConstraintClue(row0, ScopeKind.ROW, target=1, grid=grid, index=0)  # diff_target = 1-1 = 0
    known, _ = propagate_to_fixpoint([a, b], {}, allow_combination=True)
    assert known == {row0[2]: False, row0[3]: False}


def test_combination_no_info_from_partial_overlap(grid):
    # Two custom-pair clues sharing one cell but neither a subset of the
    # other - combination has nothing to say (no valid subset relation).
    a = CountConstraintClue([(0, 0), (0, 1)], ScopeKind.CUSTOM_PAIR, target=1, grid=grid)
    b = CountConstraintClue([(0, 1), (0, 2)], ScopeKind.CUSTOM_PAIR, target=1, grid=grid)
    known, steps = propagate_to_fixpoint([a, b], {}, allow_combination=True)
    assert known == {}
    assert steps == []


def test_combination_detects_contradiction_under_false_hypothesis(grid):
    # A ⊂ B with diff_target=2 over a 2-cell diff (both must be criminal) -
    # asserting the opposite (both innocent) as a "known" fact is only
    # reachable via a false hypothesis, and combination alone (neither
    # clue's own propagate()) must catch the resulting contradiction.
    row0 = row_cells(0)
    a = CountConstraintClue(row0[:2], ScopeKind.CUSTOM_PAIR, target=1, grid=grid)
    b = CountConstraintClue(row0, ScopeKind.ROW, target=3, grid=grid, index=0)
    bad_known = {row0[2]: False, row0[3]: False}
    with pytest.raises(ContradictionError):
        propagate_to_fixpoint([a, b], bad_known, allow_combination=True)


def test_run_reasoner_used_combination_flag(grid):
    row0 = row_cells(0)
    a = CountConstraintClue(row0[:2], ScopeKind.CUSTOM_PAIR, target=1, grid=grid)
    b = CountConstraintClue(row0, ScopeKind.ROW, target=3, grid=grid, index=0)

    trace_off = run_reasoner([a, b], allow_combination=False)
    assert trace_off.used_combination is False

    trace_on = run_reasoner([a, b], allow_combination=True)
    assert trace_on.used_combination is True
    assert trace_on.known[row0[2]] is True
    assert trace_on.known[row0[3]] is True
