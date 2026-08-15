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
    allow_tier4: bool  # NOTE (v9): measured across 50+ generated Medium/Hard puzzles, tier4 has never once been
    # load-bearing - tiers 0-3(+combination) always already finish the job before tier4 gets a chance to matter.
    # Not touched this round (deliberately deprioritized), but the goal is for it to become load-bearing in MOST
    # Hard puzzles eventually - needs a deliberately-constructed tier4 dependency, the same way v5 engineered real
    # combination-necessity (see _find_combination_seed_pair in generator.py) rather than leaving it to chance.
    allow_combination: bool = False  # cross-reference pairs of count clues (see reasoner.py) - cheap, unlike tier4
    require_min_tier: int = 0  # if set, generation rejects puzzles that never needed this tier
    min_chain_depth: int = 0  # Hard only: minimum forced-step depth before a hypothesis contradiction
    require_combination: bool = False  # Hard only: puzzle must genuinely need combination reasoning to solve
    min_combination_events: int = 1  # Hard only: how many *distinct* combination events the attached play must use (see AttachmentQuality.combination_event_count - deliberately not a count of individual forced deductions)
    max_starter_power: int | None = None  # Hard only: reject a starter clue that alone resolves too much for free
    candidate_pool_size: int = 1  # generate up to this many valid puzzles per attempt cycle and keep the best-paced
    starter_candidates: int = 1  # v9: try up to this many starter cells per successful `chosen` set, keep the
    # best-scoring attachment (see generator.py's attach_clues_to_cells) - a cheap quality lever that reuses the
    # same clue set instead of paying for a fresh candidate_pool_size search. 1 = today's single-starter behavior.

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
    min_clues=10,
    max_clues=15,
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
    min_clues=11,
    max_clues=15,
    max_tier_allowed=4,
    allow_tier1=False,
    allow_neighbor=True,
    allow_custom_pair=True,
    allow_compare=True,
    allow_group_existence=True,
    allow_parity=True,
    allow_tier4=True,
    allow_combination=True,  # cross-referencing two count clues at once - see reasoner.py
    require_min_tier=2,  # must genuinely need comparisons, not just counts
    min_chain_depth=3,  # only enforced when tier 4 *does* get used - see select_clue_subset
    require_combination=True,  # must genuinely need to combine two clues, not just read one
    max_starter_power=3,  # the free starting clue mustn't single-handedly resolve more than this many cells
    candidate_pool_size=1,  # no best-of-N search here - that expense moves up to Hard only (see v8 plan)
    starter_candidates=3,  # cheap quality lever (v9) - starting value, tune via batch_instrument.py measurement
)

HARD = DifficultyParams(
    name="hard",
    criminal_ratio_range=(0.30, 0.60),
    min_clues=11,
    max_clues=15,
    max_tier_allowed=4,
    allow_tier1=False,
    allow_neighbor=True,
    allow_custom_pair=True,
    allow_compare=True,
    allow_group_existence=True,
    allow_parity=True,
    allow_tier4=True,
    allow_combination=True,
    require_min_tier=2,
    min_chain_depth=3,
    require_combination=True,
    min_combination_events=2,  # the *new* bar over Medium: at least two genuine combination moments, not just one
    max_starter_power=2,  # tightened from Medium's 4 - even less handed over for free
    # v12: cut from 3 to 2 (compare up to N valid puzzles, keep the
    # best-paced - see difficulty_metrics.py). An old config.py comment
    # claimed this roughly doubled median Hard generation time (30s->63s)
    # - turned out stale/overstated once actually isolated: a clean A/B
    # against the real generate_puzzle (not batch_instrument.py's
    # simplified reimplementation, which doesn't even exercise this
    # parameter) showed 1 vs 3 giving IDENTICAL 88% success, just
    # ~11% slower median/max at 3. DirectCountClue's exclusion above is
    # doing essentially all the real reliability work, not this. Landed on
    # 2 as a deliberate middle ground - the 45s target is a goal, not a
    # hard cutoff, so it's worth keeping a little of Hard's best-of-N
    # pacing quality rather than dropping it to 1 purely on a benefit that
    # measured out much smaller than assumed going in.
    candidate_pool_size=2,
    starter_candidates=5,  # stacks with candidate_pool_size - each of those independent clue sets also gets a best-of-5 starter
)

BY_NAME: dict[str, DifficultyParams] = {p.name: p for p in (EASY, MEDIUM, HARD)}


def get_difficulty(name: str) -> DifficultyParams:
    try:
        return BY_NAME[name]
    except KeyError:
        raise ValueError(f"Unknown difficulty: {name!r}") from None
