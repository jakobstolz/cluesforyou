"""The human-style reasoning engine.

`propagate_to_fixpoint` repeatedly asks every clue "what can you deduce
right now?" until nothing new comes out (tiers 0-3: direct reveals, exact
counts, comparisons), optionally also cross-referencing pairs of count
clues against each other (see `_derive_pair_facts`). `run_reasoner` wraps
that with an optional bounded tier-4 pass - single-level hypothesis
testing - for Hard-difficulty puzzles that need it. This same engine is
used both to *validate* that a generated puzzle is human-solvable, and at
play-time to decide whether the player is stuck (needs a new clue) or
could still make progress with what they've already got (gets a fun fact
instead) - see generator.py and api/routes.py.
"""

from __future__ import annotations

import itertools

from backend.app.config import NUM_CELLS
from backend.app.core.clues.base import Clue, ContradictionError, ReasoningTrace, Step
from backend.app.core.clues.counts import CountConstraintClue
from backend.app.core.types import ALL_CELLS, CELL_MASK, Cell, KnownState, mask_to_cells

COMBINE_PREFIX = "combine:"


def _subset_pairs(
    count_clues: list[CountConstraintClue],
) -> list[tuple[CountConstraintClue, CountConstraintClue, list[Cell], int, int]]:
    """Precompute every (small, big, diff_list, diff_mask, diff_target)
    tuple among `count_clues` where small's scope is a strict subset of
    big's - the only pairs `_derive_pair_facts_mask` can ever produce
    anything from (an equal/disjoint/partial-overlap pair always returns
    (0, 0) regardless of known state, since the identity it relies on
    needs a genuine subset relationship). Clue scopes/targets are fixed
    for the lifetime of a clue, so this whole tuple never changes across
    propagate_to_fixpoint's rounds - computing it once up front instead of
    re-deriving it on every round for every pair, most of which aren't
    subset pairs at all, was measured as the dominant generation-time cost
    for combination-requiring difficulties. `diff_list` (not just
    `diff_mask`) is kept for Step-ordering - see Clue.propagate()'s
    docstring on why a multi-cell reveal's exact cell order matters."""
    pairs: list[tuple[CountConstraintClue, CountConstraintClue, list[Cell], int, int]] = []
    for a, b in itertools.combinations(count_clues, 2):
        scope_a = a.scope
        scope_b = b.scope
        if scope_a < scope_b:
            diff_list = [c for c in b.scope_list if c not in scope_a]
            pairs.append((a, b, diff_list, _cells_mask(diff_list), b.target - a.target))
        elif scope_b < scope_a:
            diff_list = [c for c in a.scope_list if c not in scope_b]
            pairs.append((b, a, diff_list, _cells_mask(diff_list), a.target - b.target))
    return pairs


def _cells_mask(cells: list[Cell]) -> int:
    mask = 0
    for c in cells:
        mask |= CELL_MASK[c]
    return mask


def _derive_pair_facts_mask(diff_mask: int, diff_target: int, known_mask: int, criminal_mask: int) -> tuple[int, int]:
    """Bitmask equivalent of the old dict-based `_derive_pair_facts`: `a`'s
    scope is a strict subset of `b`'s (guaranteed by `_subset_pairs`) and
    `diff_mask` is B\\A - basic set arithmetic gives an exact target for
    that difference region for free, since sum(B) = sum(A) + sum(B\\A)
    always, so sum(B\\A) = b.target - a.target = `diff_target` (already
    precomputed once by `_subset_pairs`, not re-derived per call) - no
    assumption needed, it's an identity, not a guess. Apply the same
    tight-case forcing CountConstraintClue.propagate_mask uses on that
    derived region. This is the "hold two clues in your head and subtract
    one from the other" reasoning a single clue's own propagate_mask()
    can never produce alone - the mechanism genuinely multi-clue puzzles
    need.

    A derived target outside [0, popcount(diff_mask)] can only happen
    while exploring a false hypothesis (both clues are always true
    statements about the real solution, so the identity above can't fail
    there) - raising ContradictionError (by the caller, using the depth
    convention) here is correct and, as a side effect, strengthens
    tier-4/5 hypothesis testing for free. This function itself never
    raises - the caller (propagate_to_fixpoint) does, so it can stamp the
    combine: clue id onto the exception, same as the dict version did."""
    unknown_mask = diff_mask & ~known_mask
    known_criminals = (diff_mask & known_mask & criminal_mask).bit_count()
    unknown_count = unknown_mask.bit_count()

    if diff_target < known_criminals or diff_target > known_criminals + unknown_count:
        return -1, -1  # sentinel: caller raises ContradictionError
    if unknown_mask == 0:
        return 0, 0
    needed = diff_target - known_criminals
    if needed == 0:
        return unknown_mask, 0
    if needed == unknown_count:
        return unknown_mask, unknown_mask
    return 0, 0


