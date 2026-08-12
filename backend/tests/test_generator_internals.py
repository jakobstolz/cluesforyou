import random

from backend.app.core.clues import (
    AtLeastOneCriminalClue,
    CompareCountClue,
    CountConstraintClue,
    DirectRevealClue,
)
from backend.app.core.generator import _SolveCache, _clue_family, _stratified_sample
from backend.app.core.grid import random_grid_layout
from backend.app.core.reasoner import run_reasoner
from backend.app.core.solver_cpsat import cpsat_is_unique
from backend.app.core.types import ALL_CELLS, Person, ScopeKind, col_cells, row_cells

NAMES = [
    "Alice", "Bob", "Carl", "Dana", "Eli", "Fay", "Gus", "Hana", "Ivo", "Jill",
    "Kian", "Lea", "Milo", "Nia", "Omar", "Pia", "Quinn", "Rex", "Sara", "Theo",
]
PROFESSIONS = ["Chef", "Cop", "Doctor", "Teacher", "Engineer"]
POOL = [Person(NAMES[i], PROFESSIONS[i % len(PROFESSIONS)]) for i in range(len(NAMES))]


def grid():
    return random_grid_layout(POOL, random.Random(3))


def make_solution(criminal_cells):
    criminal_cells = set(criminal_cells)
    return {c: (c in criminal_cells) for c in ALL_CELLS}


# ---------- _clue_family ----------


def test_clue_family_direct():
    g = grid()
    assert _clue_family(DirectRevealClue((0, 0), True, g)) == "direct"


def test_clue_family_row_col():
    g = grid()
    assert _clue_family(CountConstraintClue(row_cells(0), ScopeKind.ROW, target=1, grid=g, index=0)) == "row_col"
    assert _clue_family(CountConstraintClue(col_cells(0), ScopeKind.COL, target=1, grid=g, index=0)) == "row_col"


def test_clue_family_pair_and_compare_and_existence():
    g = grid()
    pair = CountConstraintClue([(0, 0), (0, 1)], ScopeKind.CUSTOM_PAIR, target=1, grid=g)
    assert _clue_family(pair) == "pair"

    compare = CompareCountClue(row_cells(0), row_cells(1), "GT", "a", "b", g)
    assert _clue_family(compare) == "compare"

    existence = AtLeastOneCriminalClue([row_cells(r) for r in range(5)], ScopeKind.ROW, g)
    assert _clue_family(existence) == "existence"


def test_clue_family_intersection_vs_neighbor():
    g = grid()
    neighbor = CountConstraintClue([(0, 0), (0, 1), (1, 0)], ScopeKind.NEIGHBOR, target=1, grid=g, index=(0, 0))
    assert _clue_family(neighbor) == "neighbor"

    intersection = CountConstraintClue(
        [(0, 0), (0, 1)], ScopeKind.ROW_NEIGHBOR, target=1, grid=g, index=(0, (1, 1))
    )
    assert _clue_family(intersection) == "intersection"


# ---------- _stratified_sample ----------


def test_stratified_sample_returns_everything_when_under_target():
    g = grid()
    clues = [DirectRevealClue(c, True, g) for c in ALL_CELLS[:5]]
    result = _stratified_sample(clues, target_size=10, rng=random.Random(0))
    assert len(result) == 5


def test_stratified_sample_preserves_family_diversity():
    g = grid()
    # Build 5 clues from each of 4 distinct families (20 total), sample
    # down to 8 - a flat random truncation could plausibly starve a whole
    # family; stratified round-robin sampling must not.
    families: list = []
    families += [CountConstraintClue(row_cells(r), ScopeKind.ROW, target=1, grid=g, index=r) for r in range(5)]
    families += [CountConstraintClue(col_cells(c), ScopeKind.COL, target=1, grid=g, index=c) for c in range(4)] + [
        CountConstraintClue([(0, 0), (0, 1)], ScopeKind.CUSTOM_PAIR, target=1, grid=g)
    ]
    pairs = [
        CountConstraintClue([ALL_CELLS[i], ALL_CELLS[i + 1]], ScopeKind.CUSTOM_PAIR, target=1, grid=g)
        for i in range(0, 10, 2)
    ]
    directs = [DirectRevealClue(c, True, g) for c in ALL_CELLS[:5]]

    pool = families + pairs + directs
    result = _stratified_sample(pool, target_size=8, rng=random.Random(1))

    assert len(result) == 8
    families_seen = {_clue_family(c) for c in result}
    assert len(families_seen) >= 3  # meaningfully spread across families, not dominated by one


def test_stratified_sample_is_deterministic_given_same_rng_seed():
    g = grid()
    clues = [DirectRevealClue(c, True, g) for c in ALL_CELLS] + [
        CountConstraintClue(row_cells(r), ScopeKind.ROW, target=1, grid=g, index=r) for r in range(5)
    ]
    result_a = _stratified_sample(clues, target_size=6, rng=random.Random(42))
    result_b = _stratified_sample(clues, target_size=6, rng=random.Random(42))
    assert [c.id for c in result_a] == [c.id for c in result_b]


# ---------- _SolveCache ----------


def test_solve_cache_matches_uncached_reasoner_result():
    g = grid()
    row0 = row_cells(0)
    direct = DirectRevealClue(row0[0], True, g)
    clue = CountConstraintClue(row0, ScopeKind.ROW, target=1, grid=g, index=0)
    clues = [direct, clue]

    cache = _SolveCache()
    cached_trace = cache.solves(clues, allow_tier4=False, allow_combination=False)
    direct_trace = run_reasoner(clues, allow_tier4=False, allow_combination=False)
    assert cached_trace.known == direct_trace.known
    assert cached_trace.solved == direct_trace.solved


def test_solve_cache_returns_identical_object_on_repeat_call():
    g = grid()
    clue = CountConstraintClue(row_cells(0), ScopeKind.ROW, target=1, grid=g, index=0)
    cache = _SolveCache()
    first = cache.solves([clue], allow_tier4=False, allow_combination=False)
    second = cache.solves([clue], allow_tier4=False, allow_combination=False)
    assert first is second  # served from cache, not recomputed


def test_solve_cache_distinguishes_flag_combinations():
    g = grid()
    row0 = row_cells(0)
    a = CountConstraintClue(row0[:2], ScopeKind.CUSTOM_PAIR, target=1, grid=g)
    b = CountConstraintClue(row0, ScopeKind.ROW, target=3, grid=g, index=0)
    cache = _SolveCache()
    without = cache.solves([a, b], allow_tier4=False, allow_combination=False)
    withcombo = cache.solves([a, b], allow_tier4=False, allow_combination=True)
    assert without is not withcombo
    assert without.known != withcombo.known


def test_solve_cache_is_unique_matches_direct_cpsat_call():
    g = grid()
    solution = make_solution(ALL_CELLS[:9])
    clues = [DirectRevealClue(c, solution[c], g) for c in ALL_CELLS]
    cache = _SolveCache()
    assert cache.is_unique(clues) == cpsat_is_unique(clues) == True
