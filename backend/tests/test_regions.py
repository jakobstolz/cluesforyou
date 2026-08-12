from backend.app.config import GRID_COLS, GRID_ROWS
from backend.app.core.types import (
    ALL_CELLS,
    all_neighbor_cells,
    corner_cells,
    diagonal_neighbor_cells,
    edge_cells,
    interior_cells,
    neighbor_cells,
)


def test_regions_partition_the_grid():
    corners, edges, interior = corner_cells(), edge_cells(), interior_cells()
    assert len(corners) == 4
    assert len(edges) == 2 * (GRID_ROWS - 2) + 2 * (GRID_COLS - 2)
    assert len(interior) == (GRID_ROWS - 2) * (GRID_COLS - 2)

    # A true partition: covers everything, no overlaps.
    assert set(corners) | set(edges) | set(interior) == set(ALL_CELLS)
    assert not (set(corners) & set(edges))
    assert not (set(corners) & set(interior))
    assert not (set(edges) & set(interior))


def test_corner_cells_are_the_four_extremes():
    last_row, last_col = GRID_ROWS - 1, GRID_COLS - 1
    assert set(corner_cells()) == {(0, 0), (0, last_col), (last_row, 0), (last_row, last_col)}


def test_edge_cells_are_border_minus_corners():
    edges = set(edge_cells())
    assert (0, 1) in edges  # top border, not a corner
    assert (2, 0) in edges  # left border, not a corner
    assert (0, 0) not in edges  # corner
    assert (2, 2) not in edges  # interior


def test_interior_cells_exclude_the_whole_border():
    interior = set(interior_cells())
    last_row, last_col = GRID_ROWS - 1, GRID_COLS - 1
    for r in range(GRID_ROWS):
        assert (r, 0) not in interior
        assert (r, last_col) not in interior
    for c in range(GRID_COLS):
        assert (0, c) not in interior
        assert (last_row, c) not in interior


def test_diagonal_neighbors_center_vs_corner():
    assert set(diagonal_neighbor_cells((2, 1))) == {(1, 0), (1, 2), (3, 0), (3, 2)}
    assert set(diagonal_neighbor_cells((0, 0))) == {(1, 1)}


def test_all_neighbor_cells_is_orthogonal_plus_diagonal():
    center_all = all_neighbor_cells((2, 1))
    assert len(center_all) == 8
    assert set(center_all) == set(neighbor_cells((2, 1))) | set(diagonal_neighbor_cells((2, 1)))

    corner_all = all_neighbor_cells((0, 0))
    assert len(corner_all) == 3
    assert set(corner_all) == set(neighbor_cells((0, 0))) | set(diagonal_neighbor_cells((0, 0)))