def propagate_to_fixpoint(
    clues: list[Clue], known: KnownState, allow_combination: bool = False
) -> tuple[KnownState, list[Step]]:
    """Apply every clue's propagate_mask() repeatedly until no clue yields
    any new fact. When `allow_combination` is set, also cross-references
    every pair of active CountConstraintClues (see `_derive_pair_facts_mask`)
    each round - cheap (O(count-clues^2)), unlike tier-4's hypothesis
    search, so it's safe to run on every pass. Raises ContradictionError if
    `known` is infeasible under any clue or combined pair - stamped with
    `depth = len(steps)`, i.e. how many forced facts this call had already
    accumulated before the contradiction, so callers doing hypothesis
    testing can measure how deep the forced chain went. Does not mutate
    the `known` argument.

    Internally checks tightness via (known_mask, criminal_mask) int pairs -
    see types.py's bitmask helpers - avoiding dict/generator-expression/
    sum() work on the hot "is this clue tight yet" check that runs every
    round for every clue (measured 7-9x faster on realistic clue sets, see
    project memory). The returned KnownState dict itself is still built
    incrementally in the SAME insertion order the old fully dict-based
    version always produced (original `known` entries first, then each
    newly-forced cell appended the moment its Step is created) - this
    isn't just cosmetic: generator.py's _replay_attachment iterates a
    KnownState's keys in order to decide which clue to activate next when
    several cells resolve in the same pass, so a dict with the "right"
    content but the wrong iteration order silently changes attachment
    behavior. Caught by exactly this scenario during development - see
    project memory for the full story."""
    known_result: KnownState = dict(known)
    known_mask, criminal_mask = 0, 0
    for c, v in known.items():
        bit = CELL_MASK[c]
        known_mask |= bit
        if v:
            criminal_mask |= bit

    steps: list[Step] = []
    count_clues = [c for c in clues if isinstance(c, CountConstraintClue)] if allow_combination else []
    subset_pairs = _subset_pairs(count_clues) if allow_combination else []
    round_num = 0

    def _commit_mask(
        forced_known_mask: int,
        forced_criminal_mask: int,
        ordered_cells,
        clue_id: str,
        tier: int,
        text: str,
        used_cells_mask: int,
        used_clue_ids: tuple[str, ...],
    ) -> bool:
        nonlocal known_mask, criminal_mask
        # Defensive, matching the old per-cell _commit's same check: every
        # propagate_mask() implementation only ever returns bits that are
        # genuinely unknown relative to what it was called with, so this
        # should never actually trigger in practice - kept as cheap
        # insurance rather than assumed away.
        already_known = forced_known_mask & known_mask
        if already_known:
            if (criminal_mask & already_known) != (forced_criminal_mask & already_known):
                raise ContradictionError(clue_id, depth=len(steps))
        new_bits = forced_known_mask & ~known_mask
        if new_bits == 0:
            return False
        new_criminal_bits = forced_criminal_mask & new_bits
        used_cells = mask_to_cells(used_cells_mask)
        # Iterate the clue's (or combination pair's diff region's) own
        # canonical cell order, not an arbitrary bit-scan order - a
        # multi-cell reveal must produce Steps in the exact order the
        # original dict-based implementation always did, since that order
        # feeds generator.py's FIFO attachment and the seed->puzzle
        # mapping the seed system depends on (see Clue.propagate()'s
        # docstring for the full reasoning). Also appends to known_result
        # here (not just at the very end) so its key order matches too -
        # see this function's own docstring on why that matters.
        for c in ordered_cells:
            bit = CELL_MASK[c]
            if bit & new_bits:
                value = bool(new_criminal_bits & bit)
                steps.append(Step(clue_id, tier, c, value, text, round=round_num, used_cells=used_cells, used_clue_ids=used_clue_ids))
                known_result[c] = value
        known_mask |= new_bits
        criminal_mask |= new_criminal_bits
        return True

    changed = True
    while changed:
        changed = False
        for clue in clues:
            # Snapshot BEFORE calling propagate_mask() - every cell this
            # call resolves shares this same dependency set (one
            # deduction event, not one per cell).
            used_cells_mask = clue.scope_mask & known_mask
            try:
                forced_known_mask, forced_criminal_mask = clue.propagate_mask(known_mask, criminal_mask)
            except ContradictionError as exc:
                exc.depth = len(steps)
                raise
            if forced_known_mask and _commit_mask(
                forced_known_mask, forced_criminal_mask, clue.scope_order, clue.id, clue.tier, clue.text, used_cells_mask, (clue.id,)
            ):
                changed = True

        if allow_combination:
            for src, dst, diff_list, diff_mask, diff_target in subset_pairs:
                used_cells_mask = (src.scope_mask | dst.scope_mask) & known_mask
                forced_known_mask, forced_criminal_mask = _derive_pair_facts_mask(diff_mask, diff_target, known_mask, criminal_mask)
                if forced_known_mask == -1:
                    raise ContradictionError(f"{COMBINE_PREFIX}{src.id}:{dst.id}", depth=len(steps))
                if not forced_known_mask:
                    continue
                clue_id = f"{COMBINE_PREFIX}{src.id}:{dst.id}"
                text = (
                    f"Combining \"{src.text}\" with \"{dst.text}\" pins down the rest "
                    f"of the second group."
                )
                if _commit_mask(forced_known_mask, forced_criminal_mask, diff_list, clue_id, 3, text, used_cells_mask, (src.id, dst.id)):
                    changed = True

        round_num += 1

    return known_result, steps


