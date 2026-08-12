import random

import pytest

from backend.app.config import GRID_COLS, GRID_ROWS, NUM_CELLS
from backend.app.core.grid import random_grid_layout
from backend.app.core.solution import MAX_CRIMINALS, MIN_CRIMINALS, random_solution
from backend.app.core.types import ALL_CELLS, Person, neighbor_cells


NAMES = [
    "Alice", "Bob", "Carl", "Dana", "Eli", "Fay", "Gus", "Hana", "Ivo", "Jill",
    "Kian", "Lea", "Milo", "Nia", "Omar", "Pia", "Quinn", "Rex", "Sara", "Theo",
]  # 20 distinct names, matches NUM_CELLS - a generated grid never repeats a name
PROFESSIONS = ["Chef", "Cop", "Doctor", "Teacher", "Engineer"]
POOL_20 = [Person(NAMES[i], PROFESSIONS[i % len(PROFESSIONS)]) for i in range(len(NAMES))]
POOL_35 = POOL_20 + [Person(f"Extra{i}", f"Job{i}") for i in range(15)]  # a pool bigger than 20


def test_grid_layout_uses_all_entries_when_pool_is_exactly_num_cells():
    rng = random.Random(42)
    grid = random_grid_layout(POOL_20, rng)
    assert len(grid) == GRID_ROWS
    assert all(len(row) == GRID_COLS for row in grid)

    pairs = [grid[r][c] for r in range(GRID_ROWS) for c in range(GRID_COLS)]
    assert len(set(pairs)) == NUM_CELLS
    assert set(pairs) == set(POOL_20)


def test_grid_layout_samples_from_a_larger_pool():
    rng = random.Random(3)
    grid = random_grid_layout(POOL_35, rng)
    pairs = [grid[r][c] for r in range(GRID_ROWS) for c in range(GRID_COLS)]
    assert len(set(pairs)) == NUM_CELLS
    assert set(pairs) <= set(POOL_35)


def test_grid_layout_varies_across_calls():
    rng = random.Random(1)
    g1 = random_grid_layout(POOL_20, rng)
    g2 = random_grid_layout(POOL_20, rng)
    assert g1 != g2


def test_grid_layout_rejects_too_small_pool():
    with pytest.raises(ValueError):
        random_grid_layout(POOL_20[: NUM_CELLS - 1], random.Random(0))


def test_random_solution_covers_all_cells_and_respects_bounds():
    rng = random.Random(7)
    for ratio in (0.0, 0.2, 0.5, 0.8, 1.0):
        sol = random_solution(ratio, rng)
        assert set(sol.keys()) == set(ALL_CELLS)
        n_criminals = sum(sol.values())
        assert MIN_CRIMINALS <= n_criminals <= MAX_CRIMINALS


def test_neighbor_cells_are_orthogonal_and_in_bounds():
    last_row, last_col = GRID_ROWS - 1, GRID_COLS - 1
    assert set(neighbor_cells((0, 0))) == {(0, 1), (1, 0)}
    assert set(neighbor_cells((2, 1))) == {(1, 1), (3, 1), (2, 0), (2, 2)}
    assert set(neighbor_cells((last_row, last_col))) == {(last_row - 1, last_col), (last_row, last_col - 1)}
