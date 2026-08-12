"""Pydantic request/response schemas for the API. These are the only
shapes ever sent to the client - solution booleans and unrevealed clues
never appear in any of them."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from backend.app.config import GRID_COLS, GRID_ROWS

# ---------- Roster ----------


class RosterEntryOut(BaseModel):
    id: str
    name: str
    profession: str


class RosterListResponse(BaseModel):
    people: list[RosterEntryOut]


class UpsertRosterEntryRequest(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    profession: str = Field(min_length=1, max_length=40)

    @field_validator("name", "profession")
    @classmethod
    def _nonempty_trimmed(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be empty")
        return cleaned


# ---------- Puzzle ----------


class GeneratePuzzleRequest(BaseModel):
    difficulty: Literal["easy", "medium", "hard"]


class GridCellOut(BaseModel):
    row: int
    col: int
    name: str
    profession: str


class StarterOut(BaseModel):
    row: int
    col: int
    status: Literal["criminal", "innocent"]


class ClueOut(BaseModel):
    id: str
    text: str
    tier: int


class PuzzleResponse(BaseModel):
    puzzle_id: str
    grid: list[list[GridCellOut]]
    starter: StarterOut
    first_clue: ClueOut
    difficulty: str


class GuessRequest(BaseModel):
    puzzle_id: str
    row: int = Field(ge=0, le=GRID_ROWS - 1)
    col: int = Field(ge=0, le=GRID_COLS - 1)
    guess: Literal["criminal", "innocent"]


class RevealOut(BaseModel):
    kind: Literal["clue", "funfact"]
    text: str
    tier: int | None = None


class GuessResponse(BaseModel):
    correct: bool
    reveal: RevealOut | None = None
    solved: bool = False


class HintRequest(BaseModel):
    puzzle_id: str


class HintResponse(BaseModel):
    available: bool
    row: int | None = None
    col: int | None = None
    value: Literal["criminal", "innocent"] | None = None
    reason: str | None = None
    reveal: RevealOut | None = None
    solved: bool = False
