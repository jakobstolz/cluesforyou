"""Difficulty presets controlling puzzle generation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DifficultyParams:
    name: str
    criminal_ratio_range: tuple[float, float]
    min_clues: int
    max_clues: int
    max_tier_allowed: int
    allow_tier1: bool  # "everyone/no one in X" clues - trivial, no deduction required
    allow_neighbor: bool  # unified neighborhood clues, plus row/col x neighbor intersections
    allow_custom_pair: bool
    allow_compare: bool  # GT/LT/EQ comparisons (group-vs-group and person-vs-person neighbor counts)
    allow_group_existence: bool  # "every row/column/name/profession has >=1 criminal"
    allow_parity: bool  # "an odd/even number of criminals in X" - weak, only resolves a last cell
    allow_tier4: bool
    allow_combination: bool = False  # cross-reference pairs of count clues (see reasoner.py) - cheap, unlike tier4
    require_min_tier: int = 0  # if set, generation rejects puzzles that never needed this tier
    min_chain_depth: int = 0  # Hard only: minimum forced-step depth before a hypothesis contradiction
    require_combination: bool = False  # Hard only: puzzle must genuinely need combination reasoning to solve
    min_combination_steps: int = 1  # Hard only: how many *distinct* combination moments the attached play must use
    max_starter_power: int | None = None  # Hard only: reject a starter clue that alone resolves too much for free
    candidate_pool_size: int = 1  # generate up to this many valid puzzles per attempt cycle and keep the best-paced

    # Person-relative directional regions (above/below/left/right of X) are
    # mechanically as simple as a row/column clue, so they're generated at
    # every difficulty unconditionally - no flag needed.


# v8 tier reshuffle: playtesting showed today's Hard actually sat at a
# "decent Medium" - so the whole curve moves down a notch (new Easy = old
# Medium, new Medium = old Hard minus its expensive candidate search) and a
# genuinely harder tier is built on top as the new Hard. See the v8 plan for
# the full rationale.

EASY = DifficultyParams(
    name="easy",
    criminal_ratio_range=(0.30, 0.60),
    min_clues=8,
    max_clues=13,
    max_tier_allowed=2,
    allow_tier1=False,
    allow_neighbor=True,
    allow_custom_pair=True,
    allow_compare=False,
    allow_group_existence=True,
    allow_parity=True,
    allow_tier4=False,
)

MEDIUM = DifficultyParams(
    name="medium",
    criminal_ratio_range=(0.30, 0.60),
    min_clues=8,
    max_clues=12,
    max_tier_allowed=4,
    allow_tier1=False,
    allow_neighbor=True,
    allow_custom_pair=True,
    allow_compare=True,
    allow_group_existence=True,
    allow_parity=True,
    allow_tier4=True,
    allow_combination=True,  # cross-referencing two count clues at once - see reasoner.py
    require_min_tier=3,  # must genuinely need comparisons, not just counts
    min_chain_depth=3,  # only enforced when tier 4 *does* get used - see select_clue_subset
    require_combination=True,  # must genuinely need to combine two clues, not just read one
    max_starter_power=4,  # the free starting clue mustn't single-handedly resolve more than this many cells
    candidate_pool_size=1,  # no best-of-N search here - that expense moves up to Hard only (see v8 plan)
)

HARD = DifficultyParams(
    name="hard",
    criminal_ratio_range=(0.30, 0.60),
    min_clues=8,
    max_clues=12,
    max_tier_allowed=4,
    allow_tier1=False,
    allow_neighbor=True,
    allow_custom_pair=True,
    allow_compare=True,
    allow_group_existence=True,
    allow_parity=True,
    allow_tier4=True,
    allow_combination=True,
    require_min_tier=3,
    min_chain_depth=3,
    require_combination=True,
    min_combination_steps=2,  # the *new* bar over Medium: at least two genuine combination moments, not just one
    max_starter_power=3,  # tightened from Medium's 4 - even less handed over for free
    candidate_pool_size=3,  # compare up to 3 valid puzzles per attempt cycle, keep the best-paced (see difficulty_metrics.py)
)

BY_NAME: dict[str, DifficultyParams] = {p.name: p for p in (EASY, MEDIUM, HARD)}


def get_difficulty(name: str) -> DifficultyParams:
    try:
        return BY_NAME[name]
    except KeyError:
        raise ValueError(f"Unknown difficulty: {name!r}") from None
