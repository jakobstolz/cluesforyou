"""Puzzle generation: candidate clue pool -> minimal solvable+unique subset
-> per-cell clue attachment.

See the plan doc for the full algorithm description. Roughly:
  1. Random grid layout (people sampled from the roster pool) + random
     hidden solution.
  2. Instantiate every clue template against the concrete layout, with
     targets computed straight from the solution (so every candidate is
     automatically a true statement - no filtering needed).
  3. Grow a working clue set (randomized order) until the human-reasoning
     engine fully determines the whole grid and CP-SAT confirms uniqueness.
  4. Prune to a locally-minimal, non-redundant set.
  5. Attach each clue to a specific cell: pick a starter cell independent
     of the clue graph, seed the reasoning trace with it, and assign each
     subsequently-needed clue to one of the cells the *previous* clue's
     firing resolved - so every cell ends up with exactly one thing
     permanently attached to it (a real clue, for as many cells as there
     are clues, or nothing -> a fun fact at play-time).
  6. Retry with a fresh layout/solution on any failure, bounded by an
     attempt count and a wall-clock time budget.
"""

from __future__ import annotations

import itertools
import random
import time
from dataclasses import dataclass

from backend.app.config import (
    EXTRA_CANDIDATE_ATTEMPT_BUDGET,
    GENERATION_TIME_BUDGET_SECONDS,
    GRID_COLS,
    GRID_ROWS,
    MAX_GENERATION_ATTEMPTS,
    NUM_CELLS,
)
from backend.app.core.clues.base import Clue, Step
from backend.app.core.clues.compare import CompareCountClue
from backend.app.core.clues.counts import CountConstraintClue
from backend.app.core.clues.direct import DirectRevealClue
from backend.app.core.clues.existence import AtLeastOneCriminalClue
from backend.app.core.clues.parity import ParityConstraintClue
from backend.app.core.difficulty import DifficultyParams, get_difficulty
from backend.app.core.difficulty_metrics import AttachmentQuality, analyze_attachment_steps, score_attachment_quality
from backend.app.core.grid import random_grid_layout
from backend.app.core.reasoner import COMBINE_PREFIX, propagate_to_fixpoint, run_reasoner
from backend.app.core.solution import random_solution
from backend.app.core.solver_cpsat import cpsat_is_unique
from backend.app.core.types import (
    ALL_CELLS,
    Cell,
    Grid,
    KnownState,
    Person,
    ScopeKind,
    Solution,
    all_neighbor_cells,
    cells_above,
    cells_below,
    cells_east_of,
    cells_left_of,
    cells_north_of,
    cells_right_of,
    cells_south_of,
    cells_west_of,
    col_cells,
    corner_cells,
    edge_cells,
    identity_text,
    interior_cells,
    profession_group_cells,
    profession_group_key,
    profession_group_label,
    row_cells,
)

DIRECT_CLUE_SAMPLE_SIZE = 3
CUSTOM_PAIR_SAMPLE_SIZE = 20
COMPARE_SAMPLE_SIZE = 20
NEIGHBOR_COMPARE_SAMPLE_SIZE = 15
RELATIVE_REGION_SAMPLE_SIZE = 15
ROW_COL_NEIGHBOR_SAMPLE_SIZE = 15
PARITY_SAMPLE_SIZE = 15
# Every propagation round is O(pool size); capping the final pool bounds the
# cost of every growth/prune step (this matters most for Hard, where many
# of those steps also run the tier-4 hypothesis search).
MAX_POOL_SIZE = 60
# Growth's candidate scoring (see _best_growth_candidate) is more expensive
# per-candidate than the old pure-overlap pick, so it's only ever applied to
# a bounded shortlist rather than every remaining candidate - this caps that
# cost independent of how large `remaining` is (v9: measured against the
# pre-change baseline in batch_instrument.py's output before landing).
GROWTH_SCORING_SHORTLIST_SIZE = 3
# How much more a "dependency" deduction (an existing chosen clue or a
# combination only becoming possible because of the candidate being scored)
# counts than a "direct" one (the candidate resolving something purely on
# its own) - see _growth_candidate_score.
GROWTH_DEPENDENCY_WEIGHT = 2.0

ScopeDescriptor = tuple[list[Cell], ScopeKind, object]


class GenerationTimeoutError(Exception):
    """Raised when generate_puzzle can't converge on a valid puzzle within
    the attempt/time budget."""


@dataclass
class PuzzleData:
    layout: Grid
    solution: Solution
    starter_cell: Cell
    cell_clue: dict[Cell, Clue]  # cells with a real attached clue; all other cells -> fun fact
    difficulty: DifficultyParams


# ---------------------------------------------------------------------------
# Candidate pool
# ---------------------------------------------------------------------------


def _group_count(solution: Solution, scope: list[Cell]) -> int:
    return sum(1 for c in scope if solution[c])


def _make_count_clue_if_allowed(
    scope: list[Cell],
    scope_kind: ScopeKind,
    solution: Solution,
    layout: Grid,
    difficulty: DifficultyParams,
    index=None,
    rng: random.Random | None = None,
) -> Clue | None:
    """Build a CountConstraintClue, unless its target happens to be extreme
    (0 or the full scope - a tier-1 "everyone/no one" giveaway) and this
    difficulty bans tier-1 clues. Centralizes the ban in one place instead
    of scattering the check across every candidate site below."""
    if not scope:
        return None
    target = _group_count(solution, scope)
    is_extreme = target in (0, len(scope))
    if is_extreme and not difficulty.allow_tier1:
        return None
    return CountConstraintClue(scope, scope_kind, target, layout, index=index, rng=rng)


