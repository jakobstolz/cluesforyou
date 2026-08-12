"""API routes:
- roster management (the shared pool of name/profession pairs)
- generate a puzzle, submit per-cell guesses (each one revealing that
  cell's own attached clue or fun fact), and an optional hint bail-out.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.config import GRID_COLS, GRID_ROWS, NUM_CELLS
from backend.app.core import roster as roster_store
from backend.app.core.generator import GenerationTimeoutError, generate_puzzle
from backend.app.core.reasoner import run_reasoner
from backend.app.core.reveal import reveal_for_cell
from backend.app.core.types import Person
from backend.app.models import (
    ClueOut,
    GeneratePuzzleRequest,
    GridCellOut,
    GuessRequest,
    GuessResponse,
    HintRequest,
    HintResponse,
    PuzzleResponse,
    RevealOut,
    RosterEntryOut,
    RosterListResponse,
    StarterOut,
    UpsertRosterEntryRequest,
)
from backend.app.state import create_puzzle_record, get_puzzle

router = APIRouter()

MIN_ROSTER_SIZE = NUM_CELLS


def _status_to_bool(status: str) -> bool:
    return status == "criminal"


def _bool_to_status(value: bool) -> str:
    return "criminal" if value else "innocent"


def _reveal_out(reveal) -> RevealOut:
    return RevealOut(kind=reveal.kind, text=reveal.text, tier=reveal.tier)


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


# ---------- Roster ----------


@router.get("/roster", response_model=RosterListResponse)
def list_roster() -> RosterListResponse:
    entries = roster_store.load_roster()
    return RosterListResponse(people=[RosterEntryOut(id=e.id, name=e.name, profession=e.profession) for e in entries])


@router.post("/roster", response_model=RosterEntryOut, status_code=201)
def create_roster_entry(req: UpsertRosterEntryRequest) -> RosterEntryOut:
    try:
        entry = roster_store.add_entry(req.name, req.profession)
    except roster_store.DuplicatePairError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return RosterEntryOut(id=entry.id, name=entry.name, profession=entry.profession)


@router.put("/roster/{entry_id}", response_model=RosterEntryOut)
def update_roster_entry(entry_id: str, req: UpsertRosterEntryRequest) -> RosterEntryOut:
    try:
        entry = roster_store.update_entry(entry_id, req.name, req.profession)
    except roster_store.DuplicatePairError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown roster entry") from exc
    return RosterEntryOut(id=entry.id, name=entry.name, profession=entry.profession)


@router.delete("/roster/{entry_id}", status_code=204)
def delete_roster_entry(entry_id: str) -> None:
    try:
        roster_store.delete_entry(entry_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown roster entry") from exc


# ---------- Puzzle ----------


@router.post("/puzzle", response_model=PuzzleResponse)
def create_puzzle(req: GeneratePuzzleRequest) -> PuzzleResponse:
    roster = roster_store.load_roster()
    # A puzzle grid never repeats a name (see core/grid.py), so what matters
    # is distinct *names* in the roster, not raw entry count - two entries
    # sharing a name only count once toward the minimum.
    unique_names = {e.name for e in roster}
    if len(unique_names) < MIN_ROSTER_SIZE:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Add at least {MIN_ROSTER_SIZE} people with distinct names to your "
                f"roster first - you have {len(unique_names)}."
            ),
        )
    pool = [Person(e.name, e.profession) for e in roster]

    try:
        data = generate_puzzle(pool, req.difficulty)
    except GenerationTimeoutError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    puzzle_id, _record = create_puzzle_record(
        data.layout, data.solution, data.starter_cell, data.cell_clue, data.difficulty
    )

    grid_out = [
        [
            GridCellOut(row=r, col=c, name=data.layout[r][c].name, profession=data.layout[r][c].profession)
            for c in range(GRID_COLS)
        ]
        for r in range(GRID_ROWS)
    ]
    starter_out = StarterOut(
        row=data.starter_cell[0],
        col=data.starter_cell[1],
        status=_bool_to_status(data.solution[data.starter_cell]),
    )
    first_clue = data.cell_clue[data.starter_cell]

    return PuzzleResponse(
        puzzle_id=puzzle_id,
        grid=grid_out,
        starter=starter_out,
        first_clue=ClueOut(id=first_clue.id, text=first_clue.text, tier=first_clue.tier),
        difficulty=data.difficulty.name,
    )


@router.post("/guess", response_model=GuessResponse)
def submit_guess(req: GuessRequest) -> GuessResponse:
    record = get_puzzle(req.puzzle_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Unknown puzzle_id")

    cell = (req.row, req.col)
    guess_bool = _status_to_bool(req.guess)

    if record.solution[cell] != guess_bool:
        return GuessResponse(correct=False)

    if cell in record.known_correct:
        # Idempotent re-click on an already-locked cell - no double reveal.
        return GuessResponse(correct=True, solved=(len(record.known_correct) == NUM_CELLS))

    record.known_correct[cell] = guess_bool

    if len(record.known_correct) == NUM_CELLS:
        return GuessResponse(correct=True, solved=True)

    reveal = reveal_for_cell(cell, guess_bool, record.layout, record.cell_clue, record.used_funfact_keys)
    return GuessResponse(correct=True, reveal=_reveal_out(reveal), solved=False)


@router.post("/hint", response_model=HintResponse)
def get_hint(req: HintRequest) -> HintResponse:
    record = get_puzzle(req.puzzle_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Unknown puzzle_id")

    active_clues = [record.cell_clue[c] for c in record.known_correct if c in record.cell_clue]
    trace = run_reasoner(
        active_clues,
        initial_known=record.known_correct,
        allow_tier4=record.difficulty.allow_tier4,
        allow_combination=record.difficulty.allow_combination,
    )

    new_cells = [c for c in trace.known if c not in record.known_correct]
    if not new_cells:
        return HintResponse(available=False)

    cell = new_cells[0]
    value = trace.known[cell]
    record.known_correct[cell] = value
    reason = next((step.text for step in trace.steps if step.cell == cell), None)

    reveal = None
    if len(record.known_correct) < NUM_CELLS:
        reveal = _reveal_out(reveal_for_cell(cell, value, record.layout, record.cell_clue, record.used_funfact_keys))

    return HintResponse(
        available=True,
        row=cell[0],
        col=cell[1],
        value=_bool_to_status(value),
        reason=reason,
        reveal=reveal,
        solved=len(record.known_correct) == NUM_CELLS,
    )
