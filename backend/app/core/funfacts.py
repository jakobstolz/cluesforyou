"""Cosmetic flavor-text pools for the progressive-reveal 'fun facts'.

These carry no logical information about the puzzle - they're purely a
reward shown when a correct guess doesn't unlock a new clue (see
core/reveal.py). Kept in their own module so wording can be freely
expanded without touching game logic.

Two independent pools exist: the default one, and ACE MODE's own (see
frontend's ACE MODE button) - picking which applies is the caller's job
(core/reveal.py), not this module's.
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

# PLACEHOLDER - ACE MODE's own fun-fact pools, mirroring the same
# {name}/{profession}-template shape as the default pools above but with
# generic, inside-joke-free text so the mode works end to end immediately.
# Unlike the roster, these aren't editable in-app - swap the text below
# whenever real content is ready.
ACE_INNOCENT_FACTS = [
    "{name} gewinnt verdächtig oft beim Watten.",
    "{name} bluffed nie, nur strategisches Schweigen.",
    "{name} hat ein Pokerface, das selbst Profis neidisch macht.",
    "{name} sticht an Spitz dant.",
    "{name} mischt die Karten dreimal aus Aberglaube.",
    "{name}'s Lieblingskarte ist der Graß Unter.",
    "{name} denkt der erste Stich ist heilig.",
    "{name} kennt alle Regeln, spielt aber trotzdem nach Gefühl.",
    "{name} feiert jeden Gewinn, egal wie klein.",
    "{name} lässt beim Watten die 6er drin.",
    "{name} ist {profession} aus Leidenscahft.",
]

ACE_CRIMINAL_FACTS = [
    "{name} markiert heimlich den Maxi.",
    "{name} schaut beim {profession}-Sein gerne über die Schulter.",
    "{name} zählt Karten, obwohl wir Watten.",
    "{name} behauptet, noch nie verloren zu haben.",
    "{name} hebt nochmal ab, wenn keiner hinschaut.",
    "{name} bluffed selbst beim Fischer Seppi.",
    "{name} hat ein Ktitischen im Ärmel.",
    "{name} schummelt beim Mischen.",
    "{name} nimmt sich heimlich einen Chip mehr.",
    "{name} behauptet, der Dealer sei bestochen.",
    "{name} glaubt an den Osterhasen.",
    "{name} wählt heimlich AfD.",
    "{name} geht crashout wegen 5 cent.",
    "{name} steht auf Füße.",
    "{name} ist {profession} nur wegen der Kohle.",
]


def pick_funfact(name: str, profession: str, is_criminal: bool, used_keys: set[str], ace: bool = False) -> str:
    """Pick a random not-yet-used-this-puzzle template and fill it in.
    `used_keys` is mutated in place to record the choice. If every
    template in the relevant pool has already been used this puzzle,
    repeats are allowed rather than erroring. `ace` selects ACE MODE's
    own pool instead of the default one - the two never share `used_keys`
    entries (different prefix), which doesn't matter in practice (a given
    puzzle is always entirely one mode or the other) but keeps the
    bookkeeping honest either way."""
    if ace:
        pool = ACE_CRIMINAL_FACTS if is_criminal else ACE_INNOCENT_FACTS
        prefix = "ac" if is_criminal else "ai"
    else:
        pool = CRIMINAL_FACTS if is_criminal else INNOCENT_FACTS
        prefix = "c" if is_criminal else "i"

    available = [i for i in range(len(pool)) if f"{prefix}{i}" not in used_keys]
    if not available:
        available = list(range(len(pool)))

    idx = random.choice(available)
    used_keys.add(f"{prefix}{idx}")
    return pool[idx].format(name=name, profession=profession)
