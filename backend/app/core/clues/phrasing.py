"""Randomized natural-language phrasing pools for each clue flavor.

Clue text is in German (buttons/dialog chrome, fun facts, and everything
else stay English - see core/funfacts.py and the frontend). Wording is
approximate, not grammatically polished - kept separate from the clue
classes so it can be tuned/expanded without touching
evaluation/propagation/CP-SAT logic.
"""

from __future__ import annotations

import random

from backend.app.core.types import Grid, ScopeKind, identity_text, profession_group_label

DIRECT_TEMPLATES = [
    "{identity} ist {status}.",
    "Bestätigt: {identity} ist {status}.",
    "Wir wissen mit Sicherheit: {identity} ist {status}.",
]


def direct_clue_text(identity: str, is_criminal: bool) -> str:
    status = "kriminell" if is_criminal else "unschuldig"
    return random.choice(DIRECT_TEMPLATES).format(identity=identity, status=status)


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


def _group_phrase(group: str, target: int, n: int) -> str:
    if target == 0:
        template = random.choice(_GROUP_TEMPLATES_ZERO)
    elif target == n:
        template = random.choice(_GROUP_TEMPLATES_FULL)
    else:
        template = random.choice(_GROUP_TEMPLATES_GENERAL)
    return template.format(group=group, target=target, n=n)


def _describe_scope(clue, grid: Grid) -> str:
    """A phrase like 'in Reihe 2' or 'neben Alice (Chef)' describing a
    clue's scope, driven by scope_kind/index. Shared between count and
    parity phrasing (CUSTOM_PAIR is handled separately by each - its
    phrasing names the two people directly rather than describing a
    group)."""
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
        return f"neben {identity_text(grid, clue.index)}"
    if kind == ScopeKind.ROW_NEIGHBOR:
        row, anchor = clue.index
        return f"in Reihe {row + 1} neben {identity_text(grid, anchor)}"
    if kind == ScopeKind.COL_NEIGHBOR:
        col, anchor = clue.index
        return f"in Spalte {col + 1} neben {identity_text(grid, anchor)}"
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
    raise ValueError(f"Unknown scope kind: {kind}")


def count_clue_text(clue, grid: Grid) -> str:
    if clue.scope_kind == ScopeKind.CUSTOM_PAIR:
        a_identity = identity_text(grid, clue.scope_list[0])
        b_identity = identity_text(grid, clue.scope_list[1])
        template = random.choice(PAIR_TEMPLATES[clue.target])
        return template.format(a=a_identity, b=b_identity)

    group = _describe_scope(clue, grid)
    return _group_phrase(group, clue.target, len(clue.scope_list))


_PARITY_TEMPLATES = [
    "Es gibt eine {parity} Anzahl an Kriminellen {group}.",
    "Eine {parity} Anzahl an Kriminellen ist {group}.",
]


def parity_clue_text(clue, grid: Grid) -> str:
    group = _describe_scope(clue, grid)
    parity_word = "ungerade" if clue.is_odd else "gerade"
    text = random.choice(_PARITY_TEMPLATES).format(parity=parity_word, group=group)
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


def group_existence_text(clue, grid: Grid) -> str:
    templates = EXISTENCE_TEMPLATES.get(clue.partition_kind)
    if not templates:
        raise ValueError(f"Unknown partition kind: {clue.partition_kind}")
    return random.choice(templates)


COMPARE_TEMPLATES = [
    "Es gibt mehr Kriminelle unter den {greater} als unter den{lesser}.",
    "Es gibt weniger Unschuldige unter den {greater} als unter den {lesser}.",
]

EQ_COMPARE_TEMPLATES = [
    "Es gibt genauso viele Kriminelle in {a} wie in {b}.",
    "{a} und {b} haben die gleiche Anzahl an Kriminellen.",
]


def compare_clue_text(clue, grid: Grid) -> str:
    if clue.relation == "EQ":
        text = random.choice(EQ_COMPARE_TEMPLATES).format(a=clue.label_a, b=clue.label_b)
        return text[0].upper() + text[1:]

    if clue.relation == "GT":
        greater_label, lesser_label = clue.label_a, clue.label_b
    else:
        greater_label, lesser_label = clue.label_b, clue.label_a
    template = random.choice(COMPARE_TEMPLATES)
    text = template.format(greater=greater_label, lesser=lesser_label)
    return text[0].upper() + text[1:]