def _relative_region_scopes(rng: random.Random) -> list[ScopeDescriptor]:
    """Person-relative directional regions, two families competing as
    separate candidates: the cluesbysam-consistent same-row/column-only
    version (ABOVE/BELOW/LEFT_OF/RIGHT_OF, "über/unter/links/rechts von
    X") and the original whole-half-grid version (NORTH_OF/SOUTH_OF/
    WEST_OF/EAST_OF, "nördlich/südlich/westlich/östlich von X"). Both are
    mechanically as simple as a row/column clue, so offered at every
    difficulty with no gating flag."""
    scopes: list[ScopeDescriptor] = []
    for cell in ALL_CELLS:
        for kind, fn in (
            (ScopeKind.ABOVE, cells_above),
            (ScopeKind.BELOW, cells_below),
            (ScopeKind.LEFT_OF, cells_left_of),
            (ScopeKind.RIGHT_OF, cells_right_of),
            (ScopeKind.NORTH_OF, cells_north_of),
            (ScopeKind.SOUTH_OF, cells_south_of),
            (ScopeKind.WEST_OF, cells_west_of),
            (ScopeKind.EAST_OF, cells_east_of),
        ):
            scope = fn(cell)
            if scope:
                scopes.append((scope, kind, cell))
    rng.shuffle(scopes)
    return scopes[:RELATIVE_REGION_SAMPLE_SIZE]


def _intersection_scopes(rng: random.Random) -> list[ScopeDescriptor]:
    """A row or column AND neighboring some anchor person at once - e.g.
    "in row 2 neighboring Lisa." Individually much weaker than a plain row
    or neighbor clue (the scope is typically 1-3 cells), which is exactly
    what makes combining several clues necessary instead of optional."""
    scopes: list[ScopeDescriptor] = []
    for anchor in ALL_CELLS:
        neighbor_set = set(all_neighbor_cells(anchor))
        if not neighbor_set:
            continue
        for r in range(GRID_ROWS):
            scope = sorted(neighbor_set & set(row_cells(r)))
            if scope and len(scope) < len(neighbor_set):
                scopes.append((scope, ScopeKind.ROW_NEIGHBOR, (r, anchor)))
        for c in range(GRID_COLS):
            scope = sorted(neighbor_set & set(col_cells(c)))
            if scope and len(scope) < len(neighbor_set):
                scopes.append((scope, ScopeKind.COL_NEIGHBOR, (c, anchor)))
    rng.shuffle(scopes)
    return scopes[:ROW_COL_NEIGHBOR_SAMPLE_SIZE]


def build_candidate_pool(
    layout: Grid,
    solution: Solution,
    difficulty: DifficultyParams,
    rng: random.Random,
) -> list[Clue]:
    # Names are never generated as a clue scope: every generated grid has
    # distinct names by construction (see core/grid.py), so a "named X"
    # scope would always be exactly one person - a redundant, more awkward
    # way of saying what a direct reveal already says. Professions stay,
    # since several people usually share one - grouped by canonical key so
    # a gendered pair like Politiker/Politikerin counts as one profession.
    professions = sorted({profession_group_key(person.profession) for row in layout for person in row})

    pool: list[Clue] = []

    # A handful of direct reveals - kept scarce so the puzzle can't lean on
    # "just tell them", but always available as a bootstrapping seed. Each
    # also gets a neighbor-framed twin (same fact, different flavor text -
    # see DirectRevealClue's docstring for why that's free setup for a
    # later neighbor-count deduction) as an alternative candidate.
    for cell in rng.sample(ALL_CELLS, min(DIRECT_CLUE_SAMPLE_SIZE, NUM_CELLS)):
        pool.append(DirectRevealClue(cell, solution[cell], layout, rng=rng))
        neighbors = all_neighbor_cells(cell)
        if neighbors:
            anchor = rng.choice(neighbors)
            pool.append(DirectRevealClue(cell, solution[cell], layout, neighbor_context=anchor, rng=rng))

    def add_count(scope, kind, index=None):
        clue = _make_count_clue_if_allowed(scope, kind, solution, layout, difficulty, index=index, rng=rng)
        if clue is not None:
            pool.append(clue)

    # Core, reusable scope descriptors - also the basis for parity candidates below.
    base_scopes: list[ScopeDescriptor] = []
    for r in range(GRID_ROWS):
        base_scopes.append((row_cells(r), ScopeKind.ROW, r))
    for c in range(GRID_COLS):
        base_scopes.append((col_cells(c), ScopeKind.COL, c))
    for prof in professions:
        base_scopes.append((profession_group_cells(layout, prof), ScopeKind.PROFESSION, prof))
    base_scopes.append((ALL_CELLS, ScopeKind.GLOBAL, None))
    base_scopes.append((corner_cells(), ScopeKind.CORNER, None))
    base_scopes.append((edge_cells(), ScopeKind.EDGE, None))
    base_scopes.append((interior_cells(), ScopeKind.INTERIOR, None))

    if difficulty.allow_neighbor:
        for cell in ALL_CELLS:
            base_scopes.append((all_neighbor_cells(cell), ScopeKind.NEIGHBOR, cell))

    relative_scopes = _relative_region_scopes(rng)
    intersection_scopes = _intersection_scopes(rng) if difficulty.allow_neighbor else []

    for scope, kind, index in itertools.chain(base_scopes, relative_scopes, intersection_scopes):
        add_count(scope, kind, index=index)

    if difficulty.allow_parity:
        # Parity degenerates into an exact-count clue for scopes smaller
        # than 3 cells (e.g. a pair), so those are excluded here.
        parity_sources = [s for s in itertools.chain(base_scopes, relative_scopes, intersection_scopes) if len(s[0]) >= 3]
        rng.shuffle(parity_sources)
        for scope, kind, index in parity_sources[:PARITY_SAMPLE_SIZE]:
            target = _group_count(solution, scope)
            pool.append(ParityConstraintClue(scope, kind, target % 2 == 1, layout, index=index, rng=rng))

    if difficulty.allow_custom_pair:
        groups = [row_cells(r) for r in range(GRID_ROWS)]
        groups += [col_cells(c) for c in range(GRID_COLS)]
        groups += [profession_group_cells(layout, p) for p in professions]
        pair_candidates = [pair for group in groups for pair in itertools.combinations(group, 2)]
        rng.shuffle(pair_candidates)
        for a, b in pair_candidates[:CUSTOM_PAIR_SAMPLE_SIZE]:
            add_count([a, b], ScopeKind.CUSTOM_PAIR)

    if difficulty.allow_group_existence:
        partitions = [
            (ScopeKind.ROW, [row_cells(r) for r in range(GRID_ROWS)]),
            (ScopeKind.COL, [col_cells(c) for c in range(GRID_COLS)]),
            (ScopeKind.PROFESSION, [profession_group_cells(layout, p) for p in professions]),
        ]
        for kind, groups in partitions:
            # A size-1 group would make this an instant giveaway for that
            # group - only offer it when every group has real ambiguity.
            # And unlike every other candidate here, this one has no target
            # computed from `solution` to guarantee truth by construction -
            # it must be checked explicitly (every group actually needs
            # >=1 criminal in this particular solution for it to be valid).
            if (
                groups
                and all(len(g) >= 2 for g in groups)
                and all(any(solution[c] for c in g) for g in groups)
            ):
                pool.append(AtLeastOneCriminalClue(groups, kind, layout, rng=rng))

    if difficulty.allow_compare:
        pool.extend(_build_compare_candidates(layout, solution, professions, rng))
        pool.extend(_build_neighbor_compare_candidates(layout, solution, rng))

    if len(pool) > MAX_POOL_SIZE:
        direct = [c for c in pool if isinstance(c, DirectRevealClue)]  # always keep the bootstrap seeds
        rest = [c for c in pool if not isinstance(c, DirectRevealClue)]
        pool = direct + _stratified_sample(rest, max(0, MAX_POOL_SIZE - len(direct)), rng)

    return pool


