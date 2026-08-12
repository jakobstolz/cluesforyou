"""JSON-file-backed roster storage: the persistent, shared pool of
(name, profession) pairs a puzzle's grid cells are sampled from.

Read-modify-write the whole file on each call - simple and safe enough
for a single-household app with no concurrent writers; would want a real
datastore (or at least file locking) before hosting for real concurrent
multi-writer use (see README "Future: hosting").
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
ROSTER_PATH = DATA_DIR / "roster.json"

# The default roster - 25 (name, profession) pairs, more than the 20-cell
# grid needs, so a fresh subset gets sampled each generation for variety.
DEFAULT_ENTRIES: list[tuple[str, str]] = [
    ("Annika", "Dichterin"),
    ("Jakob", "Mathematiker"),
    ("Biene", "Politikerin"),
    ("Willy", "Comedian"),
    ("Ella", "Barkeeperin"),
    ("Tom", "DJ"),
    ("Dominik", "DJ"),
    ("Aileen", "Comedian"),
    ("Lee-Ann", "Barkeeperin"),
    ("Lilly", "Mathematikerin"),
    ("Julian", "Comedian"),
    ("Benita", "Politikerin"),
    ("Kim", "Mitbewohnerin"),
    ("Jannis", "Fußballer"),
    ("Sophia", "Fußballerin"),
    ("ACE Jonas", "Politiker"),
    ("Matthias", "Mitbewohner"),
    ("Tjark", "Mitbewohner"),
    ("Alina", "Barkeeperin"),
    ("Syd", "Pink Floyd"),
    ("Rogers", "Pink Floyd"),
    ("Richards", "Pink Floyd"),
    ("Nick", "Pink Floyd"),
    ("Beastboy", "Dichter"),
    ("Messi", "Fußballer"),
]


@dataclass
class RosterEntry:
    id: str
    name: str
    profession: str


class DuplicatePairError(ValueError):
    """Raised when adding/updating an entry would create a duplicate
    (name, profession) pair (case-insensitive)."""


def _default_entries() -> list[RosterEntry]:
    return [RosterEntry(id=uuid.uuid4().hex, name=n, profession=p) for n, p in DEFAULT_ENTRIES]


def _write(entries: list[RosterEntry]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ROSTER_PATH.write_text(json.dumps([asdict(e) for e in entries], indent=2), encoding="utf-8")


def load_roster() -> list[RosterEntry]:
    """Auto-seeds the file with 25 default entries on first ever read."""
    if not ROSTER_PATH.exists():
        entries = _default_entries()
        _write(entries)
        return entries
    raw = json.loads(ROSTER_PATH.read_text(encoding="utf-8"))
    return [RosterEntry(**item) for item in raw]


def _validate(name: str, profession: str) -> tuple[str, str]:
    name = name.strip()
    profession = profession.strip()
    if not name or not profession:
        raise ValueError("Name and profession must not be empty.")
    return name, profession


def _has_duplicate(
    entries: list[RosterEntry], name: str, profession: str, exclude_id: str | None = None
) -> bool:
    key = (name.lower(), profession.lower())
    return any((e.name.lower(), e.profession.lower()) == key for e in entries if e.id != exclude_id)


def add_entry(name: str, profession: str) -> RosterEntry:
    name, profession = _validate(name, profession)
    entries = load_roster()
    if _has_duplicate(entries, name, profession):
        raise DuplicatePairError(f"{name} the {profession} is already in the roster.")
    entry = RosterEntry(id=uuid.uuid4().hex, name=name, profession=profession)
    entries.append(entry)
    _write(entries)
    return entry


def update_entry(entry_id: str, name: str, profession: str) -> RosterEntry:
    name, profession = _validate(name, profession)
    entries = load_roster()
    target = next((e for e in entries if e.id == entry_id), None)
    if target is None:
        raise KeyError(entry_id)
    if _has_duplicate(entries, name, profession, exclude_id=entry_id):
        raise DuplicatePairError(f"{name} the {profession} is already in the roster.")
    target.name = name
    target.profession = profession
    _write(entries)
    return target


def delete_entry(entry_id: str) -> None:
    entries = load_roster()
    remaining = [e for e in entries if e.id != entry_id]
    if len(remaining) == len(entries):
        raise KeyError(entry_id)
    _write(remaining)
