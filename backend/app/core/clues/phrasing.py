"""Randomized natural-language phrasing pools for each clue flavor.

Clue text is in German (buttons/dialog chrome, fun facts, and everything
else stay English - see core/funfacts.py and the frontend). Wording is
approximate, not grammatically polished - kept separate from the clue
classes so it can be tuned/expanded without touching
evaluation/propagation/CP-SAT logic.

Every function here takes an optional `rng` (a `random.Random` instance)
used for template selection - defaults to the global `random` module when
omitted (fine for anything that doesn't care about determinism, e.g. most
of the test suite). Clue subclasses pass their own `self._rng` (see
clues/base.py) - the same per-generation instance threaded through
generator.py - so wording variety is a deterministic function of the
puzzle's seed too, not just its layout/solution/clue-set. Never use the
bare `random` module directly in this file for that reason.
"""

from __future__ import annotations

import random

from backend.app.core.types import Grid, ScopeKind, identity_text, profession_group_label

DIRECT_TEMPLATES = [
    "{identity} ist {status}.",
    "Bestätigt: {identity} ist {status}.",
    "Wir wissen mit Sicherheit: {identity} ist {status}.",
]


def direct_clue_text(identity: str, is_criminal: bool, rng: random.Random | None = None) -> str:
    rng = rng if rng is not None else random
    status = "kriminell" if is_criminal else "unschuldig"
    return rng.choice(DIRECT_TEMPLATES).format(identity=identity, status=status)


_NEIGHBOR_DIRECT_TEMPLATES = {
    True: [
        "{identity} ist eine(r) von {neighbor}s kriminellen Nachbarn.",
        "{identity} gehört zu {neighbor}s kriminellen Nachbarn.",
    ],
    False: [
        "{identity} ist eine(r) von {neighbor}s unschuldigen Nachbarn.",
        "{identity} gehört zu {neighbor}s unschuldigen Nachbarn.",
    ],
}


def neighbor_direct_clue_text(
    identity: str, neighbor_identity: str, is_criminal: bool, rng: random.Random | None = None
) -> str:
    rng = rng if rng is not None else random
    template = rng.choice(_NEIGHBOR_DIRECT_TEMPLATES[is_criminal])
    return template.format(identity=identity, neighbor=neighbor_identity)


_GROUP_TEMPLATES_ZERO = [
    "Niemand {group} ist kriminell.",
    "Alle {group} sind unschuldig.",
]
_GROUP_TEMPLATES_FULL = [
    "Alle {group} sind kriminell.",
    "Niemand {group} ist unschuldig.",
]
_GROUP_TEMPLATES_GENERAL = [
    "Genau {target} der Personen {group} sind kriminell.",
    "Es gibt genau {target} Kriminelle {group}.",
    "{target} von {n} Personen {group} sind kriminell.",
]

PAIR_TEMPLATES = {
    0: ["Weder {a} noch {b} ist kriminell.", "{a} und {b} sind beide unschuldig."],
    1: [
        "Genau eine(r) von {a} und {b} ist kriminell.",
        "Einer von {a} und {b} ist kriminell, der/die andere unschuldig.",
    ],
    2: ["{a} und {b} sind beide kriminell.", "Weder {a} noch {b} ist unschuldig."],
}


def _group_phrase(group: str, target: int, n: int, rng: random.Random) -> str:
    if target == 0:
        template = rng.choice(_GROUP_TEMPLATES_ZERO)
    elif target == n:
        template = rng.choice(_GROUP_TEMPLATES_FULL)
    else:
        template = rng.choice(_GROUP_TEMPLATES_GENERAL)
    return template.format(group=group, target=target, n=n)


