import random
from dataclasses import replace

from backend.app.core.clues import (
    AtLeastOneCriminalClue,
    CompareCountClue,
    CountConstraintClue,
    DirectRevealClue,
)
from backend.app.core.difficulty import get_difficulty
from backend.app.core.difficulty_metrics import AttachmentQuality
from backend.app.core.generator import (
    _SolveCache,
    _best_growth_candidate,
    _clue_family,
    _growth_candidate_score,
    _pick_growth_shortlist,
    _stratified_sample,
    attach_clues_to_cells,
)
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


# ---------- _pick_growth_shortlist / _growth_candidate_score / _best_growth_candidate (v9) ----------


def test_pick_growth_shortlist_returns_everything_when_under_k():
    g = grid()
    clues = [DirectRevealClue(c, True, g) for c in ALL_CELLS[:5]]
    result = _pick_growth_shortlist(clues, set(), random.Random(0), k=10)
    assert len(result) == 5


def test_pick_growth_shortlist_samples_k_distinct_candidates():
    g = grid()
    clues = [DirectRevealClue(c, True, g) for c in ALL_CELLS]  # 20 candidates
    result = _pick_growth_shortlist(clues, set(), random.Random(0), k=6)
    assert len(result) == 6
    assert len({c.id for c in result}) == 6  # sampled without replacement


def test_growth_candidate_score_rewards_dependency_over_pure_direct():
    # pair_clue alone is ambiguous (1 of 2 cells is criminal, don't know
    # which). A candidate that reveals (0,0) directly ALSO makes pair_clue
    # newly resolve (0,1) - a genuine dependency (pair_clue's own
    # propagate() only fires once the candidate's fact is available) - vs
    # a candidate that reveals some unrelated cell with zero interaction.
    # Both are equally "1 direct cell revealed" by the old overlap-style
    # accounting; only the dependency-aware score should prefer the first.
    g = grid()
    pair_clue = CountConstraintClue([(0, 0), (0, 1)], ScopeKind.CUSTOM_PAIR, target=1, grid=g)
    chosen = [pair_clue]
    cache = _SolveCache()
    baseline = cache.solves(chosen, allow_tier4=False, allow_combination=False)

    dependency_candidate = DirectRevealClue((0, 0), True, g)
    direct_only_candidate = DirectRevealClue((4, 3), False, g)
    difficulty = get_difficulty("medium")

    dep_score = _growth_candidate_score(dependency_candidate, chosen, baseline.known, difficulty, cache)
    direct_score = _growth_candidate_score(direct_only_candidate, chosen, baseline.known, difficulty, cache)
    assert dep_score > direct_score


def test_growth_candidate_score_is_zero_when_nothing_new_is_derivable():
    g = grid()
    # A clue whose scope is already fully known contributes nothing new.
    already_known_clue = DirectRevealClue((0, 0), True, g)
    chosen = [already_known_clue]
    cache = _SolveCache()
    baseline = cache.solves(chosen, allow_tier4=False, allow_combination=False)
    difficulty = get_difficulty("medium")

    redundant_candidate = DirectRevealClue((0, 0), True, g)  # same cell, same fact, already known
    assert _growth_candidate_score(redundant_candidate, chosen, baseline.known, difficulty, cache) == 0.0


def test_best_growth_candidate_prefers_dependency_over_direct():
    g = grid()
    pair_clue = CountConstraintClue([(0, 0), (0, 1)], ScopeKind.CUSTOM_PAIR, target=1, grid=g)
    chosen = [pair_clue]
    cache = _SolveCache()
    dependency_candidate = DirectRevealClue((0, 0), True, g)
    direct_only_candidate = DirectRevealClue((4, 3), False, g)
    difficulty = get_difficulty("medium")

    best = _best_growth_candidate(
        [dependency_candidate, direct_only_candidate], chosen, difficulty, cache, random.Random(0)
    )
    assert best is dependency_candidate


# ---------- attach_clues_to_cells multi-starter quality search (v9) ----------


def _stub_quality(max_reveal_size: int) -> AttachmentQuality:
    return AttachmentQuality(
        max_reveal_size=max_reveal_size,
        reveal_sizes=[max_reveal_size],
        first_combination_fraction=None,
        combination_fraction_spread=0.0,
        combination_event_count=0,
        combination_deduction_count=0,
    )


def test_attach_clues_to_cells_keeps_best_scoring_starter(monkeypatch):
    g = grid()
    clue = DirectRevealClue((0, 0), True, g)
    chosen = [clue]
    solution = make_solution([(0, 0)])
    difficulty = replace(get_difficulty("medium"), starter_candidates=2)

    quality_low, quality_high = _stub_quality(5), _stub_quality(1)  # smaller max_reveal_size scores better

    def fake_attach_with_starter(chosen_arg, solution_arg, difficulty_arg, starter_cell):
        if starter_cell == (0, 0):
            return {(0, 0): clue}, quality_low
        if starter_cell == (1, 1):
            return {(0, 0): clue}, quality_high
        return None

    monkeypatch.setattr("backend.app.core.generator._attach_with_starter", fake_attach_with_starter)
    monkeypatch.setattr("backend.app.core.generator._starter_candidate_cells", lambda chosen_arg, rng: [(0, 0), (1, 1)])

    result = attach_clues_to_cells(chosen, solution, difficulty, random.Random(0))
    assert result is not None
    starter_cell, _cell_clue, quality = result
    assert starter_cell == (1, 1)
    assert quality is quality_high


def test_attach_clues_to_cells_tries_at_most_starter_candidates_cells(monkeypatch):
    g = grid()
    clue = DirectRevealClue((0, 0), True, g)
    chosen = [clue]
    solution = make_solution([(0, 0)])
    difficulty = replace(get_difficulty("medium"), starter_candidates=1)  # today's default single-starter behavior

    tried: list = []

    def fake_attach_with_starter(chosen_arg, solution_arg, difficulty_arg, starter_cell):
        tried.append(starter_cell)
        return {(0, 0): clue}, _stub_quality(1)

    monkeypatch.setattr("backend.app.core.generator._attach_with_starter", fake_attach_with_starter)
    monkeypatch.setattr(
        "backend.app.core.generator._starter_candidate_cells", lambda chosen_arg, rng: [(0, 0), (1, 1), (2, 2)]
    )

    attach_clues_to_cells(chosen, solution, difficulty, random.Random(0))
    assert tried == [(0, 0)]  # only the first candidate tried - matching starter_candidates=1


def test_attach_clues_to_cells_returns_none_when_every_starter_fails(monkeypatch):
    g = grid()
    clue = DirectRevealClue((0, 0), True, g)
    chosen = [clue]
    solution = make_solution([(0, 0)])
    difficulty = replace(get_difficulty("medium"), starter_candidates=3)

    monkeypatch.setattr("backend.app.core.generator._attach_with_starter", lambda *a: None)
    monkeypatch.setattr(
        "backend.app.core.generator._starter_candidate_cells", lambda chosen_arg, rng: [(0, 0), (1, 1), (2, 2)]
    )

    assert attach_clues_to_cells(chosen, solution, difficulty, random.Random(0)) is None