_INTERSECTION_KINDS = frozenset({ScopeKind.ROW_NEIGHBOR, ScopeKind.COL_NEIGHBOR})
_RELATIVE_KINDS = frozenset(
    {
        ScopeKind.ABOVE,
        ScopeKind.BELOW,
        ScopeKind.LEFT_OF,
        ScopeKind.RIGHT_OF,
        ScopeKind.NORTH_OF,
        ScopeKind.SOUTH_OF,
        ScopeKind.WEST_OF,
        ScopeKind.EAST_OF,
    }
)
_REGION_KINDS = frozenset({ScopeKind.CORNER, ScopeKind.EDGE, ScopeKind.INTERIOR, ScopeKind.GLOBAL})


def _clue_family(clue: Clue) -> str:
    """Which "family" of clue this is, for stratified pool sampling (see
    _stratified_sample) - grouped so no single family (e.g. every
    intersection or parity candidate) can get starved out of the final
    pool by chance when it's truncated to MAX_POOL_SIZE."""
    if isinstance(clue, DirectRevealClue):
        return "direct"
    if isinstance(clue, AtLeastOneCriminalClue):
        return "existence"
    if isinstance(clue, CompareCountClue):
        return "compare"
    if isinstance(clue, (CountConstraintClue, ParityConstraintClue)):
        kind = clue.scope_kind
        if kind == ScopeKind.CUSTOM_PAIR:
            return "pair"
        if kind == ScopeKind.NEIGHBOR:
            return "neighbor"
        if kind in _INTERSECTION_KINDS:
            return "intersection"
        if kind in _RELATIVE_KINDS:
            return "relative"
        if kind in _REGION_KINDS:
            return "region"
        if kind == ScopeKind.PROFESSION:
            return "profession"
        if kind in (ScopeKind.ROW, ScopeKind.COL):
            return "row_col"
    return "other"  # pragma: no cover - defensive fallback, every real kind is covered above


def _stratified_sample(clues: list[Clue], target_size: int, rng: random.Random) -> list[Clue]:
    """Group by family (_clue_family), shuffle within each group, then
    round-robin-pop across groups until target_size is reached - so
    truncating the pool can't accidentally starve a whole family out of
    the final candidates, the way a flat random truncation occasionally
    would."""
    if len(clues) <= target_size:
        return list(clues)
    by_family: dict[str, list[Clue]] = {}
    for clue in clues:
        by_family.setdefault(_clue_family(clue), []).append(clue)
    for group in by_family.values():
        rng.shuffle(group)
    groups = list(by_family.values())
    result: list[Clue] = []
    idx = 0
    while len(result) < target_size and any(groups):
        group = groups[idx % len(groups)]
        if group:
            result.append(group.pop())
        idx += 1
    return result


def _build_compare_candidates(
    layout: Grid, solution: Solution, professions: list[str], rng: random.Random
) -> list[Clue]:
    labeled_groups: list[tuple[str, list[Cell]]] = []
    labeled_groups += [(f"Reihe {r + 1}", row_cells(r)) for r in range(GRID_ROWS)]
    labeled_groups += [(f"Spalte {c + 1}", col_cells(c)) for c in range(GRID_COLS)]
    labeled_groups += [
        (f"den {profession_group_label(layout, p)}", profession_group_cells(layout, p)) for p in professions
    ]

    # Only compare within the same category (two rows, two professions, ...)
    category_sizes = (GRID_ROWS, GRID_COLS, len(professions))
    categories, idx = [], 0
    for size in category_sizes:
        categories.append(labeled_groups[idx : idx + size])
        idx += size

    candidates: list[Clue] = []
    for category in categories:
        for (label_a, scope_a), (label_b, scope_b) in itertools.combinations(category, 2):
            sum_a = _group_count(solution, scope_a)
            sum_b = _group_count(solution, scope_b)
            relation = "EQ" if sum_a == sum_b else ("GT" if sum_a > sum_b else "LT")
            candidates.append(CompareCountClue(scope_a, scope_b, relation, label_a, label_b, layout, rng=rng))

    rng.shuffle(candidates)
    return candidates[:COMPARE_SAMPLE_SIZE]


