"""JSON-file-backed roster storage: the persistent, shared pool of
(name, profession) pairs a puzzle's grid cells are sampled from.

Read-modify-write the whole file on each call - simple and safe enough
for a single-household app with no concurrent writers; would want a real
datastore (or at least file locking) before hosting for real concurrent
multi-writer use (see README "Future: hosting").

Two independent roster "modes" exist side by side - the normal default
roster, and ACE MODE's own roster (see frontend's ACE MODE button) - each
backed by its own JSON file, auto-seeded from its own default entries,
and otherwise managed through the exact same functions/API. Neither
affects the other; switching modes just points every roster call at a
different file.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

RosterMode = Literal["default", "ace"]

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
ROSTER_PATH = DATA_DIR / "roster.json"
ACE_ROSTER_PATH = DATA_DIR / "roster_ace.json"

# The default roster - more entries than the 20-cell grid needs, so a
# fresh subset gets sampled each generation for variety.
DEFAULT_ENTRIES: list[tuple[str, str]] = [
    ("Annika", "Dichterin"),
    ("Jakob", "Mathematiker"),
    ("Biene", "Politikerin"),
    ("Willy", "Comedian"),
    ("Ella", "Barkeeperin"),
    ("Tom", "DJ"),
    ("Dominik", "DJ"),
    ("Aileen", "Erfinderin"),
    ("Lee-Ann", "Barkeeperin"),
    ("Lilly", "Mathematikerin"),
    ("Julian", "Comedian"),
    ("Benita", "Politikerin"),
    ("Kim", "Mitbewohnerin"),
    ("Jannis", "Fußballer"),
    ("Michelle", "Fußballerin"),
    ("ACE Jonas", "Politiker"),
    ("Matthias", "Mitbewohner"),
    ("Tjark", "Mitbewohner"),
    ("Alina", "Barkeeperin"),
    ("Syd", "Pink Floyd"),
    ("Rogers", "Pink Floyd"),
    ("Richard", "Pink Floyd"),
    ("Nick", "Pink Floyd"),
    ("Beastboy", "Dichter"),
    ("Messi", "Fußballer"),
    ("Kronos" , "Erfinder")
]

# PLACEHOLDER - a simple, clearly-generic card-themed roster so ACE MODE
# works end to end immediately. Swap this out (or just edit it in-app via
# "Manage roster" once ACE MODE is on - it's independently editable, same
# as the default roster) with real content whenever ready.
ACE_DEFAULT_ENTRIES: list[tuple[str, str]] = [
    ("Ace Jonas", "Kanzler"),
    ("Katha", "Lokführerin"),
    ("Andi", "Stewardess"),
    ("Jakob", "Biertrinker"),
    ("Babsi", "Englischlehrerin"),
    ("Warzel", "Englischlehrerin"),
    ("Flad", "Motivationscoach"),
    ("Bornemann", "Gravedigger"),
    ("Lindemann", "Comedian"),
    ("Kemper", "Biertrinker"),
    ("Kienberger", "Biertrinker"),
    ("Cerys", "Lokfühererin"),
    ("Angelika", "Englischlehrerin"),
    ("CF Krainer", "Gravedigger"),
    ("Elisabeth", "Stewardess"),
    ("Konsti", "Stewardess"),
    ("Blacky", "Motivationscoach"),
    ("Basti", "Comedian"),
    ("Giulia", "Gravedigger"),
    ("Viola", "Kanzlerin"),
    ("FL Bauer", "Erfinder"),
    ("Fabian Reimers", "Lokführer"),
    ("Jürgen", "Erfinder"),
]


@dataclass
class RosterEntry:
    id: str
    name: str
    profession: str


class DuplicatePairError(ValueError):
    """Raised when adding/updating an entry would create a duplicate
    (name, profession) pair (case-insensitive)."""


def _path_for(mode: RosterMode) -> Path:
    return ACE_ROSTER_PATH if mode == "ace" else ROSTER_PATH


def _defaults_for(mode: RosterMode) -> list[tuple[str, str]]:
    return ACE_DEFAULT_ENTRIES if mode == "ace" else DEFAULT_ENTRIES


def _default_entries(mode: RosterMode = "default") -> list[RosterEntry]:
    return [RosterEntry(id=uuid.uuid4().hex, name=n, profession=p) for n, p in _defaults_for(mode)]


def _write(entries: list[RosterEntry], mode: RosterMode = "default") -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _path_for(mode).write_text(json.dumps([asdict(e) for e in entries], indent=2), encoding="utf-8")


def load_roster(mode: RosterMode = "default") -> list[RosterEntry]:
    """Auto-seeds the file with this mode's default entries on first ever read."""
    path = _path_for(mode)
    if not path.exists():
        entries = _default_entries(mode)
        _write(entries, mode)
        return entries
    raw = json.loads(path.read_text(encoding="utf-8"))
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


def add_entry(name: str, profession: str, mode: RosterMode = "default") -> RosterEntry:
    name, profession = _validate(name, profession)
    entries = load_roster(mode)
    if _has_duplicate(entries, name, profession):
        raise DuplicatePairError(f"{name} the {profession} is already in the roster.")
    entry = RosterEntry(id=uuid.uuid4().hex, name=name, profession=profession)
    entries.append(entry)
    _write(entries, mode)
    return entry


def update_entry(entry_id: str, name: str, profession: str, mode: RosterMode = "default") -> RosterEntry:
    name, profession = _validate(name, profession)
    entries = load_roster(mode)
    target = next((e for e in entries if e.id == entry_id), None)
    if target is None:
        raise KeyError(entry_id)
    if _has_duplicate(entries, name, profession, exclude_id=entry_id):
        raise DuplicatePairError(f"{name} the {profession} is already in the roster.")
    target.name = name
    target.profession = profession
    _write(entries, mode)
    return target


def delete_entry(entry_id: str, mode: RosterMode = "default") -> None:
    entries = load_roster(mode)
    remaining = [e for e in entries if e.id != entry_id]
    if len(remaining) == len(entries):
        raise KeyError(entry_id)
    _write(remaining, mode)
