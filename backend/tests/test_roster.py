import pytest

from backend.app.core import roster


@pytest.fixture(autouse=True)
def isolated_roster(tmp_path, monkeypatch):
    """Point roster storage at a throwaway directory for every test."""
    monkeypatch.setattr(roster, "DATA_DIR", tmp_path)
    monkeypatch.setattr(roster, "ROSTER_PATH", tmp_path / "roster.json")
    yield


def test_load_roster_auto_seeds_25_defaults_on_first_read():
    entries = roster.load_roster()
    assert len(entries) == 25
    assert len({(e.name, e.profession) for e in entries}) == 25
    assert roster.ROSTER_PATH.exists()


def test_load_roster_is_stable_across_calls():
    first = roster.load_roster()
    second = roster.load_roster()
    assert [e.id for e in first] == [e.id for e in second]


def test_add_entry_persists_and_is_visible_on_reload():
    entry = roster.add_entry("Fiona", "Pilot")
    assert entry.name == "Fiona"
    assert entry.profession == "Pilot"
    reloaded = roster.load_roster()
    assert any(e.id == entry.id for e in reloaded)


def test_add_entry_trims_whitespace():
    entry = roster.add_entry("  Gus  ", "  Baker  ")
    assert entry.name == "Gus"
    assert entry.profession == "Baker"


def test_add_entry_rejects_empty_fields():
    with pytest.raises(ValueError):
        roster.add_entry("  ", "Baker")
    with pytest.raises(ValueError):
        roster.add_entry("Gus", "  ")


def test_add_entry_rejects_duplicate_pair_case_insensitive():
    roster.add_entry("Fiona", "Pilot")
    with pytest.raises(roster.DuplicatePairError):
        roster.add_entry("fiona", "PILOT")


def test_add_entry_allows_repeated_name_or_profession_alone():
    roster.add_entry("Fiona", "Pilot")
    # Same name, different profession - fine.
    entry2 = roster.add_entry("Fiona", "Baker")
    assert entry2.profession == "Baker"


def test_update_entry_changes_fields():
    entry = roster.add_entry("Fiona", "Pilot")
    updated = roster.update_entry(entry.id, "Fiona", "Astronaut")
    assert updated.profession == "Astronaut"
    reloaded = roster.load_roster()
    match = next(e for e in reloaded if e.id == entry.id)
    assert match.profession == "Astronaut"


def test_update_entry_unknown_id_raises_keyerror():
    with pytest.raises(KeyError):
        roster.update_entry("does-not-exist", "A", "B")


def test_update_entry_rejects_duplicate_pair_with_another_entry():
    a = roster.add_entry("Fiona", "Pilot")
    roster.add_entry("Gus", "Baker")
    with pytest.raises(roster.DuplicatePairError):
        roster.update_entry(a.id, "Gus", "Baker")


def test_update_entry_allows_keeping_its_own_pair():
    a = roster.add_entry("Fiona", "Pilot")
    updated = roster.update_entry(a.id, "Fiona", "Pilot")
    assert updated.id == a.id


def test_delete_entry_removes_it():
    entry = roster.add_entry("Fiona", "Pilot")
    roster.delete_entry(entry.id)
    reloaded = roster.load_roster()
    assert all(e.id != entry.id for e in reloaded)


def test_delete_entry_unknown_id_raises_keyerror():
    with pytest.raises(KeyError):
        roster.delete_entry("does-not-exist")