def _build_neighbor_compare_candidates(
    layout: Grid, solution: Solution, rng: random.Random
) -> list[Clue]:
    """Person-vs-person: 'more of the people neighboring Alice are
    criminals than the people neighboring Bob.' Pairs whose neighborhoods
    overlap are skipped - CompareCountClue.propagate's bound-tightening
    (and the EQ single-side forcing) assumes disjoint scopes, and a shared
    cell could otherwise get forced inconsistently."""
    cell_pairs = list(itertools.combinations(ALL_CELLS, 2))
    rng.shuffle(cell_pairs)

    candidates: list[Clue] = []
    for a, b in cell_pairs:
        if len(candidates) >= NEIGHBOR_COMPARE_SAMPLE_SIZE:
            break
        scope_a = all_neighbor_cells(a)
        scope_b = all_neighbor_cells(b)
        if not scope_a or not scope_b or set(scope_a) & set(scope_b):
            continue
        sum_a = _group_count(solution, scope_a)
        sum_b = _group_count(solution, scope_b)
        relation = "EQ" if sum_a == sum_b else ("GT" if sum_a > sum_b else "LT")
        label_a = f"den Personen neben {identity_text(layout, a)}"
        label_b = f"den Personen neben {identity_text(layout, b)}"
        candidates.append(CompareCountClue(scope_a, scope_b, relation, label_a, label_b, layout, rng=rng))

    return candidates


# ---------------------------------------------------------------------------
# Selection / pruning
# ---------------------------------------------------------------------------


class _SolveCache:
    """Memoizes run_reasoner/cpsat_is_unique results within one
    select_clue_subset call, keyed by the exact set of clue ids involved.
    Growth and (two-phase) pruning repeatedly re-check overlapping
    subsets - most concretely, the final validity block always
    immediately re-derives what pruning's last accepted trial already
    established - so this is a guaranteed win, not just an opportunistic
    one. Scoped per-attempt: clue `.id`s are unique per attempt (global
    counter in clues/base.py), so a fresh cache each call is always safe,
    never stale."""

    def __init__(self) -> None:
        self._reasoner_cache: dict[tuple, object] = {}
        self._unique_cache: dict[frozenset, bool] = {}

    def solves(self, clues: list[Clue], allow_tier4: bool, allow_combination: bool):
        key = (frozenset(c.id for c in clues), allow_tier4, allow_combination)
        if key not in self._reasoner_cache:
            self._reasoner_cache[key] = run_reasoner(clues, allow_tier4=allow_tier4, allow_combination=allow_combination)
        return self._reasoner_cache[key]

    def is_unique(self, clues: list[Clue]) -> bool:
        key = frozenset(c.id for c in clues)
        if key not in self._unique_cache:
            self._unique_cache[key] = cpsat_is_unique(clues)
        return self._unique_cache[key]


def _solves(clues: list[Clue], difficulty: DifficultyParams, cache: _SolveCache):
    """Try tiers 0-3 (+ combination, if this difficulty allows it) first -
    cheap, a handful of propagation passes; only pay for the expensive
    tier-4 hypothesis search (every cell x 2 hypotheses, each
    re-propagating the whole clue list) if that alone didn't finish the
    job and this difficulty allows tier 4. Returns the exact same trace
    either way - tier 4 never fires once already solved, so this is a
    transparent speed-up, not a behavior change."""
    trace = cache.solves(clues, allow_tier4=False, allow_combination=difficulty.allow_combination)
    if trace.solved or not difficulty.allow_tier4:
        return trace
    return cache.solves(clues, allow_tier4=True, allow_combination=difficulty.allow_combination)


def _find_combination_seed_pair(pool: list[Clue], rng: random.Random) -> tuple[Clue, Clue] | None:
    """Find a (small, big) pair of CountConstraintClues in `pool` where the
    small one's scope is a strict, *tight* subset of the big one's (the
    difference region isn't huge) - a good candidate to seed growth with
    when combination reasoning needs to end up necessary. Most random
    single-clue growth never happens to pick up a subset relationship at
    all (most clue-pairs share no subset relation), and even when one
    exists, GLOBAL-vs-anything pairs have a huge, rarely-useful difference
    region - so leaving this to pure chance makes `require_combination`
    very expensive to satisfy by retrying alone. Seeding with a proven,
    tight pair up front makes combination-necessity vastly more likely to
    actually stick through growth and pruning."""
    count_clues = [c for c in pool if isinstance(c, CountConstraintClue)]
    candidates: list[tuple[int, Clue, Clue]] = []
    for a, b in itertools.combinations(count_clues, 2):
        scope_a, scope_b = set(a.scope_list), set(b.scope_list)
        if scope_a < scope_b and len(scope_b) - len(scope_a) <= 6:
            candidates.append((len(scope_b) - len(scope_a), a, b))
        elif scope_b < scope_a and len(scope_a) - len(scope_b) <= 6:
            candidates.append((len(scope_a) - len(scope_b), b, a))
    if not candidates:
        return None
    # Prefer the tightest available difference region - more likely to
    # become forceable soon (and thus to actually stick as necessary
    # through pruning) than a loose one. Break ties randomly.
    best_diff = min(c[0] for c in candidates)
    tightest = [(a, b) for diff, a, b in candidates if diff == best_diff]
    return rng.choice(tightest)


