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
from backend.app.core.types import ALL_CELLS, Cell, KnownState

COMBINE_PREFIX = "combine:"


def _derive_pair_facts(a: CountConstraintClue, b: CountConstraintClue, known: KnownState) -> KnownState:
    """If `a`'s scope is a strict subset of `b`'s, basic set arithmetic
    gives an exact target for the difference region B\\A for free: since
    sum(B) = sum(A) + sum(B\\A) always, sum(B\\A) = b.target - a.target -
    no assumption needed, it's an identity, not a guess. Apply the same
    tight-case forcing CountConstraintClue.propagate uses on that derived
    region. This is the "hold two clues in your head and subtract one
    from the other" reasoning a single clue's own propagate() can never
    produce alone - the mechanism genuinely multi-clue puzzles need.

    A derived target outside [0, len(diff)] can only happen while
    exploring a false hypothesis (both clues are always true statements
    about the real solution, so the identity above can't fail there) -
    raising ContradictionError here is correct and, as a side effect,
    strengthens tier-4/5 hypothesis testing for free."""
    scope_a = set(a.scope_list)
    scope_b = set(b.scope_list)
    if not scope_a < scope_b:  # strict subset required; equal/disjoint/partial give nothing
        return {}

    diff = [c for c in b.scope_list if c not in scope_a]
    diff_target = b.target - a.target
    unknowns = [c for c in diff if c not in known]
    known_criminals = sum(1 for c in diff if known.get(c) is True)

    if diff_target < known_criminals or diff_target > known_criminals + len(unknowns):
        raise ContradictionError(f"{COMBINE_PREFIX}{a.id}:{b.id}")
    if not unknowns:
        return {}
    needed = diff_target - known_criminals
    if needed == 0:
        return {c: False for c in unknowns}
    if needed == len(unknowns):
        return {c: True for c in unknowns}
    return {}


def propagate_to_fixpoint(
    clues: list[Clue], known: KnownState, allow_combination: bool = False
) -> tuple[KnownState, list[Step]]:
    """Apply every clue's propagate() repeatedly until no clue yields any
    new fact. When `allow_combination` is set, also cross-references every
    pair of active CountConstraintClues (see `_derive_pair_facts`) each
    round - cheap (O(count-clues^2)), unlike tier-4's hypothesis search,
    so it's safe to run on every pass. Raises ContradictionError if
    `known` is infeasible under any clue or combined pair - stamped with
    `depth = len(steps)`, i.e. how many forced facts this call had already
    accumulated before the contradiction, so callers doing hypothesis
    testing can measure how deep the forced chain went. Does not mutate
    the `known` argument."""
    known = dict(known)
    steps: list[Step] = []
    count_clues = [c for c in clues if isinstance(c, CountConstraintClue)] if allow_combination else []
    round_num = 0

    def _commit(
        cell: Cell, value: bool, clue_id: str, tier: int, text: str, used_cells: frozenset[Cell], used_clue_ids: tuple[str, ...]
    ) -> bool:
        if cell in known:
            if known[cell] != value:
                raise ContradictionError(clue_id, depth=len(steps))
            return False
        known[cell] = value
        steps.append(Step(clue_id, tier, cell, value, text, round=round_num, used_cells=used_cells, used_clue_ids=used_clue_ids))
        return True

    changed = True
    while changed:
        changed = False
        for clue in clues:
            # Snapshot BEFORE calling propagate() - every cell this call
            # resolves shares this same dependency set (one deduction
            # event, not one per cell).
            used_cells = frozenset(c for c in clue.scope if c in known)
            try:
                new_facts = clue.propagate(known)
            except ContradictionError as exc:
                exc.depth = len(steps)
                raise
            for cell, value in new_facts.items():
                if _commit(cell, value, clue.id, clue.tier, clue.text, used_cells, (clue.id,)):
                    changed = True

        if allow_combination:
            for a, b in itertools.combinations(count_clues, 2):
                for src, dst in ((a, b), (b, a)):
                    used_cells = frozenset(c for c in (src.scope | dst.scope) if c in known)
                    try:
                        new_facts = _derive_pair_facts(src, dst, known)
                    except ContradictionError as exc:
                        exc.depth = len(steps)
                        raise
                    if not new_facts:
                        continue
                    clue_id = f"{COMBINE_PREFIX}{src.id}:{dst.id}"
                    text = (
                        f"Combining \"{src.text}\" with \"{dst.text}\" pins down the rest "
                        f"of the second group."
                    )
                    for cell, value in new_facts.items():
                        if _commit(cell, value, clue_id, 3, text, used_cells, (src.id, dst.id)):
                            changed = True

        round_num += 1

    return known, steps


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
