import random

from backend.app.core.clues import CountConstraintClue
from backend.app.core.clues.base import ReasoningTrace, Step
from backend.app.core.difficulty import EASY, HARD, MEDIUM
from backend.app.core.difficulty_metrics import (
    analyze_attachment_steps,
    build_dependency_depths,
    compute_metrics,
    score_attachment_quality,
)
from backend.app.core.grid import random_grid_layout
from backend.app.core.reasoner import run_reasoner
from backend.app.core.types import Person, ScopeKind, row_cells

NAMES = [
    "Alice", "Bob", "Carl", "Dana", "Eli", "Fay", "Gus", "Hana", "Ivo", "Jill",
    "Kian", "Lea", "Milo", "Nia", "Omar", "Pia", "Quinn", "Rex", "Sara", "Theo",
]
PROFESSIONS = ["Chef", "Cop", "Doctor", "Teacher", "Engineer"]
POOL = [Person(NAMES[i], PROFESSIONS[i % len(PROFESSIONS)]) for i in range(len(NAMES))]


def test_build_dependency_depths_root_facts_are_zero():
    steps = [
        Step("c1", 0, (0, 0), True, "text", used_cells=frozenset(), used_clue_ids=("c1",)),
        Step("c2", 0, (0, 1), True, "text", used_cells=frozenset(), used_clue_ids=("c2",)),
    ]
    depths = build_dependency_depths(steps)
    assert depths == {(0, 0): 0, (0, 1): 0}


def test_build_dependency_depths_chains():
    steps = [
        Step("c1", 0, (0, 0), True, "text", used_cells=frozenset(), used_clue_ids=("c1",)),
        Step("c2", 2, (0, 1), True, "text", used_cells=frozenset({(0, 0)}), used_clue_ids=("c2",)),
        Step("c3", 2, (0, 2), True, "text", used_cells=frozenset({(0, 1)}), used_clue_ids=("c3",)),
    ]
    depths = build_dependency_depths(steps)
    assert depths == {(0, 0): 0, (0, 1): 1, (0, 2): 2}


def test_build_dependency_depths_takes_deepest_prerequisite():
    # (0,2) depends on both (0,0) [depth 0] and (0,1) [depth 1] -> depth 2.
    steps = [
        Step("c1", 0, (0, 0), True, "text", used_cells=frozenset(), used_clue_ids=("c1",)),
        Step("c2", 0, (1, 0), True, "text", used_cells=frozenset(), used_clue_ids=("c2",)),
        Step("c3", 2, (0, 1), True, "text", used_cells=frozenset({(1, 0)}), used_clue_ids=("c3",)),
        Step("c4", 2, (0, 2), True, "text", used_cells=frozenset({(0, 0), (0, 1)}), used_clue_ids=("c4",)),
    ]
    depths = build_dependency_depths(steps)
    assert depths[(0, 2)] == 2


def test_compute_metrics_empty_trace():
    trace = ReasoningTrace(known={})
    m = compute_metrics(trace)
    assert m.max_depth == 0
    assert m.avg_depth == 0.0
    assert m.nontrivial_deductions == 0
    assert m.max_round_branching == 0
    assert m.combination_steps == 0


def test_compute_metrics_counts_combination_steps_as_nontrivial():
    steps = [
        Step("c1", 0, (0, 0), True, "text", round=0, used_cells=frozenset(), used_clue_ids=("c1",)),
        Step(
            "combine:c1:c2", 3, (0, 1), True, "text",
            round=0, used_cells=frozenset({(0, 0)}), used_clue_ids=("c1", "c2"),
        ),
    ]
    trace = ReasoningTrace(known={(0, 0): True, (0, 1): True}, steps=steps)
    m = compute_metrics(trace)
    assert m.combination_steps == 1
    assert m.nontrivial_deductions == 1  # the tier-0 direct step doesn't count, the combine step does
    assert m.avg_clues_per_deduction == 1.5  # (1 + 2) / 2
    assert m.max_round_branching == 2  # both steps fired in round 0


def test_compute_metrics_branching_across_rounds():
    steps = [
        Step("c1", 0, (0, 0), True, "text", round=0, used_cells=frozenset(), used_clue_ids=("c1",)),
        Step("c2", 0, (0, 1), True, "text", round=0, used_cells=frozenset(), used_clue_ids=("c2",)),
        Step("c3", 2, (0, 2), True, "text", round=1, used_cells=frozenset({(0, 0)}), used_clue_ids=("c3",)),
    ]
    trace = ReasoningTrace(known={c: True for c in [(0, 0), (0, 1), (0, 2)]}, steps=steps)
    m = compute_metrics(trace)
    assert m.max_round_branching == 2  # round 0 had 2 simultaneous steps, round 1 had 1