def _solves_with_required_properties(clues: list[Clue], difficulty: DifficultyParams, cache: _SolveCache) -> bool:
    """Cheap tiers-0-3(+combination) solvability check. When
    `require_combination` is set, this also enforces genuine *necessity*,
    not just "did combination happen to fire" (see the note further down
    on why that distinction matters) - by checking the same clues solve
    *without* combination and requiring that to FAIL. Used by both growth
    and pruning below so combination-necessity, once achieved, is never
    accidentally lost along the way instead of being left to chance at
    the very end."""
    if not cache.solves(clues, allow_tier4=False, allow_combination=difficulty.allow_combination).solved:
        return False
    if difficulty.require_combination:
        if cache.solves(clues, allow_tier4=False, allow_combination=False).solved:
            return False
    return True


def _pick_growth_shortlist(remaining: list[Clue], chosen_cells: set[Cell], rng: random.Random, k: int) -> list[Clue]:
    """Cheap pre-filter before the more expensive dependency-scoring in
    _best_growth_candidate: sample up to `k` distinct candidates from
    `remaining`, weighted toward clues whose scope overlaps what's already
    chosen (weight = 1 + overlap size, so a zero-overlap candidate still
    has a nonzero chance - keeps variety - but overlapping candidates are
    favored, since a combination opportunity requires a subset
    relationship, which usually implies overlap). This used to be the
    *entire* growth-candidate selection (formerly `_weighted_growth_pick`);
    now it only bounds which candidates the expensive step below has to
    evaluate, keeping that step's cost independent of how large
    `remaining` is."""
    if len(remaining) <= k:
        return list(remaining)
    pool = list(remaining)
    weights = [1 + len(clue.scope & chosen_cells) for clue in pool]
    picked: list[Clue] = []
    for _ in range(k):
        idx = rng.choices(range(len(pool)), weights=weights, k=1)[0]
        picked.append(pool.pop(idx))
        weights.pop(idx)
    return picked


def _growth_candidate_score(
    candidate: Clue,
    chosen: list[Clue],
    baseline_known: KnownState,
    difficulty: DifficultyParams,
    cache: _SolveCache,
) -> float:
    """How much does adding `candidate` to `chosen` actually buy, beyond
    what `chosen` already derives alone (`baseline_known`)? Two kinds of
    payoff, weighted differently (see GROWTH_DEPENDENCY_WEIGHT):
      - "direct": candidate resolves a new cell on its own (its own
        propagate() fires, no other clue involved) - the same kind of
        progress the old pure-overlap heuristic implicitly rewarded, and
        still worth something (growth has to make progress somehow).
      - "dependency": a cell only becomes resolvable once candidate's own
        facts are added - either an EXISTING chosen clue's propagate()
        newly fires (it needed candidate's contribution to go tight), or a
        combination step fires with candidate as one of the pair. This is
        the "does this clue pay off *because of* what's already chosen"
        signal spatial overlap alone can't see - overlap rewards clues
        that reinforce each other regardless of whether that reinforcement
        actually produces a new deduction.
    Always the cheap tiers-0-3(+combination) check, never tier4 - the same
    invariant growth already relies on elsewhere (see select_clue_subset's
    comment on why tier4 during growth would reintroduce the v3-postmortem
    performance trap)."""
    trial = cache.solves(chosen + [candidate], allow_tier4=False, allow_combination=difficulty.allow_combination)
    new_cells = set(trial.known) - set(baseline_known)
    if not new_cells:
        return 0.0

    direct = 0
    dependency = 0
    for step in trial.steps:
        if step.cell not in new_cells:
            continue
        if step.clue_id == candidate.id and len(step.used_clue_ids) == 1:
            direct += 1
        else:
            dependency += 1

    return direct + GROWTH_DEPENDENCY_WEIGHT * dependency


def _best_growth_candidate(
    shortlist: list[Clue],
    chosen: list[Clue],
    difficulty: DifficultyParams,
    cache: _SolveCache,
    rng: random.Random,
) -> Clue:
    """Score every shortlisted candidate (see _pick_growth_shortlist) via
    _growth_candidate_score and keep the best, breaking ties randomly.
    Reuses _SolveCache throughout: the baseline (`chosen` alone) is almost
    always already cached from the previous growth iteration's
    _solves_with_required_properties check, and whichever candidate wins
    here costs nothing extra when that same check re-runs on it right
    after - the added cost of this whole step is strictly bounded to the
    other `len(shortlist) - 1` candidates, one cache.solves() call each."""
    baseline = cache.solves(chosen, allow_tier4=False, allow_combination=difficulty.allow_combination)
    scored = [(_growth_candidate_score(c, chosen, baseline.known, difficulty, cache), c) for c in shortlist]
    best_score = max(score for score, _ in scored)
    best = [c for score, c in scored if score == best_score]
    return rng.choice(best)


