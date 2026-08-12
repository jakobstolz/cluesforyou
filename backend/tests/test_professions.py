import random

from backend.app.core.grid import random_grid_layout
from backend.app.core.types import (
    Person,
    profession_group_cells,
    profession_group_key,
    profession_group_label,
)


def test_profession_group_key_strips_gendered_in_suffix():
    # German female profession nouns append "-in" to the male form.
    assert profession_group_key("Politiker") == "Politiker"
    assert profession_group_key("Politikerin") == "Politiker"
    assert profession_group_key("Mathematiker") == "Mathematiker"
    assert profession_group_key("Mathematikerin") == "Mathematiker"


def test_profession_group_key_leaves_non_gendered_words_alone():
    # Words that don't end in "in" pass through unchanged.
    assert profession_group_key("Comedian") == "Comedian"
    assert profession_group_key("DJ") == "DJ"
    assert profession_group_key("Pink Floyd") == "Pink Floyd"


def test_profession_group_key_does_not_mangle_tiny_words():
    # The len() > 3 guard avoids stripping "-in" off something too short
    # for that to plausibly be a gendered-noun suffix.
    assert profession_group_key("in") == "in"


def test_profession_group_cells_unifies_both_spellings():
    grid = [
        [Person("Alice", "Politiker"), Person("Bob", "Politikerin"), Person("Carl", "DJ"), Person("Dana", "Comedian")],
        [Person("Eli", "Chef"), Person("Fay", "Chef"), Person("Gus", "Cop"), Person("Hana", "Cop")],
        [Person("Ivo", "Doctor"), Person("Jill", "Doctor"), Person("Kian", "Teacher"), Person("Lea", "Teacher")],
        [Person("Milo", "Engineer"), Person("Nia", "Engineer"), Person("Omar", "Chef"), Person("Pia", "Cop")],
        [Person("Quinn", "Doctor"), Person("Rex", "Teacher"), Person("Sara", "Engineer"), Person("Theo", "Chef")],
    ]
    cells = profession_group_cells(grid, "Politiker")
    assert set(cells) == {(0, 0), (0, 1)}  # both the "Politiker" and "Politikerin" cells


def test_profession_group_label_uses_bare_spelling_when_only_one_present():
    grid = [
        [Person("Alice", "Comedian"), Person("Bob", "Comedian"), Person("Carl", "DJ"), Person("Dana", "DJ")],
        [Person("Eli", "Chef"), Person("Fay", "Chef"), Person("Gus", "Cop"), Person("Hana", "Cop")],
        [Person("Ivo", "Doctor"), Person("Jill", "Doctor"), Person("Kian", "Teacher"), Person("Lea", "Teacher")],
        [Person("Milo", "Engineer"), Person("Nia", "Engineer"), Person("Omar", "Chef"), Person("Pia", "Cop")],
        [Person("Quinn", "Doctor"), Person("Rex", "Teacher"), Person("Sara", "Engineer"), Person("Theo", "Chef")],
    ]
    assert profession_group_label(grid, "Comedian") == "Comedian"


def test_profession_group_label_uses_neutral_form_when_both_spellings_present():
    grid = [
        [Person("Alice", "Politiker"), Person("Bob", "Politikerin"), Person("Carl", "DJ"), Person("Dana", "Comedian")],
        [Person("Eli", "Chef"), Person("Fay", "Chef"), Person("Gus", "Cop"), Person("Hana", "Cop")],
        [Person("Ivo", "Doctor"), Person("Jill", "Doctor"), Person("Kian", "Teacher"), Person("Lea", "Teacher")],
        [Person("Milo", "Engineer"), Person("Nia", "Engineer"), Person("Omar", "Chef"), Person("Pia", "Cop")],
        [Person("Quinn", "Doctor"), Person("Rex", "Teacher"), Person("Sara", "Engineer"), Person("Theo", "Chef")],
    ]
    assert profession_group_label(grid, "Politiker") == "Politiker(innen)"


def test_generated_grid_never_repeats_a_name_and_profession_grouping_is_consistent():
    # Sanity-check profession_group_cells against a real generated grid too.
    pool = [Person(f"Name{i}", "Politiker" if i % 2 == 0 else "Politikerin") for i in range(20)]
    grid = random_grid_layout(pool, random.Random(1))
    merged = profession_group_cells(grid, "Politiker")
    assert len(merged) == 20  # every single cell in this all-Politiker(in) pool
