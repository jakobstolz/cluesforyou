"""What gets shown when a cell is correctly identified.

Attachment is fixed at generation time (see generator.py::attach_clues_to_cells),
so there's nothing dynamic to decide here anymore: a cell either has a
real clue permanently attached to it, or it doesn't - in which case it
gets a cosmetic fun fact instead. The reasoner is no longer needed for
this; it's still used, unchanged, for the /api/hint bail-out in
api/routes.py, which is a genuinely dynamic "what's derivable from the
clues currently in play" question.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.core.clues.base import Clue
from backend.app.core.funfacts import pick_funfact
from backend.app.core.types import Cell, Grid


@dataclass
class Reveal:
    kind: str  # "clue" | "funfact"
    text: str
    tier: int | None = None


def reveal_for_cell(
    cell: Cell,
    value: bool,
    layout: Grid,
    cell_clue: dict[Cell, Clue],
    used_funfact_keys: set[str],
) -> Reveal:
    clue = cell_clue.get(cell)
    if clue is not None:
        return Reveal(kind="clue", text=clue.text, tier=clue.tier)

    row, col = cell
    person = layout[row][col]
    text = pick_funfact(person.name, person.profession, value, used_funfact_keys)
    return Reveal(kind="funfact", text=text)
