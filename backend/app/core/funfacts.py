"""Cosmetic flavor-text pools for the progressive-reveal 'fun facts'.

These carry no logical information about the puzzle - they're purely a
reward shown when a correct guess doesn't unlock a new clue (see
core/reveal.py). Kept in their own module so wording can be freely
expanded without touching game logic.
"""

from __future__ import annotations

import random

INNOCENT_FACTS = [
    "{name} findet immer die besten {profession}-bezogenen Wortspiele auf Partys.",
    "{name} findet Annika und Jakob sind ein süßes Pärchen.",
    "{name} findet Annika schreibt die besten Gedichte über {profession}.",
    "Jakob hat {name} erzählt, dass er in Annika verliebt ist.",
    "Jakob hat {name} erzählt, dass Annika die schönste Person der Welt ist.",
    "Jakob hat {name} erzählt, dass Annika zu schlau für dieses Puzzle ist.",
    "{name} findet Annika und Jakob passen gut zusammen.",
    "Die Hauptstadt von Mali ist Bammako.",
    "Die Haupstadt von Turkmenistan ist Ashgabat.",
    "{name} findet Willy und Biene sehr süß.",
    "Die Haupstadt von Suriname ist Paramaribo.",
    "{name} denkt Annika ist eine sehr gute Freundin.",
    "{name}'s Lieblingsessen ist Gute Käse.",
    "{name} findet Jakob ist ein sehr guter Freund.",
]

CRIMINAL_FACTS = [
    "{name} ist bekannt dafür, oft zu flunkern.",
    "{name} denkt 67 ist extreeem lustig.",
    "{name} denkt Jakob hat sehr breite Füße.",
    "{name} denkt das Kollosseum ist in Athen.",
    "{name} glaubt an den Osterhasen.",
    "{name} wählt heimlich AfD.",
    "{name} ist neidisch auf Annika und Jakobs Beziehung.",
    "{name} ist neidisch auf Jakob, weil er so eine tolle Freundin hat.",
    "{name} denkt die Hauptstadt von Australien ist Sydney.",
    "{name} geht crashout wegen 5 cent.",
    "{name} steht auf Füße.",
]


def pick_funfact(name: str, profession: str, is_criminal: bool, used_keys: set[str]) -> str:
    """Pick a random not-yet-used-this-puzzle template and fill it in.
    `used_keys` is mutated in place to record the choice. If every
    template in the relevant pool has already been used this puzzle,
    repeats are allowed rather than erroring."""
    pool = CRIMINAL_FACTS if is_criminal else INNOCENT_FACTS
    prefix = "c" if is_criminal else "i"

    available = [i for i in range(len(pool)) if f"{prefix}{i}" not in used_keys]
    if not available:
        available = list(range(len(pool)))

    idx = random.choice(available)
    used_keys.add(f"{prefix}{idx}")
    return pool[idx].format(name=name, profession=profession)
