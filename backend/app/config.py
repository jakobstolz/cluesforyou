"""Global constants and small enums shared across the backend."""

from __future__ import annotations

from enum import Enum

# Generation bounds
# Hard's require_combination gate (see difficulty.py/reasoner.py) means
# generation must find a clue set that's *provably* unsolvable via tiers
# 0-3 alone - genuinely harder to land by retrying than the old tier-4
# hypothesis-chain requirement ever was, with a long tail of unlucky
# layouts needing well over 100 attempts. This is a generous ceiling so
# that tail has room to succeed locally; Easy/Medium finish in well under
# a second regardless and never need anywhere close to this.
MAX_GENERATION_ATTEMPTS = 300
GENERATION_TIME_BUDGET_SECONDS = 90.0
# When difficulty.candidate_pool_size > 1 (Hard - see difficulty_metrics.py's
# AttachmentQuality/score_attachment_quality), generate_puzzle keeps looking
# for a few candidates to compare instead of stopping at the first. Each
# additional candidate carries the SAME wide latency distribution as the
# first one did (a fresh random attempt, not a refinement) - a *fraction*
# of the whole time budget was measured to roughly double median Hard
# generation time (30s -> 63s on identical seeds). Capping the "extra
# candidate hunting" time absolutely, instead of as a fraction of the
# total budget, bounds that cost predictably regardless of how generous
# the overall budget is.
EXTRA_CANDIDATE_TIME_BUDGET_S = 15.0

# Grid size
GRID_ROWS = 5
GRID_COLS = 4
NUM_CELLS = GRID_ROWS * GRID_COLS


class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