def run_reasoner(
    clues: list[Clue],
    initial_known: KnownState | None = None,
    allow_tier4: bool = False,
    allow_combination: bool = False,
) -> ReasoningTrace:
    known, steps = propagate_to_fixpoint(clues, initial_known or {}, allow_combination=allow_combination)

    if allow_tier4:
        progress = True
        while progress and len(known) < NUM_CELLS:
            progress = False
            for cell in ALL_CELLS:
                if cell in known:
                    continue
                for hypothesis in (True, False):
                    try:
                        propagate_to_fixpoint(clues, {**known, cell: hypothesis}, allow_combination=allow_combination)
                    except ContradictionError as exc:
                        forced_value = not hypothesis
                        known[cell] = forced_value
                        hyp_label = "a criminal" if hypothesis else "innocent"
                        forced_label = "innocent" if hypothesis else "a criminal"
                        steps.append(
                            Step(
                                "hypothesis",
                                4,
                                cell,
                                forced_value,
                                f"Assuming this person were {hyp_label} leads to a "
                                f"contradiction, so they must be {forced_label}.",
                                depth=exc.depth,
                                # A hypothesis step depends on the entire current
                                # known-state (that's what got contradicted), not
                                # any specific clue - "hypothesis" is both its
                                # clue_id and its sole used_clue_id.
                                used_cells=frozenset(known),
                                used_clue_ids=("hypothesis",),
                            )
                        )
                        progress = True
                        break
                if progress:
                    break
            if progress:
                known, more_steps = propagate_to_fixpoint(clues, known, allow_combination=allow_combination)
                steps += more_steps

    return ReasoningTrace(
        known=known,
        steps=steps,
        solved=len(known) == NUM_CELLS,
        max_tier=max((s.tier for s in steps), default=0),
        max_chain_depth=max((s.depth for s in steps if s.clue_id == "hypothesis"), default=0),
        used_combination=any(s.clue_id.startswith(COMBINE_PREFIX) for s in steps),
    )
