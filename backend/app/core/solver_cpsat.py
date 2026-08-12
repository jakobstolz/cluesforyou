"""CP-SAT backed ground-truth checks: is a clue set satisfiable, and if so
is its solution unique? This is the mathematical backstop behind the
human-reasoning engine — the reasoner decides if a puzzle *feels*
solvable, CP-SAT decides if it's *actually* uniquely determined.
"""

from __future__ import annotations

from ortools.sat.python import cp_model

from backend.app.core.clues.base import Clue
from backend.app.core.types import ALL_CELLS, Cell, Solution


def build_model(clues: list[Clue]) -> tuple[cp_model.CpModel, dict[Cell, cp_model.IntVar]]:
    model = cp_model.CpModel()
    cell_vars = {c: model.NewBoolVar(f"c{c[0]}_{c[1]}") for c in ALL_CELLS}
    for clue in clues:
        clue.add_to_model(model, cell_vars)
    return model, cell_vars


def _new_solver() -> cp_model.CpSolver:
    """CP-SAT defaults to spinning up several parallel search workers, which
    is the right call for genuinely hard models but pure overhead for these
    - a model this size (NUM_CELLS boolean vars, a handful of linear
    constraints) solves in well under a millisecond single-threaded, while
    the default multi-worker setup was measured to cost ~15-20x more wall
    time on problems this tiny (worker spin-up dominating actual solve
    time). generate_puzzle calls this hundreds of times per attempt during
    pruning, so this was the single biggest generation-latency win found -
    bigger than any pool-size/attempt-budget tuning."""
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    return solver


def cpsat_solve_any(clues: list[Clue]) -> Solution | None:
    """Return any feasible solution consistent with `clues`, or None if the
    clue set is inconsistent (unsatisfiable)."""
    model, cell_vars = build_model(clues)
    solver = _new_solver()
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None
    return {c: bool(solver.Value(cell_vars[c])) for c in ALL_CELLS}


def cpsat_is_unique(clues: list[Clue]) -> bool:
    """True iff exactly one assignment of the 25 cells satisfies every
    clue: solve once, block that exact solution, solve again — the second
    solve must come back infeasible."""
    model, cell_vars = build_model(clues)
    solver = _new_solver()
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return False  # inconsistent clue set - not a valid (let alone unique) puzzle

    sol1 = {c: solver.Value(cell_vars[c]) for c in ALL_CELLS}
    diff_literals = [cell_vars[c] if sol1[c] == 0 else cell_vars[c].Not() for c in ALL_CELLS]
    model.Add(sum(diff_literals) >= 1)

    status2 = solver.Solve(model)
    return status2 == cp_model.INFEASIBLE
