import pytest
from fastapi.testclient import TestClient

from backend.app.config import GRID_COLS, GRID_ROWS, NUM_CELLS
from backend.app.core import roster as roster_store
from backend.app.core.funfacts import ACE_CRIMINAL_FACTS, ACE_INNOCENT_FACTS
from backend.app.main import app
from backend.app.state import PUZZLES

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_roster(tmp_path, monkeypatch):
    """Every test gets a fresh, isolated roster file (default and ACE MODE
    alike), auto-seeded with their own defaults on first read (see
    core/roster.py)."""
    monkeypatch.setattr(roster_store, "DATA_DIR", tmp_path)
    monkeypatch.setattr(roster_store, "ROSTER_PATH", tmp_path / "roster.json")
    monkeypatch.setattr(roster_store, "ACE_ROSTER_PATH", tmp_path / "roster_ace.json")
    yield


def _generate(difficulty="easy", ace_mode=False):
    resp = client.post("/api/puzzle", json={"difficulty": difficulty, "ace_mode": ace_mode})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_health():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ---------- Roster ----------


def test_roster_get_auto_seeds_defaults():
    resp = client.get("/api/roster")
    assert resp.status_code == 200
    people = resp.json()["people"]
    assert len(people) == len(roster_store.DEFAULT_ENTRIES)
    assert all({"id", "name", "profession"} == set(p.keys()) for p in people)


def test_roster_add_and_delete():
    resp = client.post("/api/roster", json={"name": "Fiona", "profession": "Pilot"})
    assert resp.status_code == 201
    entry = resp.json()

    resp2 = client.get("/api/roster")
    assert any(p["id"] == entry["id"] for p in resp2.json()["people"])

    resp3 = client.delete(f"/api/roster/{entry['id']}")
    assert resp3.status_code == 204

    resp4 = client.get("/api/roster")
    assert all(p["id"] != entry["id"] for p in resp4.json()["people"])


def test_roster_add_rejects_duplicate_pair():
    client.post("/api/roster", json={"name": "Fiona", "profession": "Pilot"})
    resp = client.post("/api/roster", json={"name": "fiona", "profession": "PILOT"})
    assert resp.status_code == 422


def test_roster_add_rejects_empty_fields():
    resp = client.post("/api/roster", json={"name": "  ", "profession": "Pilot"})
    assert resp.status_code == 422


def test_roster_update():
    entry = client.post("/api/roster", json={"name": "Fiona", "profession": "Pilot"}).json()
    resp = client.put(f"/api/roster/{entry['id']}", json={"name": "Fiona", "profession": "Astronaut"})
    assert resp.status_code == 200
    assert resp.json()["profession"] == "Astronaut"


def test_roster_update_unknown_id_404():
    resp = client.put("/api/roster/does-not-exist", json={"name": "A", "profession": "B"})
    assert resp.status_code == 404


def test_roster_delete_unknown_id_404():
    resp = client.delete("/api/roster/does-not-exist")
    assert resp.status_code == 404


# ---------- Puzzle ----------


def test_create_puzzle_shape_and_no_solution_leak():
    data = _generate("easy")
    assert "puzzle_id" in data
    assert len(data["grid"]) == GRID_ROWS
    assert all(len(row) == GRID_COLS for row in data["grid"])
    assert set(data["starter"].keys()) == {"row", "col", "status"}
    assert set(data["first_clue"].keys()) == {"id", "text", "tier"}
    assert data["difficulty"] == "easy"

    grid_cells = [cell for row in data["grid"] for cell in row]
    # Grid cells only ever expose identity (name/profession/position), never status.
    assert all(set(cell.keys()) == {"row", "col", "name", "profession"} for cell in grid_cells)
    pairs = {(c["name"], c["profession"]) for c in grid_cells}
    assert len(pairs) == NUM_CELLS


def test_create_puzzle_rejects_bad_difficulty():
    resp = client.post("/api/puzzle", json={"difficulty": "impossible"})
    assert resp.status_code == 422


def test_create_puzzle_rejects_undersized_roster():
    people = client.get("/api/roster").json()["people"]
    # Shrink the roster below the NUM_CELLS-person minimum.
    for entry in people[: len(people) - NUM_CELLS + 1]:
        client.delete(f"/api/roster/{entry['id']}")
    resp = client.post("/api/puzzle", json={"difficulty": "easy"})
    assert resp.status_code == 422
    assert "roster" in resp.json()["detail"].lower()


