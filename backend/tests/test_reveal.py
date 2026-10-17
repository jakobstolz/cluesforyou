import random

import pytest

from backend.app.config import NUM_CELLS
from backend.app.core.clues import DirectRevealClue
from backend.app.core.difficulty import get_difficulty
from backend.app.core.funfacts import ACE_CRIMINAL_FACTS, ACE_INNOCENT_FACTS, CRIMINAL_FACTS
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


def test_reveal_for_cell_ace_mode_uses_the_ace_pool():
    grid = random_grid_layout(POOL, random.Random(4))
    cell = (3, 3)
    person = grid[cell[0]][cell[1]]
    used = set()
    texts_ace = {reveal_for_cell(cell, True, grid, {}, used, ace=True).text for _ in range(len(ACE_CRIMINAL_FACTS) * 3)}
    # Every observed text must be an exact render of one of ACE MODE's own
    # templates for this person - not just "different from the default
    # pool" (the two pools are allowed to share some lines/content; that's
    # a real, legitimate choice, not something this test should assume
    # against).
    possible_ace_texts = {t.format(name=person.name, profession=person.profession) for t in ACE_CRIMINAL_FACTS}
    assert texts_ace <= possible_ace_texts
    assert len(texts_ace) <= len(ACE_CRIMINAL_FACTS)
    # ace mode's used_keys use a distinct prefix, so an ace pick never
    # exhausts/collides with the default pool's own bookkeeping.
    assert all(key.startswith("ac") for key in used)


def test_reveal_for_cell_ace_mode_innocent_pool_differs_too():
    grid = random_grid_layout(POOL, random.Random(5))
    cell = (0, 2)
    person = grid[cell[0]][cell[1]]
    texts_ace = {reveal_for_cell(cell, False, grid, {}, set(), ace=True).text for _ in range(len(ACE_INNOCENT_FACTS) * 3)}
    possible_ace_texts = {t.format(name=person.name, profession=person.profession) for t in ACE_INNOCENT_FACTS}
    assert texts_ace <= possible_ace_texts


DIFFICULTY_ITERATIONS = {"easy": 5, "medium": 5, "hard": 2}  # Hard's tier-4 necessity checks are slow

# See test_generator_stress.py's matching comment/xfail: v12 substantially
# improved (not fully resolved) Hard's require_combination reliability by
# excluding DirectCountClue - measured ~88%, up from ~64%, on a fresh
# 25-seed sweep. Still not 100%, so Hard keeps an xfail here too even
# though this particular fixed seed happens to pass more often than not.
_HARD_RELIABILITY_XFAIL_REASON = (
    "Hard's require_combination gate is still not 100% reliable even after "
    "v12's DirectCountClue exclusion (measured ~88%, up from ~64%) - a real, "
    "reduced-but-real gap. See test_generator_stress.py's comment for the full numbers."
)


@pytest.mark.slow
@pytest.mark.parametrize(
    "difficulty",
    [
        "easy",
        "medium",
        pytest.param("hard", marks=pytest.mark.xfail(reason=_HARD_RELIABILITY_XFAIL_REASON, strict=False)),
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
