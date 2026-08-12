"""Turn a ReasoningTrace's step-level dependency provenance (see
Step.used_cells/used_clue_ids/round in clues/base.py) into real difficulty
numbers - dependency depth, branching, and how many clues each deduction
actually needed - instead of the flat "clue count + max tier" proxy used
before. Pure/read-only: computed from an already-finished trace, no
reasoner changes needed here.

`ReasoningMetrics`/`compute_metrics` (v6) measure the *abstract* solve.
`AttachmentQuality`/`analyze_attachment_steps`/`score_attachment_quality`
(v7) measure the *player's actual experience* instead - how spiky each
attached clue's reveal is, and how early/spread-out combination reasoning
is - computed from a chronological replay of the attachment specifically
(see generator.py's `_replay_attachment`), which is what generate_puzzle
uses to rank several candidate puzzles and keep the best-paced one.

Real information-gain-in-bits (which would need counting remaining
solutions, not just checking satisfiability) and full alternative-path
exploration (which would need the reasoner to branch on choice between
simultaneously-ready deductions, not just apply all of them) are both
still deferred - see the v6/v7 plan docs.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.core.clues.base import ReasoningTrace, Step
from backend.app.core.difficulty import DifficultyParams
from backend.app.core.types import Cell


@dataclass
class ReasoningMetrics:
    max_depth: int
    avg_depth: float
    nontrivial_deductions: int  # tier >= 2, or a combine step
    max_round_branching: int  # most steps that ever fired in a single round
    avg_round_branching: float
    combination_steps: int
    avg_clues_per_deduction: float  # mean(len(step.used_clue_ids))


def build_dependency_depths(steps: list[Step]) -> dict[Cell, int]:
    """depth[cell] = 0 for a root fact (empty used_cells, e.g. a direct
    reveal or a hypothesis step), else 1 + the deepest prerequisite's
    depth. Assumes `steps` is in firing order (true for
    ReasoningTrace.steps, which is append-only in propagate_to_fixpoint)."""
    depth_by_cell: dict[Cell, int] = {}
    for step in steps:
        if not step.used_cells:
            depth_by_cell[step.cell] = 0
        else:
            depth_by_cell[step.cell] = 1 + max(depth_by_cell.get(c, 0) for c in step.used_cells)
    return depth_by_cell


def compute_metrics(trace: ReasoningTrace) -> ReasoningMetrics:
    steps = trace.steps
    if not steps:
        return ReasoningMetrics(
            max_depth=0,
            avg_depth=0.0,
            nontrivial_deductions=0,
            max_round_branching=0,
            avg_round_branching=0.0,
            combination_steps=0,
            avg_clues_per_deduction=0.0,
        )

    depths = build_dependency_depths(steps)
    depth_values = list(depths.values())

    round_counts: dict[int, int] = {}
    for step in steps:
        round_counts[step.round] = round_counts.get(step.round, 0) + 1

    combination_steps = sum(1 for s in steps if len(s.used_clue_ids) > 1)
    nontrivial = sum(1 for s in steps if s.tier >= 2 or len(s.used_clue_ids) > 1)

    return ReasoningMetrics(
        max_depth=max(depth_values, default=0),
        avg_depth=sum(depth_values) / len(depth_values),
        nontrivial_deductions=nontrivial,
        max_round_branching=max(round_counts.values(), default=0),
        avg_round_branching=sum(round_counts.values()) / len(round_counts),
        combination_steps=combination_steps,
        avg_clues_per_deduction=sum(len(s.used_clue_ids) for s in steps) / len(steps),
    )


@dataclass
class AttachmentQuality:
    max_reveal_size: int  # largest number of cells any single attached clue's firing resolved at once
    reveal_sizes: list[int]  # per-firing-event reveal counts, for tests/inspection
    first_combination_fraction: float | None  # position (0=earliest, 1=latest) of the first combine step; None if none occurred
    combination_fraction_spread: float  # stddev of combine-step positions - 0 if <=1 combination step
    combination_step_count: int  # how many distinct combine steps fired during replay - drives min_combination_steps (Hard)


def analyze_attachment_steps(steps: list[Step]) -> AttachmentQuality:
    """`steps` must be in chronological discovery order (see generator.py's
    `_replay_attachment`, which replays the actual attached play sequence,
    not the abstract full-pool solve). Groups by clue_id to get
    reveal-event sizes - "how many cells did the player learn about the
    instant they read this one clue" - and positions combine steps
    (`used_clue_ids` with 2 entries) as fractions of the total step count
    to measure how early/spread-out combination reasoning was."""
    if not steps:
        return AttachmentQuality(
            max_reveal_size=0,
            reveal_sizes=[],
            first_combination_fraction=None,
            combination_fraction_spread=0.0,
            combination_step_count=0,
        )

    reveal_counts: dict[str, int] = {}
    for step in steps:
        reveal_counts[step.clue_id] = reveal_counts.get(step.clue_id, 0) + 1
    reveal_sizes = list(reveal_counts.values())

    n = len(steps)
    combo_positions = [i / n for i, s in enumerate(steps) if len(s.used_clue_ids) > 1]
    first_combination_fraction = combo_positions[0] if combo_positions else None
    if len(combo_positions) > 1:
        mean = sum(combo_positions) / len(combo_positions)
        spread = (sum((p - mean) ** 2 for p in combo_positions) / len(combo_positions)) ** 0.5
    else:
        spread = 0.0

    return AttachmentQuality(
        max_reveal_size=max(reveal_sizes),
        reveal_sizes=reveal_sizes,
        first_combination_fraction=first_combination_fraction,
        combination_fraction_spread=spread,
        combination_step_count=len(combo_positions),
    )


# Scoring weights - deliberately simple/tunable, not a principled model.
# Reveal-size spikes are the dominant penalty (directly the "1 then 5"
# complaint); combination timing only matters when this difficulty
# actually uses combination at all.
_REVEAL_SPIKE_WEIGHT = 1.0
_EARLY_COMBINATION_WEIGHT = 3.0
_COMBINATION_SPREAD_WEIGHT = 3.0


def score_attachment_quality(quality: AttachmentQuality, difficulty: DifficultyParams) -> float:
    """Higher = better-paced: less spiky reveals, and (when this
    difficulty uses combination) combination reasoning available earlier
    and spread across more than one moment instead of clustered at the
    end. Only meaningful for ranking candidates of the SAME difficulty
    against each other - not a cross-difficulty scale."""
    score = -quality.max_reveal_size * _REVEAL_SPIKE_WEIGHT
    if difficulty.allow_combination and quality.first_combination_fraction is not None:
        score += (1.0 - quality.first_combination_fraction) * _EARLY_COMBINATION_WEIGHT
        score += quality.combination_fraction_spread * _COMBINATION_SPREAD_WEIGHT
    return score