def test_full_playthrough_via_api():
    data = _generate("easy")
    puzzle_id = data["puzzle_id"]
    record = PUZZLES[puzzle_id]  # test-only peek at the true state to drive + verify the walkthrough
    solution = record.solution

    starter_cell = (data["starter"]["row"], data["starter"]["col"])
    known = {starter_cell}
    remaining = [cell for cell in solution if cell not in known]

    solved = False
    for row, col in remaining:
        cell = (row, col)
        guess = "criminal" if solution[cell] else "innocent"
        resp = client.post(
            "/api/guess", json={"puzzle_id": puzzle_id, "row": row, "col": col, "guess": guess}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["correct"] is True

        # The core new invariant: each cell's reveal matches EXACTLY what
        # was permanently attached to that cell at generation time.
        if not body["solved"]:
            reveal = body["reveal"]
            if cell in record.cell_clue:
                assert reveal["kind"] == "clue"
                assert reveal["text"] == record.cell_clue[cell].text
            else:
                assert reveal["kind"] == "funfact"

        if body["solved"]:
            solved = True

    assert solved is True


def test_wrong_guess_does_not_change_state():
    data = _generate("easy")
    puzzle_id = data["puzzle_id"]
    record = PUZZLES[puzzle_id]
    starter_cell = (data["starter"]["row"], data["starter"]["col"])
    cell = next(c for c in record.solution if c != starter_cell)
    wrong_guess = "innocent" if record.solution[cell] else "criminal"

    resp = client.post(
        "/api/guess",
        json={"puzzle_id": puzzle_id, "row": cell[0], "col": cell[1], "guess": wrong_guess},
    )
    body = resp.json()
    assert body["correct"] is False
    assert body["reveal"] is None
    assert cell not in record.known_correct


def test_reclicking_solved_cell_is_idempotent():
    data = _generate("easy")
    puzzle_id = data["puzzle_id"]
    record = PUZZLES[puzzle_id]
    row, col = data["starter"]["row"], data["starter"]["col"]
    guess = "criminal" if record.solution[(row, col)] else "innocent"

    resp1 = client.post("/api/guess", json={"puzzle_id": puzzle_id, "row": row, "col": col, "guess": guess})
    resp2 = client.post("/api/guess", json={"puzzle_id": puzzle_id, "row": row, "col": col, "guess": guess})
    assert resp1.json()["correct"] is True
    assert resp2.json()["correct"] is True
    assert resp2.json()["reveal"] is None  # no double reveal for re-clicking an already-locked cell


def test_guess_unknown_puzzle_id_404():
    resp = client.post(
        "/api/guess", json={"puzzle_id": "does-not-exist", "row": 0, "col": 0, "guess": "criminal"}
    )
    assert resp.status_code == 404


def test_hint_unknown_puzzle_id_404():
    resp = client.post("/api/hint", json={"puzzle_id": "does-not-exist"})
    assert resp.status_code == 404


def test_hint_fills_a_cell_matching_the_solution_and_its_own_reveal():
    data = _generate("easy")
    puzzle_id = data["puzzle_id"]
    record = PUZZLES[puzzle_id]

    # Hint is bounded to clues attached to already-identified cells, so
    # right at puzzle start it can legitimately have nothing to offer yet.
    # Feed correct guesses (as a real player eventually would) until either
    # hint has something, or the puzzle solves itself in the process.
    body = {"available": False}
    for cell in record.solution:
        resp = client.post("/api/hint", json={"puzzle_id": puzzle_id})
        assert resp.status_code == 200
        body = resp.json()
        if body["available"] or len(record.known_correct) == NUM_CELLS:
            break
        if cell in record.known_correct:
            continue
        guess = "criminal" if record.solution[cell] else "innocent"
        client.post("/api/guess", json={"puzzle_id": puzzle_id, "row": cell[0], "col": cell[1], "guess": guess})

    assert body["available"] is True
    cell = (body["row"], body["col"])
    expected_status = "criminal" if record.solution[cell] else "innocent"
    assert body["value"] == expected_status
    assert body["reason"]
    assert cell in record.known_correct

    if not body["solved"]:
        assert body["reveal"] is not None
        if cell in record.cell_clue:
            assert body["reveal"]["kind"] == "clue"
            assert body["reveal"]["text"] == record.cell_clue[cell].text
        else:
            assert body["reveal"]["kind"] == "funfact"


# ---------- ACE MODE ----------


def test_ace_roster_is_independent_of_default_roster():
    default_people = client.get("/api/roster").json()["people"]
    ace_people = client.get("/api/roster?ace=true").json()["people"]
    # Each mode seeds from its OWN defaults - checked by exact (name,
    # profession) content, not by assuming the two lists share no names
    # (they're allowed to - e.g. the same person appearing in both with a
    # different profession is a legitimate, real scenario here).
    assert {(p["name"], p["profession"]) for p in default_people} == set(roster_store.DEFAULT_ENTRIES)
    assert {(p["name"], p["profession"]) for p in ace_people} == set(roster_store.ACE_DEFAULT_ENTRIES)


def test_ace_roster_add_update_delete_do_not_touch_default_roster():
    default_before = client.get("/api/roster").json()["people"]

    created = client.post("/api/roster?ace=true", json={"name": "Fiona", "profession": "Pilot"})
    assert created.status_code == 201
    entry = created.json()

    assert any(p["id"] == entry["id"] for p in client.get("/api/roster?ace=true").json()["people"])
    assert all(p["id"] != entry["id"] for p in client.get("/api/roster").json()["people"])

    updated = client.put(f"/api/roster/{entry['id']}?ace=true", json={"name": "Fiona", "profession": "Astronaut"})
    assert updated.status_code == 200
    assert updated.json()["profession"] == "Astronaut"

    deleted = client.delete(f"/api/roster/{entry['id']}?ace=true")
    assert deleted.status_code == 204
    assert all(p["id"] != entry["id"] for p in client.get("/api/roster?ace=true").json()["people"])

    # The default roster was never touched by any of the above.
    assert client.get("/api/roster").json()["people"] == default_before


def test_create_puzzle_in_ace_mode_uses_the_ace_roster():
    data = _generate("easy", ace_mode=True)
    ace_names = {name for name, _ in roster_store.ACE_DEFAULT_ENTRIES}
    grid_names = {cell["name"] for row in data["grid"] for cell in row}
    assert grid_names <= ace_names

    puzzle_id = data["puzzle_id"]
    record = PUZZLES[puzzle_id]
    assert record.ace is True


def test_create_puzzle_without_ace_mode_uses_the_default_roster():
    data = _generate("easy")
    default_names = {name for name, _ in roster_store.DEFAULT_ENTRIES}
    grid_names = {cell["name"] for row in data["grid"] for cell in row}
    assert grid_names <= default_names

    puzzle_id = data["puzzle_id"]
    record = PUZZLES[puzzle_id]
    assert record.ace is False


def test_ace_mode_guess_reveals_come_from_the_ace_funfact_pool():
    data = _generate("easy", ace_mode=True)
    puzzle_id = data["puzzle_id"]
    record = PUZZLES[puzzle_id]
    starter_cell = (data["starter"]["row"], data["starter"]["col"])
    # Any cell without its own attached clue reveals a fun fact on a
    # correct guess - find one and confirm the EXACT text is one this
    # person's name/profession could only have produced from ACE MODE's
    # own pool, not the default one (rendering every template directly,
    # not prefix-matching - every template here starts with "{name}").
    fun_fact_cell = next(c for c in record.solution if c != starter_cell and c not in record.cell_clue)
    guess = "criminal" if record.solution[fun_fact_cell] else "innocent"
    resp = client.post(
        "/api/guess",
        json={"puzzle_id": puzzle_id, "row": fun_fact_cell[0], "col": fun_fact_cell[1], "guess": guess},
    )
    body = resp.json()
    assert body["reveal"]["kind"] == "funfact"

    person = record.layout[fun_fact_cell[0]][fun_fact_cell[1]]
    ace_pool = ACE_CRIMINAL_FACTS if guess == "criminal" else ACE_INNOCENT_FACTS
    possible_ace_texts = {t.format(name=person.name, profession=person.profession) for t in ace_pool}
    assert body["reveal"]["text"] in possible_ace_texts