def _describe_scope(clue, grid: Grid) -> str:
    """A phrase like 'in Reihe 2' or 'unter Alice (Chef)s Nachbarn'
    describing a clue's scope, driven by scope_kind/index. Shared between
    count and parity phrasing (CUSTOM_PAIR is handled separately by each -
    its phrasing names the two people directly rather than describing a
    group). Doesn't itself pick between template variants, so it needs
    no rng."""
    kind = clue.scope_kind
    if kind == ScopeKind.ROW:
        return f"in Reihe {clue.index + 1}"
    if kind == ScopeKind.COL:
        return f"in Spalte {clue.index + 1}"
    if kind == ScopeKind.NAME:
        return f"namens {clue.index}"
    if kind == ScopeKind.PROFESSION:
        return f"unter den {profession_group_label(grid, clue.index)}"
    if kind == ScopeKind.GLOBAL:
        return "im gesamten Raster"
    if kind == ScopeKind.NEIGHBOR:
        # Unreachable today (count_clue_text/parity_clue_text both
        # special-case NEIGHBOR before ever reaching this fallback) -
        # kept correct anyway in case a future caller hits it directly.
        return f"unter {identity_text(grid, clue.index)}s Nachbarn"
    if kind == ScopeKind.ROW_NEIGHBOR:
        row, anchor = clue.index
        return f"in Reihe {row + 1} unter {identity_text(grid, anchor)}s Nachbarn"
    if kind == ScopeKind.COL_NEIGHBOR:
        col, anchor = clue.index
        return f"in Spalte {col + 1} unter {identity_text(grid, anchor)}s Nachbarn"
    if kind == ScopeKind.CORNER:
        return "in einer Ecke"
    if kind == ScopeKind.EDGE:
        return "am Rand (keine Ecke)"
    if kind == ScopeKind.INTERIOR:
        return "im Inneren"
    if kind == ScopeKind.ABOVE:
        return f"über {identity_text(grid, clue.index)}"
    if kind == ScopeKind.BELOW:
        return f"unter {identity_text(grid, clue.index)}"
    if kind == ScopeKind.LEFT_OF:
        return f"links von {identity_text(grid, clue.index)}"
    if kind == ScopeKind.RIGHT_OF:
        return f"rechts von {identity_text(grid, clue.index)}"
    if kind == ScopeKind.NORTH_OF:
        return f"nördlich von {identity_text(grid, clue.index)}"
    if kind == ScopeKind.SOUTH_OF:
        return f"südlich von {identity_text(grid, clue.index)}"
    if kind == ScopeKind.WEST_OF:
        return f"westlich von {identity_text(grid, clue.index)}"
    if kind == ScopeKind.EAST_OF:
        return f"östlich von {identity_text(grid, clue.index)}"
    raise ValueError(f"Unknown scope kind: {kind}")


_NEIGHBOR_TEMPLATES_ZERO = [
    "Keiner von {identity}s Nachbarn ist kriminell.",
    "Alle Nachbarn von {identity} sind unschuldig.",
]
_NEIGHBOR_TEMPLATES_FULL = [
    "Alle Nachbarn von {identity} sind kriminell.",
    "Keiner von {identity}s Nachbarn ist unschuldig.",
]
_NEIGHBOR_TEMPLATES_GENERAL = [
    "{target} von {n} {identity}s Nachbarn sind kriminell.",
    "Genau {target} von {identity}s Nachbarn sind kriminell.",
    "Unter {identity}s Nachbarn sind genau {target} kriminell.",
]


def _neighbor_count_phrase(identity: str, target: int, n: int, rng: random.Random) -> str:
    if target == 0:
        template = rng.choice(_NEIGHBOR_TEMPLATES_ZERO)
    elif target == n:
        template = rng.choice(_NEIGHBOR_TEMPLATES_FULL)
    else:
        template = rng.choice(_NEIGHBOR_TEMPLATES_GENERAL)
    return template.format(identity=identity, target=target, n=n)


_DIRECT_COUNT_GENERAL_TEMPLATES = {
    True: [
        "{identity} ist eine(r) von {n} Kriminellen {scope}.",
        "{identity} zählt zu den {n} Kriminellen {scope}.",
    ],
    False: [
        "{identity} ist unschuldig - es gibt trotzdem {n} Kriminelle {scope}.",
        "{identity} gehört nicht dazu, aber es gibt {n} Kriminelle {scope}.",
    ],
}

_DIRECT_COUNT_NEIGHBOR_TEMPLATES = {
    True: [
        "{identity} ist eine(r) von {neighbor}s {n} kriminellen Nachbarn.",
        "{identity} zählt zu {neighbor}s {n} kriminellen Nachbarn.",
    ],
    False: [
        "{identity} ist unschuldig, obwohl {neighbor} insgesamt {n} kriminelle Nachbarn hat.",
        "{identity} gehört zu {neighbor}s unschuldigen Nachbarn - {neighbor} hat trotzdem {n} kriminelle Nachbarn.",
    ],
}


def direct_count_clue_text(clue, grid: Grid, rng: random.Random | None = None) -> str:
    """Phrasing for DirectCountClue (counts.py) - a genuine direct-reveal
    + count combo, not just flavor text on a plain reveal (contrast with
    neighbor_direct_clue_text above). Branches on scope_kind exactly like
    count_clue_text does, for the same reason: NEIGHBOR reads more
    naturally as a possessive ("Y's N criminal neighbors") than the
    generic "{n} Kriminellen {scope}" pattern would."""
    rng = rng if rng is not None else random
    identity = identity_text(grid, clue.cell)
    if clue.scope_kind == ScopeKind.NEIGHBOR:
        neighbor = identity_text(grid, clue.index)
        template = rng.choice(_DIRECT_COUNT_NEIGHBOR_TEMPLATES[clue.is_criminal])
        text = template.format(identity=identity, neighbor=neighbor, n=clue.target)
    else:
        scope = _describe_scope(clue, grid)
        template = rng.choice(_DIRECT_COUNT_GENERAL_TEMPLATES[clue.is_criminal])
        text = template.format(identity=identity, n=clue.target, scope=scope)
    return text[0].upper() + text[1:]


