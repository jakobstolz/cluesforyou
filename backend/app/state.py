"""In-memory server-side puzzle storage.

This app is a single local process for one household at a time, so a
plain dict keyed by puzzle_id is all the "persistence" it needs - no DB,
no sessions, no auth. The solution and per-cell clue attachments live
here only; API responses never serialize them wholesale (see api/routes.py).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from backend.app.core.clues.base import Clue
from backend.app.core.difficulty import DifficultyParams
from backend.app.core.types import Cell, Grid, KnownState, Solution


@dataclass
class PuzzleRecord:
    layout: Grid
    solution: Solution
    starter_cell: Cell
    cell_clue: dict[Cell, Clue]  # cells with a real attached clue; all other cells -> fun fact
    difficulty: DifficultyParams
    known_correct: KnownState = field(default_factory=dict)
    used_funfact_keys: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.known_correct = {self.starter_cell: self.solution[self.starter_cell]}


PUZZLES: dict[str, PuzzleRecord] = {}


def create_puzzle_record(
    layout: Grid,
    solution: Solution,
    starter_cell: Cell,
    cell_clue: dict[Cell, Clue],
    difficulty: DifficultyParams,
) -> tuple[str, PuzzleRecord]:
    puzzle_id = uuid.uuid4().hex
    record = PuzzleRecord(
        layout=layout,
        solution=solution,
        starter_cell=starter_cell,
        cell_clue=cell_clue,
        difficulty=difficulty,
    )
    PUZZLES[puzzle_id] = record
    return puzzle_id, record


def get_puzzle(puzzle_id: str) -> PuzzleRecord | None:
    return PUZZLES.get(puzzle_id)
