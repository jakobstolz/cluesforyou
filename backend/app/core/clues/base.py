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

from backend.app.core.types import Cell, Grid, KnownState, Solution

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
    `render_text` depends on *before* calling `super().__init__(...)`.

    `rng`, if given, is the SAME per-generation `random.Random` instance
    threaded through generator.py - subclasses' render_text() should pass
    `self._rng` on to phrasing.py's template-choosing functions so wording
    variety is a deterministic function of the puzzle's seed too (not just
    the layout/solution/clue-set), which the seed system depends on.
    Defaults to None (falls back to the global `random` module) so
    existing call sites that don't care about determinism - most of the
    test suite - are unaffected."""

    tier: int

    def __init__(self, scope: frozenset[Cell], grid: Grid, rng: random.Random | None = None):
        self.id: str = f"clue{next(_id_counter)}"
        self.scope: frozenset[Cell] = scope
        self._rng: random.Random = rng if rng is not None else random
        self.text: str = self.render_text(grid)

    @abstractmethod
    def evaluate(self, solution: Solution) -> bool:
        """Is this clue a true statement about `solution`?"""

    @abstractmethod
    def add_to_model(self, model, cell_vars: dict[Cell, object]) -> None:
        """Add this clue's constraint to a CP-SAT model."""

    @abstractmethod
    def propagate(self, known: KnownState) -> KnownState:
        """Return newly-deduced {cell: value} facts derivable from this
        clue plus `known` alone. Return {} if nothing new can be deduced
        yet. Raise ContradictionError if `known` is impossible under this
        clue."""

    @abstractmethod
    def render_text(self, grid: Grid) -> str:
        """Player-facing natural-language rendering of this clue."""

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{type(self).__name__} {self.id} tier={self.tier} {self.text!r}>"
