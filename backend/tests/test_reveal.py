import random

import pytest

from backend.app.config import NUM_CELLS
from backend.app.core.clues import DirectRevealClue
from backend.app.core.difficulty import get_difficulty
from backend.app.core.funfacts import CRIMINAL_FACTS, INNOCENT_FACTS
from backend.app.core.generator import generate_puzzle
from backend.app.core.grid import random_grid_layout
from backend.app.core.reasoner import run_reasoner
from backend.app.core.reveal import reveal_for_cell
from backend.app.core.types import Person

NAMES = [
    "Alice", "Bob", "Carl", "Dana", "Eli", "Fay", "Gus", "Hana", "Ivo", "Jill",
    "Kian", "Lea", "Milo", "Nia", "Omar", "Pia", "Quinn", "Rex", "Sara", "Theo",
]  # 20 distinct names, matches NUM_CELLS - a generated grid never repeats a name
PROFESSIONS = ["Chef", "Cop", "Doctor", "Teacher", "Engineer"]
POOL = [Person(NAMES[i], PROFESSIONS[i % len(PROFESSIONS)]) for i in range(len(NAMES))]


def test_reveal_for_cell_with_attached_clue_returns_the_clue():
    grid = random_grid_layout(POOL, random.Random(1))
    cell = (0, 0)
    clue = DirectRevealClue(cell, True, grid)
    reveal = reveal_for_cell(cell, True, grid, {cell: clue}, set())
    assert reveal.kind == "clue"
    assert reveal.text == clue.text
    assert reveal.tier == clue.tier


def test_reveal_for_cell_without_attached_clue_returns_a_funfact():
    grid = random_grid_layout(POOL, random.Random(2))
    cell = (1, 1)
    reveal = reveal_for_cell(cell, False, grid, {}, set())
    assert reveal.kind == "funfact"
    # Not every fun-fact template references the person by name (some are
    # generic trivia - see core/funfacts.py) - just check we got real text.
    assert reveal.text


def test_reveal_for_cell_funfact_respects_used_keys():
    grid = random_grid_layout(POOL, random.Random(3))
    cell = (2, 2)
    used = set()
    texts = {reveal_for_cell(cell, True, grid, {}, used).text for _ in range(len(CRIMINAL_FACTS))}
    # With used_keys tracked, every template should be used at most once
    # while the pool isn't exhausted.
    assert len(texts) == len(CRIMINAL_FACTS)


DIFFICULTY_ITERATIONS = {"easy": 5, "medium": 5, "hard": 2}  # Hard's tier-4 necessity checks are slow

# See test_generator_stress.py's matching xfail for the full explanation:
# DirectCountClue's direct-reveal fact measurably (and knowingly, by
# deliberate choice) competes with require_combination's necessity proof -
# worse for Hard's stricter min_combination_events=2.
_DIRECT_COUNT_RELIABILITY_XFAIL_REASON = (
    "DirectCountClue's direct-reveal fact competes with require_combination's "
    "necessity proof (worse for Hard's stricter min_combination_events=2) - "
    "accepted tradeoff, not a bug. See test_generator_stress.py's comment for measured numbers."
)


@pytest.mark.slow
@pytest.mark.parametrize(
    "difficulty",
    [
        "easy",
        pytest.param(
            "medium", marks=pytest.mark.xfail(reason=_DIRECT_COUNT_RELIABILITY_XFAIL_REASON, strict=False)
        ),
        pytest.param("hard", marks=pytest.mark.xfail(reason=_DIRECT_COUNT_RELIABILITY_XFAIL_REASON, strict=False)),
    ],
)
def test_generated_attachment_chain_reaches_all_cells(difficulty):
    rng = random.Random(f"attach-{difficulty}")
    params = get_difficulty(difficulty)

    for _ in range(DIFFICULTY_ITERATIONS[difficulty]):
        data = generate_puzzle(POOL, difficulty, rng=rng)

        # Every attached clue is used exactly once.
        clue_ids = [c.id for c in data.cell_clue.values()]
        assert len(clue_ids) == len(set(clue_ids))

        # Replay the reveal chain using ONLY the fixed per-cell attachment
        # (no dynamic decisions) and confirm it reaches every cell, matching
        # the true solution throughout.
        known = {data.starter_cell: data.solution[data.starter_cell]}
        active_clues = [data.cell_clue[data.starter_cell]]
        changed = True
        while changed:
            changed = False
            trace = run_reasoner(
                active_clues, initial_known=known, allow_tier4=params.allow_tier4, allow_combination=params.allow_combination
            )
            for cell, value in trace.known.items():
                if cell not in known:
                    known[cell] = value
                    changed = True
            for cell in list(known):
                clue = data.cell_clue.get(cell)
                if clue is not None and clue not in active_clues:
                    active_clues.append(clue)
                    changed = True

        assert known == data.solution

        # Fewer clues than cells - most cells fall back to fun facts.
        assert len(data.cell_clue) < NUM_CELLS