def select_clue_subset(
    pool: list[Clue],
    difficulty: DifficultyParams,
    rng: random.Random,
) -> list[Clue] | None:
    cache = _SolveCache()
    remaining = list(pool)
    rng.shuffle(remaining)  # baseline order for the zero-overlap ties within _pick_growth_shortlist

    # If this difficulty needs combination reasoning to be necessary,
    # seed growth with a proven tight subset-pair up front - see
    # _find_combination_seed_pair for why leaving this entirely to chance
    # makes require_combination very expensive to satisfy.
    chosen: list[Clue] = []
    if difficulty.require_combination:
        seed_pair = _find_combination_seed_pair(pool, rng)
        if seed_pair is not None:
            chosen = list(seed_pair)
            remaining = [c for c in remaining if c not in chosen]

    chosen_cells: set[Cell] = set().union(*(c.scope for c in chosen)) if chosen else set()

    # Grow using tiers 0-3 only - always cheap, same as Easy/Medium. Once
    # pruning starts, removing a clue can only ever reduce what's
    # derivable, so if the *full* chosen set needed tier 4 to complete,
    # every single removal trial would need it too - checking tier 4
    # during growth would mean paying that cost repeatedly while `chosen`
    # is still small and mostly-unconstrained (where a hypothesis search
    # is most likely to find nothing anyway). Better to keep growth fast
    # and let tier-4 dependency emerge (if it does) during pruning below,
    # where `chosen` is already much smaller. When combination is
    # required, growth also keeps going past the first "solved" point
    # until it's solved *and* genuinely needs combination - stopping too
    # early would hand pruning a set with no combination dependency to
    # preserve in the first place. Candidates are picked via a bounded
    # shortlist + dependency-scoring pass (_pick_growth_shortlist +
    # _best_growth_candidate) rather than a fixed shuffled order or pure
    # spatial-overlap weighting (see there for why).
    grown = False
    while remaining:
        shortlist = _pick_growth_shortlist(remaining, chosen_cells, rng, GROWTH_SCORING_SHORTLIST_SIZE)
        clue = _best_growth_candidate(shortlist, chosen, difficulty, cache, rng)
        remaining.remove(clue)
        chosen.append(clue)
        chosen_cells |= clue.scope
        if _solves_with_required_properties(chosen, difficulty, cache):
            grown = True
            break
    if not grown:
        final_attempt = _solves(chosen, difficulty, cache)
        if not final_attempt.solved:
            return None  # not even the whole pool (with tier 4, if allowed) can finish it
        if difficulty.require_combination:
            without = cache.solves(chosen, allow_tier4=False, allow_combination=False)
            if without.solved:
                return None  # whole pool solves without ever needing combination - hopeless, retry

    if not cache.is_unique(chosen):
        return None

    # Pruning always checks tiers 0-3 only, never escalating to tier 4:
    # removing a clue can only ever reduce what's derivable, so if `chosen`
    # needed tier 4 to complete in the first place, *every* removal trial
    # would need it too - repeating that expensive search across dozens of
    # trials is what made this pathologically slow. In the rare case where
    # growth's fallback above needed tier 4 to finish the whole pool,
    # pruning simply can't shrink it here (every trial correctly reports
    # "not solved" via the cheap check) and the min/max_clues band check
    # below will reject the attempt - a fast, safe outcome; the caller
    # just retries with a fresh layout/solution. `_solves_with_required_properties`
    # keeps this the same cost class (still no tier 4) while also refusing
    # any removal that would strip out combination-necessity once it's won.
    improved = True
    while improved:
        improved = False
        order = list(chosen)
        rng.shuffle(order)
        for clue in order:
            trial = [c for c in chosen if c is not clue]
            if not trial:
                continue
            if _solves_with_required_properties(trial, difficulty, cache) and cache.is_unique(trial):
                chosen = trial
                improved = True
                break

    # Deterministic finishing pass: prefer to shed the *easiest* remaining
    # clues (lowest tier, largest scope) first, instead of random order, so
    # whatever difficulty survives random pruning gets concentrated into
    # the final puzzle rather than left to chance.
    def _easiness(clue: Clue) -> tuple[int, int]:
        return (clue.tier, -len(clue.scope))

    improved = True
    while improved:
        improved = False
        for clue in sorted(chosen, key=_easiness):
            trial = [c for c in chosen if c is not clue]
            if not trial:
                continue
            if _solves_with_required_properties(trial, difficulty, cache) and cache.is_unique(trial):
                chosen = trial
                improved = True
                break

    if not (difficulty.min_clues <= len(chosen) <= difficulty.max_clues):
        return None

    final_trace = _solves(chosen, difficulty, cache)
    if final_trace.max_tier > difficulty.max_tier_allowed:
        return None
    if difficulty.require_min_tier and final_trace.max_tier < difficulty.require_min_tier:
        return None
    # min_chain_depth is a bonus requirement, not a mandatory one: proving
    # tiers 0-3 *provably can't* finish a puzzle (forcing tier 4 to be used)
    # would mean an expensive negative-proof retry loop on nearly every
    # attempt. Instead, only require real depth on the hypothesis chains
    # that *do* happen to occur - most Hard puzzles will still get some
    # tier-4 moments given how much of the pool tends toward tier 2-3.
    if difficulty.min_chain_depth and final_trace.max_tier >= 4:
        if final_trace.max_chain_depth < difficulty.min_chain_depth:
            return None
    # Unlike min_chain_depth (a bonus-only check), this is a genuine
    # necessity proof, not just "did combination happen to fire": whether
    # tiers 0-3 alone are order-independently *sufficient* is well-defined
    # (a fixpoint always converges to the same known-set regardless of
    # iteration order), but *which* deduction path gets credited for a
    # given fact (combination vs. an individual clue eventually going
    # tight on its own) is NOT order-independent - two clue sets/orderings
    # that solve identically could differ on whether trace.used_combination
    # happens to be True. So proving combination is actually *required*
    # means checking solvability *without* it, directly - cheap
    # (O(count-clues^2), nothing like tier 4's hypothesis search), so
    # affording this as a hard requirement + retry doesn't reintroduce the
    # tier-4 performance trap.
    if difficulty.require_combination:
        without_combination = cache.solves(chosen, allow_tier4=difficulty.allow_tier4, allow_combination=False)
        if without_combination.solved:
            return None  # solvable without ever combining two clues - not hard enough, retry

    return chosen


# ---------------------------------------------------------------------------
# Per-cell clue attachment
# ---------------------------------------------------------------------------


def _sort_key(clue: Clue) -> tuple[int, int, int]:
    is_direct = 0 if isinstance(clue, DirectRevealClue) else 1
    return (is_direct, clue.tier, len(clue.scope))