def test_compute_metrics_on_real_combination_trace():
    grid = random_grid_layout(POOL, random.Random(1))
    row0 = row_cells(0)
    a = CountConstraintClue(row0[:2], ScopeKind.CUSTOM_PAIR, target=1, grid=grid)
    b = CountConstraintClue(row0, ScopeKind.ROW, target=3, grid=grid, index=0)
    trace = run_reasoner([a, b], allow_combination=True)
    m = compute_metrics(trace)
    assert m.combination_steps == 2  # both diff cells forced via combine
    assert m.nontrivial_deductions == 2
    assert m.avg_clues_per_deduction == 2.0  # every step here came from a combine (2 clues each)
    # Both derive straight from the two clues' fixed targets alone, with
    # no prior *cell* fact needed - a legitimate depth-0 case (depth
    # tracks cell-to-cell dependency, not how many clues were involved;
    # that's what used_clue_ids/nontrivial_deductions are for).
    assert m.max_depth == 0


# ---------- AttachmentQuality / analyze_attachment_steps / score_attachment_quality ----------


def test_analyze_attachment_steps_empty():
    q = analyze_attachment_steps([])
    assert q.max_reveal_size == 0
    assert q.reveal_sizes == []
    assert q.first_combination_fraction is None
    assert q.combination_fraction_spread == 0.0
    assert q.combination_event_count == 0
    assert q.combination_deduction_count == 0


def test_analyze_attachment_steps_groups_reveal_sizes_by_clue():
    steps = [
        Step("c1", 2, (0, 0), True, "text", used_clue_ids=("c1",)),
        Step("c1", 2, (0, 1), True, "text", used_clue_ids=("c1",)),
        Step("c1", 2, (0, 2), True, "text", used_clue_ids=("c1",)),
        Step("c2", 0, (1, 0), True, "text", used_clue_ids=("c2",)),
    ]
    q = analyze_attachment_steps(steps)
    assert sorted(q.reveal_sizes) == [1, 3]
    assert q.max_reveal_size == 3


def test_analyze_attachment_steps_first_combination_fraction():
    steps = [
        Step("c1", 0, (0, 0), True, "text", used_clue_ids=("c1",)),
        Step("c2", 2, (0, 1), True, "text", used_clue_ids=("c2",)),
        Step("c3", 2, (0, 2), True, "text", used_clue_ids=("c3",)),
        Step("c4", 2, (0, 3), True, "text", used_clue_ids=("c4",)),
        Step("combine:c1:c2", 3, (1, 0), True, "text", used_clue_ids=("c1", "c2")),
    ]
    q = analyze_attachment_steps(steps)
    assert q.first_combination_fraction == 4 / 5  # the combine step is the last (5th) of 5
    assert q.combination_fraction_spread == 0.0  # only one combination event


def test_analyze_attachment_steps_spread_across_multiple_combination_events():
    steps = [
        Step("combine:a:b", 3, (0, 0), True, "text", used_clue_ids=("a", "b")),
        Step("c1", 0, (0, 1), True, "text", used_clue_ids=("c1",)),
        Step("c2", 0, (0, 2), True, "text", used_clue_ids=("c2",)),
        Step("combine:c:d", 3, (0, 3), True, "text", used_clue_ids=("c", "d")),
    ]
    q = analyze_attachment_steps(steps)
    assert q.first_combination_fraction == 0.0  # first step is a combine step
    assert q.combination_fraction_spread > 0.0  # two combine events, spread apart
    assert q.combination_event_count == 2  # drives Hard's min_combination_events requirement
    assert q.combination_deduction_count == 2  # one forced cell per event here, so equal - see next test for the distinction


