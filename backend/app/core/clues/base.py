"""The Clue abstract base class and the small shared types around it.

Every clue flavor implements four operations against the *same* underlying
fact:
  - evaluate:      is this clue true of a given candidate solution?
  - add_to_model:  contribute a constraint to the CP-SAT uniqueness model.
  - propagate:     a human-style deduction rule: given partially known
                    cells, what (if anything) can be newly deduced from
                    this clue alone? Raises ContradictionError if `known`
                    is already inconsistent with this clue.
  - render_text:   a frozen, player-facing natural-language rendering,
                    computed once at construction time.
"""

from __future__ import annotations

import itertools
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from backend.app.core.types import CELL_MASK, Cell, Grid, KnownState, Solution, cells_to_mask

_id_counter = itertools.count()


class ContradictionError(Exception):
    """Raised by Clue.propagate() when `known` is infeasible for this clue.

    `depth` is stamped by propagate_to_fixpoint (reasoner.py) with how many
    forced facts had already been accumulated in that call before this
    contradiction hit - used to measure hypothesis-testing chain length for
    Hard-difficulty generation (see generator.py)."""

    def __init__(self, clue_id: str, depth: int = 0):
        super().__init__(f"Contradiction detected via clue {clue_id!r}")
        self.clue_id = clue_id
        self.depth = depth


@dataclass
class Step:
    """One deduction made during reasoning: this clue resolved this cell.
    `depth` is only meaningful for `clue_id == "hypothesis"` steps - how
    many forced moves happened before the contradiction that justified it.

    `round`/`used_cells`/`used_clue_ids` are the dependency-graph fields
    (see core/difficulty_metrics.py): `round` is which fixpoint iteration
    this fired in (steps sharing a round fired "simultaneously" - a cheap
    branching-factor proxy); `used_cells` is which already-known cells
    this deduction's clue(s) depended on (empty for a root fact like a
    DirectRevealClue); `used_clue_ids` is which clue(s) produced it (two
    for a combine step, one otherwise)."""

    clue_id: str
    tier: int
    cell: Cell
    value: bool
    text: str
    depth: int = 0
    round: int = 0
    used_cells: frozenset[Cell] = frozenset()
    used_clue_ids: tuple[str, ...] = ()


@dataclass
class ReasoningTrace:
    known: KnownState
    steps: list[Step] = field(default_factory=list)
    solved: bool = False
    max_tier: int = 0
    max_chain_depth: int = 0
    used_combination: bool = False  # True if any step came from combining two count clues


class Clue(ABC):
    """Base class for all clue flavors. Subclasses must set any fields
    `render_text` depends on *before* calling `super().__init__(...)`, and
    must also set `self.scope_order: tuple[Cell, ...]` before calling
    `super().__init__(...)` - the FIXED, deterministic cell order relevant
    to this clue's own scope (e.g. CountConstraintClue's `scope_list` as a
    tuple; CompareCountClue's `scope_a + scope_b`; a flattened `groups`
    for AtLeastOneCriminalClue) - see `propagate()`'s docstring for why
    this matters beyond just documentation.

    `rng`, if given, is the SAME per-generation `random.Random` instance
    threaded through generator.py - subclasses' render_text() should pass
    `self._rng` on to phrasing.py's template-choosing functions so wording
    variety is a deterministic function of the puzzle's seed too (not just
    the layout/solution/clue-set), which the seed system depends on.
    Defaults to None (falls back to the global `random` module) so
    existing call sites that don't care about determinism - most of the
    test suite - are unaffected."""

    tier: int
    scope_order: tuple[Cell, ...]

    def __init__(self, scope: frozenset[Cell], grid: Grid, rng: random.Random | None = None):
        self.id: str = f"clue{next(_id_counter)}"
        self.scope: frozenset[Cell] = scope
        self.scope_mask: int = cells_to_mask(scope)
        self._rng: random.Random = rng if rng is not None else random
        self.text: str = self.render_text(grid)

    @abstractmethod
    def evaluate(self, solution: Solution) -> bool:
        """Is this clue a true statement about `solution`?"""

    @abstractmethod
    def add_to_model(self, model, cell_vars: dict[Cell, object]) -> None:
        """Add this clue's constraint to a CP-SAT model."""

    @abstractmethod
    def propagate_mask(self, known_mask: int, criminal_mask: int) -> tuple[int, int]:
        """Bitmask-native equivalent of propagate() - the actual hot-path
        primitive reasoner.py's propagate_to_fixpoint calls directly, many
        times per generation attempt (this is the single biggest measured
        cost in puzzle generation - see project memory). Returns
        (newly_known_mask, newly_criminal_mask): which cells (as bits in
        types.CELL_MASK's numbering) are newly forced, and among those,
        which are criminal - (0, 0) if nothing new can be deduced yet.
        Raise ContradictionError if (known_mask, criminal_mask) is
        impossible under this clue - same contract as propagate()."""

    def propagate(self, known: KnownState) -> KnownState:
        """Dict-based compatibility wrapper around propagate_mask() - the
        public API every external caller (tests, anything outside
        reasoner.py's hot loop) uses. Single source of truth is
        propagate_mask(); this only converts at the boundary, so the two
        can never silently drift apart. Iterates `self.scope_order` (not
        an arbitrary bit-scan order) so a clue that forces several cells
        at once returns them in the exact same order the original
        per-clue dict-comprehension implementations always did - this
        isn't just cosmetic: reasoner.py's Step order for a multi-cell
        firing is what generator.py's FIFO attachment uses to decide
        which cell a subsequently-attached clue lands on, so a different
        order would silently change the seed->puzzle mapping the seed
        system depends on, even though the puzzle would still be equally
        valid. See propagate_mask's docstring for the hot-path version."""
        known_mask = 0
        criminal_mask = 0
        for c, v in known.items():
            bit = CELL_MASK[c]
            known_mask |= bit
            if v:
                criminal_mask |= bit
        new_known_mask, new_criminal_mask = self.propagate_mask(known_mask, criminal_mask)
        if new_known_mask == 0:
            return {}
        return {c: bool(new_criminal_mask & CELL_MASK[c]) for c in self.scope_order if CELL_MASK[c] & new_known_mask}

    @abstractmethod
    def render_text(self, grid: Grid) -> str:
        """Player-facing natural-language rendering of this clue."""

    def guaranteed_reveal_cell(self) -> Cell | None:
        """The one cell this clue is guaranteed to reveal outright given
        ZERO prior knowledge (a tier-0 fact, unconditional) - if any. None
        for clues that need some existing knowledge before they can derive
        anything (the common case). Used by generator.py to bias starter
        selection toward clues that pay off immediately regardless of
        their overall `scope` size - matters for a clue like
        DirectCountClue whose `scope` is a whole group but which still
        only ever reveals ONE specific cell unconditionally."""
        return None

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{type(self).__name__} {self.id} tier={self.tier} {self.text!r}>"