def _starter_candidate_cells(chosen: list[Clue], rng: random.Random) -> list[Cell]:
    """Shuffled starter-cell candidates, biased toward cells covered by at
    least one small-scope clue (<=3 cells) - much more likely to fire
    immediately from just the starter fact alone now that tier-1
    bootstrapping clues are banned outside Easy. Falls back to every cell
    if no such small-scope cell exists. Used both for the single-starter
    path (take the first) and the multi-starter quality search below (take
    up to `difficulty.starter_candidates`)."""
    small_scope_cells = sorted({c for clue in chosen if len(clue.scope) <= 3 for c in clue.scope})
    pool = list(small_scope_cells) if small_scope_cells else list(ALL_CELLS)
    rng.shuffle(pool)
    return pool


def _attach_with_starter(
    chosen: list[Clue],
    solution: Solution,
    difficulty: DifficultyParams,
    starter_cell: Cell,
) -> tuple[dict[Cell, Clue], AttachmentQuality] | None:
    """Seed the reasoning trace with `starter_cell`'s true value and walk
    the resulting trace to assign every clue a slot: a cell that's already
    knowable by the time that clue is needed, so a player following the
    chain in attachment order is never asked to guess something they
    couldn't yet determine. Combination steps (clue_id starting with
    "combine:") don't get their own slot - the "clue" for a combine-derived
    cell *is* the two already-attached clues it came from, nothing new to
    show - but a clue that only ever contributes as a combine partner
    (never independently fires on its own) still needs a slot somewhere so
    its text is visible at all. Cells that end up with no clue attached
    (including any resolved only via combination, or via tier-4 hypothesis
    testing) get a fun fact at play-time instead (see reveal.py). Also
    returns an AttachmentQuality (see difficulty_metrics.py) describing how
    evenly paced this particular attachment is - both `attach_clues_to_cells`
    (multiple starters, same `chosen`) and `generate_puzzle` (multiple
    independent `chosen` sets, via candidate_pool_size) use it to keep the
    best-paced result."""
    sorted_clues = sorted(chosen, key=_sort_key)
    trace = run_reasoner(
        sorted_clues,
        initial_known={starter_cell: solution[starter_cell]},
        allow_tier4=difficulty.allow_tier4,
        allow_combination=difficulty.allow_combination,
    )
    if not trace.solved:
        return None
    first_id = trace.steps[0].clue_id if trace.steps else None
    if first_id is None or first_id == "hypothesis" or first_id.startswith(COMBINE_PREFIX):
        return None  # first move would require reasoning the player hasn't unlocked yet

    id_to_clue = {c.id: c for c in sorted_clues}

    if difficulty.max_starter_power is not None:
        starter_clue = id_to_clue[first_id]
        starter_only_known, _ = propagate_to_fixpoint([starter_clue], {starter_cell: solution[starter_cell]})
        if len(starter_only_known) - 1 > difficulty.max_starter_power:
            return None  # starter alone hands over too much for free - retry with a different starter

    known_cells: list[Cell] = [starter_cell]
    available_slots: list[Cell] = []
    cell_clue: dict[Cell, Clue] = {starter_cell: id_to_clue[first_id]}
    attached: set[str] = {first_id}
    pending_real: list[str] = []

    for step in trace.steps:
        if step.cell not in known_cells:
            known_cells.append(step.cell)
            if step.cell not in cell_clue:
                available_slots.append(step.cell)
        if step.clue_id == "hypothesis" or step.clue_id.startswith(COMBINE_PREFIX):
            continue
        if step.clue_id not in attached and step.clue_id not in pending_real:
            pending_real.append(step.clue_id)
        while pending_real and available_slots:
            clue_id = pending_real.pop(0)
            slot = available_slots.pop(0)
            cell_clue[slot] = id_to_clue[clue_id]
            attached.add(clue_id)

    # A clue that only ever contributed as a combine partner (its own
    # propagate() never independently fired) still needs a slot.
    for clue in chosen:
        if clue.id in attached:
            continue
        if not available_slots:
            return None
        cell_clue[available_slots.pop(0)] = clue
        attached.add(clue.id)

    if len(attached) != len(chosen):
        return None  # a clue never actually contributed under this ordering - bail, caller retries

    replay_steps = _replay_attachment(starter_cell, solution, cell_clue, difficulty)
    if replay_steps is None:
        return None  # extremely unlikely given the construction above, but cheap to double-check

    quality = analyze_attachment_steps(replay_steps)
    # require_combination (select_clue_subset) only proves `chosen` is
    # unsolvable via combination-free reasoning from a COLD start (no
    # initial_known) - but real play starts with the starter's fact for
    # free and unlocks clues incrementally, which can be enough extra
    # leverage to route around the combination step entirely (measured,
    # not assumed: this genuinely happens). Re-check against the actual
    # play sequence here, where it matters.
    if difficulty.require_combination:
        needed = max(1, difficulty.min_combination_events)
        if quality.combination_event_count < needed:
            return None  # this attachment's actual play sequence didn't combine enough distinct times - retry

    return cell_clue, quality