def test_analyze_attachment_steps_one_event_forcing_several_cells_is_one_event_not_several():
    # The bug this distinction fixes: reasoner.py's _derive_pair_facts can
    # force an entire multi-cell difference region from a SINGLE src/dst
    # combination (same clue_id, "combine:a:b", for every cell it forces in
    # that one event) - that must count as ONE combination event, not one
    # per forced cell, or difficulty.min_combination_events would be
    # satisfiable by luck (one lucky event forcing 3 cells) instead of by
    # genuinely needing several separate combination moments.
    steps = [
        Step("c1", 0, (0, 0), True, "text", used_clue_ids=("c1",)),
        Step("combine:a:b", 3, (0, 1), True, "text", used_clue_ids=("a", "b")),
        Step("combine:a:b", 3, (0, 2), True, "text", used_clue_ids=("a", "b")),
        Step("combine:a:b", 3, (0, 3), True, "text", used_clue_ids=("a", "b")),
    ]
    q = analyze_attachment_steps(steps)
    assert q.combination_event_count == 1  # one src/dst pair, however many cells it forced
    assert q.combination_deduction_count == 3  # but it really did force 3 cells - kept as a separate, informational total
    assert q.combination_fraction_spread == 0.0  # a single event can't be "spread"


def test_score_prefers_smaller_max_reveal_size_regardless_of_difficulty():
    spiky = analyze_attachment_steps(
        [Step("c1", 2, (0, i), True, "t", used_clue_ids=("c1",)) for i in range(4)]
    )
    even = analyze_attachment_steps([Step("c1", 2, (0, 0), True, "t", used_clue_ids=("c1",))])
    assert score_attachment_quality(even, EASY) > score_attachment_quality(spiky, EASY)
    assert score_attachment_quality(even, HARD) > score_attachment_quality(spiky, HARD)


def test_score_prefers_earlier_and_more_spread_combination_when_allowed():
    n = 10
    late_steps = [Step(f"c{i}", 0, (0, i % 4), True, "t", used_clue_ids=(f"c{i}",)) for i in range(n - 1)]
    late_steps.append(Step("combine:a:b", 3, (1, 0), True, "t", used_clue_ids=("a", "b")))
    late = analyze_attachment_steps(late_steps)

    early_steps = [Step("combine:a:b", 3, (1, 0), True, "t", used_clue_ids=("a", "b"))]
    early_steps += [Step(f"c{i}", 0, (0, i % 4), True, "t", used_clue_ids=(f"c{i}",)) for i in range(n - 1)]
    early = analyze_attachment_steps(early_steps)

    assert score_attachment_quality(early, HARD) > score_attachment_quality(late, HARD)


def test_score_ignores_combination_timing_when_difficulty_does_not_allow_it():
    n = 10
    late_steps = [Step(f"c{i}", 0, (0, i % 4), True, "t", used_clue_ids=(f"c{i}",)) for i in range(n - 1)]
    late_steps.append(Step("combine:a:b", 3, (1, 0), True, "t", used_clue_ids=("a", "b")))
    late = analyze_attachment_steps(late_steps)

    early_steps = [Step("combine:a:b", 3, (1, 0), True, "t", used_clue_ids=("a", "b"))]
    early_steps += [Step(f"c{i}", 0, (0, i % 4), True, "t", used_clue_ids=(f"c{i}",)) for i in range(n - 1)]
    early = analyze_attachment_steps(early_steps)

    assert not EASY.allow_combination
    assert score_attachment_quality(early, EASY) == score_attachment_quality(late, EASY)


def test_candidate_pool_size_reduced_for_hard():
    # v12: Hard's best-of-N candidate search (v8's "generate 3, keep the
    # best-paced" quality lever) was measured, isolated against the real
    # generate_puzzle, to cost much less than an old stale comment claimed
    # (identical 88% success at 1 vs 3, ~11% slower median/max at 3) - so
    # DirectCountClue's exclusion (see build_candidate_pool) is doing
    # essentially all the real reliability work, not this. Cut from 3 to
    # 2 as a deliberate middle ground: the 45s target is a goal, not a
    # hard cutoff, so it's worth keeping a little of the pacing quality
    # rather than dropping to 1 purely on a benefit that measured out
    # smaller than assumed. See project memory for the full numbers.
    assert EASY.candidate_pool_size == 1
    assert MEDIUM.candidate_pool_size == 1
    assert HARD.candidate_pool_size == 2


def test_min_combination_events_only_raised_for_hard():
    # v8's new "genuinely harder Hard" lever: Medium keeps the implicit
    # default (>=1 combination moment), Hard demands >=2 - genuinely
    # distinct combination *events*, not individually forced cells (see
    # combination_event_count vs combination_deduction_count above).
    assert MEDIUM.min_combination_events == 1
    assert HARD.min_combination_events == 2
