import pytest

from backend.app.core import roster


@pytest.fixture(autouse=True)
def isolated_roster(tmp_path, monkeypatch):
    """Point roster storage at a throwaway directory for every test."""
    monkeypatch.setattr(roster, "DATA_DIR", tmp_path)
    monkeypatch.setattr(roster, "ROSTER_PATH", tmp_path / "roster.json")
    monkeypatch.setattr(roster, "ACE_ROSTER_PATH", tmp_path / "roster_ace.json")
    yield


def test_load_roster_auto_seeds_defaults_on_first_read():
    entries = roster.load_roster()
    assert len(entries) == len(roster.DEFAULT_ENTRIES)
    assert len({(e.name, e.profession) for e in entries}) == len(roster.DEFAULT_ENTRIES)
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


# ---------- ACE MODE: a second, independent roster profile ----------


def test_ace_mode_has_its_own_defaults_and_file():
    entries = roster.load_roster("ace")
    assert len(entries) == len(roster.ACE_DEFAULT_ENTRIES)
    assert len({(e.name, e.profession) for e in entries}) == len(roster.ACE_DEFAULT_ENTRIES)
    assert roster.ACE_ROSTER_PATH.exists()
    assert not roster.ROSTER_PATH.exists()  # default roster untouched by an ace-only call


def test_ace_mode_is_independent_of_the_default_roster():
    roster.add_entry("Fiona", "Pilot")  # default mode
    roster.add_entry("Gus", "Baker", mode="ace")

    default_names = {e.name for e in roster.load_roster()}
    ace_names = {e.name for e in roster.load_roster("ace")}
    assert "Fiona" in default_names and "Fiona" not in ace_names
    assert "Gus" in ace_names and "Gus" not in default_names


def test_ace_mode_update_and_delete_do_not_touch_default_roster():
    default_entry = roster.add_entry("Fiona", "Pilot")
    ace_entry = roster.add_entry("Fiona", "Pilot", mode="ace")  # same pair, different profile - allowed

    roster.update_entry(ace_entry.id, "Fiona", "Astronaut", mode="ace")
    reloaded_default = roster.load_roster()
    reloaded_ace = roster.load_roster("ace")
    assert next(e for e in reloaded_default if e.id == default_entry.id).profession == "Pilot"
    assert next(e for e in reloaded_ace if e.id == ace_entry.id).profession == "Astronaut"

    roster.delete_entry(ace_entry.id, mode="ace")
    assert all(e.id != ace_entry.id for e in roster.load_roster("ace"))
    assert any(e.id == default_entry.id for e in roster.load_roster())