def count_clue_text(clue, grid: Grid, rng: random.Random | None = None) -> str:
    rng = rng if rng is not None else random
    if clue.scope_kind == ScopeKind.CUSTOM_PAIR:
        a_identity = identity_text(grid, clue.scope_list[0])
        b_identity = identity_text(grid, clue.scope_list[1])
        template = rng.choice(PAIR_TEMPLATES[clue.target])
        return template.format(a=a_identity, b=b_identity)

    # Plain NEIGHBOR scope gets its own "X's neighbors" phrasing instead
    # of the generic "{group}" templates below - reads more naturally as
    # a possessive noun phrase. Intersection scopes (ROW_NEIGHBOR/
    # COL_NEIGHBOR) go through the generic path via _describe_scope
    # instead, since they're already a compound description ("in row 2,
    # among X's neighbors") that doesn't reduce to a simple possessive as
    # cleanly - but _describe_scope itself uses "Nachbarn" phrasing too,
    # not "neben".
    if clue.scope_kind == ScopeKind.NEIGHBOR:
        identity = identity_text(grid, clue.index)
        return _neighbor_count_phrase(identity, clue.target, len(clue.scope_list), rng)

    group = _describe_scope(clue, grid)
    return _group_phrase(group, clue.target, len(clue.scope_list), rng)


_PARITY_TEMPLATES = [
    "Es gibt eine {parity} Anzahl an Kriminellen {group}.",
    "Eine {parity} Anzahl an Kriminellen ist {group}.",
]

_NEIGHBOR_PARITY_TEMPLATES = [
    "Eine {parity} Anzahl von {identity}s Nachbarn ist kriminell.",
    "Unter {identity}s Nachbarn ist die Anzahl der Kriminellen {parity}.",
]


def parity_clue_text(clue, grid: Grid, rng: random.Random | None = None) -> str:
    rng = rng if rng is not None else random
    parity_word = "ungerade" if clue.is_odd else "gerade"
    if clue.scope_kind == ScopeKind.NEIGHBOR:
        identity = identity_text(grid, clue.index)
        text = rng.choice(_NEIGHBOR_PARITY_TEMPLATES).format(parity=parity_word, identity=identity)
        return text[0].upper() + text[1:]

    group = _describe_scope(clue, grid)
    text = rng.choice(_PARITY_TEMPLATES).format(parity=parity_word, group=group)
    return text[0].upper() + text[1:]


EXISTENCE_TEMPLATES = {
    ScopeKind.ROW: [
        "Jede Reihe hat mindestens einen Kriminellen.",
        "In jeder Reihe gibt es mindestens einen Kriminellen.",
    ],
    ScopeKind.COL: [
        "Jede Spalte hat mindestens einen Kriminellen.",
        "In jeder Spalte gibt es mindestens einen Kriminellen.",
    ],
    ScopeKind.NAME: [
        "Unter den Personen mit gleichem Namen ist mindestens eine kriminell.",
        "Für jeden verwendeten Namen ist mindestens eine Person mit diesem Namen kriminell.",
    ],
    ScopeKind.PROFESSION: [
        "Jeder Beruf hat mindestens einen Kriminellen.",
        "Unter jedem Beruf ist mindestens eine Person kriminell.",
    ],
}


def group_existence_text(clue, grid: Grid, rng: random.Random | None = None) -> str:
    rng = rng if rng is not None else random
    templates = EXISTENCE_TEMPLATES.get(clue.partition_kind)
    if not templates:
        raise ValueError(f"Unknown partition kind: {clue.partition_kind}")
    return rng.choice(templates)


COMPARE_TEMPLATES = [
    # No hardcoded article before {greater}/{lesser}: the label itself
    # already carries whatever article it needs ("den Fußballer(innen)")
    # or needs none ("Reihe 1", "Xs Nachbarn") - same convention
    # EQ_COMPARE_TEMPLATES's "in {a}" already relies on below. Templating
    # a "den" here too used to double up into "unter den den X" for any
    # label that already had its own "den" - a real, confusing bug fixed
    # by dropping it here instead of stripping "den" from every caller.
    "Es gibt mehr Kriminelle unter {greater} als unter {lesser}.",
    "Es gibt weniger Unschuldige unter {greater} als unter {lesser}.",
]

EQ_COMPARE_TEMPLATES = [
    "Es gibt genauso viele Kriminelle in {a} wie in {b}.",
    "{a} und {b} haben die gleiche Anzahl an Kriminellen.",
]


def compare_clue_text(clue, grid: Grid, rng: random.Random | None = None) -> str:
    rng = rng if rng is not None else random
    if clue.relation == "EQ":
        text = rng.choice(EQ_COMPARE_TEMPLATES).format(a=clue.label_a, b=clue.label_b)
        return text[0].upper() + text[1:]

    if clue.relation == "GT":
        greater_label, lesser_label = clue.label_a, clue.label_b
    else:
        greater_label, lesser_label = clue.label_b, clue.label_a
    template = rng.choice(COMPARE_TEMPLATES)
    text = template.format(greater=greater_label, lesser=lesser_label)
    return text[0].upper() + text[1:]