def attach_clues_to_cells(
    chosen: list[Clue],
    solution: Solution,
    difficulty: DifficultyParams,
    rng: random.Random,
) -> tuple[Cell, dict[Cell, Clue], AttachmentQuality] | None:
    """Try up to `difficulty.starter_candidates` distinct starter cells for
    this ALREADY-valid `chosen` clue set (no re-running select_clue_subset -
    that's the expensive ~88%-of-attempts bottleneck; this only re-runs the
    comparatively cheap attachment/replay logic per extra starter) and keep
    whichever succeeds with the best score_attachment_quality. A cheap way
    to get some of candidate_pool_size's quality benefit without paying for
    a fresh clue-set search each time - stacks with it naturally (Hard's
    handful of independent `chosen` sets each also get their own best-of-N
    starter). `starter_candidates=1` (Easy's default) is byte-for-byte
    identical to the old single-starter behavior."""
    num_candidates = max(1, difficulty.starter_candidates)
    starter_pool = _starter_candidate_cells(chosen, rng)[:num_candidates]

    best: tuple[Cell, dict[Cell, Clue], AttachmentQuality] | None = None
    for starter_cell in starter_pool:
        result = _attach_with_starter(chosen, solution, difficulty, starter_cell)
        if result is None:
            continue
        cell_clue, quality = result
        if best is None or score_attachment_quality(quality, difficulty) > score_attachment_quality(best[2], difficulty):
            best = (starter_cell, cell_clue, quality)
    return best


def _replay_attachment(
    starter_cell: Cell,
    solution: Solution,
    cell_clue: dict[Cell, Clue],
    difficulty: DifficultyParams,
) -> list[Step] | None:
    """Defensive replay AND the source of the attachment-quality signal:
    simulate a player who only ever reasons with clues attached to cells
    they've correctly identified so far, starting from the starter alone,
    and confirm that process reaches every cell - exactly what a real
    playthrough needs, including any combine-derived facts once both of a
    combination's parent clues are active (same pattern as
    backend/tests/test_reveal.py's attachment-chain test). Returns the
    full, de-duplicated step history in chronological discovery order if
    the replay reaches every cell, else None - run_reasoner is
    deterministic given the same clues + known state, and each pass's
    `initial_known` already contains everything discovered by an earlier
    pass, so re-running it every time active_clues grows only ever emits
    genuinely *new* steps, safe to concatenate across passes."""
    known: KnownState = {starter_cell: solution[starter_cell]}
    active_clues: list[Clue] = [cell_clue[starter_cell]]
    all_steps: list[Step] = []
    changed = True
    while changed:
        changed = False
        trace = run_reasoner(
            active_clues, initial_known=known, allow_tier4=difficulty.allow_tier4, allow_combination=difficulty.allow_combination
        )
        all_steps.extend(trace.steps)
        for cell, value in trace.known.items():
            if cell not in known:
                known[cell] = value
                changed = True
        for cell in list(known):
            clue = cell_clue.get(cell)
            if clue is not None and clue not in active_clues:
                active_clues.append(clue)
                changed = True
    if len(known) != NUM_CELLS:
        return None
    return all_steps


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def generate_puzzle(
    pool: list[Person],
    difficulty_name: str,
    max_attempts: int = MAX_GENERATION_ATTEMPTS,
    time_budget_s: float = GENERATION_TIME_BUDGET_SECONDS,
    rng: random.Random | None = None,
) -> PuzzleData:
    """Retries attempts (fresh layout/solution/pool each time) until a
    valid puzzle is found, bounded by `max_attempts`/`time_budget_s`.
    When `difficulty.candidate_pool_size > 1` (Hard), doesn't stop at the
    first valid puzzle - keeps going, collecting up to that many, and
    returns the best-paced one (see difficulty_metrics.py's
    AttachmentQuality/score_attachment_quality). Each additional candidate
    is a fresh random attempt with the SAME wide latency distribution as
    the first, not a refinement of it - measured (not assumed) to roughly
    double median Hard generation time if bounded as a *fraction* of the
    whole budget, so instead: once at least one candidate exists, stop
    hunting for more after EXTRA_CANDIDATE_ATTEMPT_BUDGET more attempts (a
    count-based cap, not a wall-clock one - bounds cost predictably
    *and*, unlike a time-based cutoff, makes the whole function a pure
    function of `rng`'s sequence, which the seed system depends on: the
    same seed must always produce the same puzzle regardless of how fast
    the machine happens to be that moment). `time_budget_s` remains as an
    outer safety net for genuinely pathological cases, not the primary
    control. Easy/Medium (`candidate_pool_size=1`) are unaffected: the
    very first success still returns immediately, exactly as before."""
    difficulty = get_difficulty(difficulty_name)
    rng = rng or random.Random()
    start = time.monotonic()
    target_candidates = max(1, difficulty.candidate_pool_size)
    candidates: list[tuple[PuzzleData, AttachmentQuality]] = []
    attempts_since_first_candidate: int | None = None

    for _ in range(max_attempts):
        if time.monotonic() - start > time_budget_s:
            break
        if attempts_since_first_candidate is not None and attempts_since_first_candidate >= EXTRA_CANDIDATE_ATTEMPT_BUDGET:
            break
        if attempts_since_first_candidate is not None:
            attempts_since_first_candidate += 1

        layout = random_grid_layout(pool, rng)
        ratio = rng.uniform(*difficulty.criminal_ratio_range)
        solution = random_solution(ratio, rng)

        candidate_pool = build_candidate_pool(layout, solution, difficulty, rng)
        chosen = select_clue_subset(candidate_pool, difficulty, rng)
        if chosen is None:
            continue

        result = attach_clues_to_cells(chosen, solution, difficulty, rng)
        if result is None:
            continue
        starter_cell, cell_clue, quality = result

        data = PuzzleData(
            layout=layout,
            solution=solution,
            starter_cell=starter_cell,
            cell_clue=cell_clue,
            difficulty=difficulty,
        )
        if attempts_since_first_candidate is None:
            attempts_since_first_candidate = 0
        candidates.append((data, quality))
        if len(candidates) >= target_candidates:
            break

    if not candidates:
        raise GenerationTimeoutError(
            "Could not generate a valid puzzle in time. Try again, or a different difficulty."
        )
    if len(candidates) == 1:
        return candidates[0][0]
    return max(candidates, key=lambda pair: score_attachment_quality(pair[1], difficulty))[0]
