# CluesForYou

A homemade, cluesbysam-style logic puzzle game: a 5x4 grid of 20 people
sampled from your own customizable roster (each a name + profession pair),
each secretly innocent or a criminal. Every person carries their own clue
or fun fact, revealed the moment you correctly identify them.

Every puzzle is generated fresh, guaranteed to have exactly one valid
solution (checked with a CP-SAT solver), and checked to be solvable through
step-by-step human-style deduction, not just brute-force search.

Built for personal/family use, mobile-first - runs entirely on your own
machine, no account, no internet connection required once installed.

## Setup

Requires Python 3.11+ (developed against 3.12).

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

## Run

```bash
python cluesforyou.py
```

Then open **http://127.0.0.1:8000** in a browser (works well on phones too -
open it from any device on the same network as the machine running it, or
see "Future: hosting" below).

## Play

1. **Roster.** The app ships with a default roster of 25 people. Tap
   **Manage roster** to add your own (name + profession), or remove ones you
   don't want - you need at least 20 in the pool to generate a puzzle.
   Every puzzle samples 20 of them, so a roster bigger than 20 gives you
   variety across replays.
2. Pick a difficulty and hit **Generate puzzle**.
3. One person's status is revealed for free as your starting lead, along
   with their attached clue - which is usually a tip about *someone else*.
   Every one of the 20 people has exactly one thing attached to them: a real
   clue, or (for most of them) just a fun fact. It lives right there on
   their card, truncated to fit - correctly identifying a person reveals
   *their own* attached item, so following a clue's logic to find the right
   people is how you make progress. There's no separate clue list; each
   person carries their own.
4. Tap any grid cell to open it: unsolved cells prompt you to choose
   **Innocent** or **Criminal**; a correct guess locks the cell and shows
   its attached clue/fun fact right there in the dialog, and from then on
   directly on the card itself (every card reserves the same fixed space
   for it, revealed or not, so cards never resize as the game goes on). A
   wrong guess shows an inline "try again" - nothing is lost, the dialog
   stays open. Tapping an already-*solved* cell again toggles its clue
   between normal and greyed-out, so you can visually deprioritize clues
   you've already used and focus on what's still relevant.
5. Stuck? **Hint** fills in a cell it can justify from clues currently in
   play (it won't peek at anyone you haven't found yet).
6. Identify all 20 people correctly to win. **New puzzle** starts over
   with a fresh grid sampled from your roster.

Clue text is in German (buttons and everything else in the app stay
English) - wording is intentionally approximate, not polished. Gendered
profession pairs (Politiker/Politikerin, Mathematiker/Mathematikerin, ...)
count as the same profession for clue purposes, even though the roster is
free to hold both spellings.

Difficulties are tuned to require genuinely combining several clues, not
just reading off one:
- **Easy**: row/column/profession/region counts, plus person-relative
  directional counts ("N criminals below Alice"), including the
  occasional free "everyone/no one" giveaway.
- **Medium**: no more giveaways - every clue takes some real
  partial-count reasoning. Adds **neighbor** counts (a unified 8-cell
  neighborhood - orthogonal and diagonal together, fewer on edges/corners),
  intersection clues ("N criminals in row 2 neighboring Alice"), parity
  clues ("an odd number of criminals in the interior"), pairwise clues, and
  "every row/column/profession has at least one criminal" (a single clue
  spanning every group at once, which tends to only pay off once several
  *other* clues have already narrowed things down - a deliberately
  non-linear one).
- **Hard**: everything Medium has, plus comparison clues (including
  equality), and - the main thing that makes Hard genuinely hard - every
  Hard puzzle is guaranteed to require **combining two clues at once**:
  reading two count clues whose groups overlap and subtracting one from
  the other to figure out the rest (e.g. know the total for a row *and*
  the count for just the people in it neighboring someone - the
  difference tells you about everyone else in that row). This is a real,
  checked requirement, not a maybe - which means Hard generation
  sometimes has to search much harder for a valid puzzle than Easy/Medium
  do. Generating a Hard puzzle typically takes a few seconds but can
  occasionally take up to a minute or so; that's expected, not a bug.

## Development

Run the test suite (unit tests plus generation/attachment stress tests
across all three difficulties):

```bash
pytest
```

### Project layout

```
cluesforyou.py          launcher (starts uvicorn)
backend/app/
  core/                 puzzle engine: types, clue classes, the human
                         reasoning engine, the CP-SAT uniqueness solver,
                         the generator (incl. per-cell clue attachment),
                         roster storage, fun facts
  api/routes.py          FastAPI endpoints (roster CRUD + puzzle/guess/hint)
  state.py                in-memory puzzle storage (no DB, single-process)
  models.py                request/response schemas
backend/data/            roster.json (gitignored runtime data, auto-seeded)
frontend/                plain HTML/CSS/vanilla JS, no build step, mobile-first
backend/tests/           pytest suite
```

### How puzzle generation works, briefly

1. Sample 20 (name, profession) pairs from the roster into the 5x4 grid,
   never repeating a name in the same grid even if the roster holds
   duplicates; randomly decide who's a criminal.
2. Generate a big pool of candidate clues that are all true of that hidden
   solution - row/column/profession/corner/edge/interior counts, direct
   reveals, unified neighbor counts (one 8-cell neighborhood concept, not
   separate orthogonal/diagonal variants), person-relative directional
   counts (above/below/left/right of someone), intersection scopes (a
   row or column narrowed to just one person's neighbors), parity clues,
   pairwise clues, "every group has a criminal" existence clues, and
   person-vs-person/group-vs-group comparisons (including equality),
   depending on difficulty. Difficulties above Easy exclude "everyone/no
   one" giveaway clues entirely, so every remaining clue takes some real
   reasoning.
3. Grow a clue set (tiers 0-3 propagation only - fast) until it fully
   solves the grid, then prune away anything not actually needed. Pruning
   prefers to shed the *easiest* surviving clues first, concentrating
   whatever difficulty survives into the final puzzle. On Hard, growth and
   pruning both also enforce that the set stays genuinely *dependent* on
   combining two clues (see below) the whole way through, not just at the
   very end.
4. Double-check with a CP-SAT solver that the surviving clue set has
   *exactly one* valid solution, and that it needs the difficulty's
   minimum reasoning tier (Hard requires at least a comparison clue, and
   separately, a genuine combination-reasoning dependency).
5. Pick a starter cell, seed the reasoning trace with it, and walk the
   trace to attach each clue to a specific cell that's already knowable by
   the time it's needed. Cells that aren't chosen as a trigger (most of
   them, including any only reachable via combining two other clues) get
   a fun fact instead at play-time. The starter's own clue is guaranteed
   to be immediately useful on its own (never dependent on reasoning the
   player hasn't unlocked yet).

**What makes Hard actually hard:** the reasoning engine can cross-reference
any two active count clues whose groups overlap - if one clue's group is
entirely contained in another's, the difference between their two targets
tells you exactly how many criminals are in the leftover region, which can
force cells neither clue alone would ever reveal. This is real "hold two
clues in your head and subtract one from the other" reasoning, not just a
longer chain of single-clue deductions. Every Hard puzzle is checked to
*genuinely need* this (solving the same clue set with that cross-
referencing disabled is checked to fail), not just to have it available -
proving that negative reliably is considerably more expensive to search
for than Easy/Medium ever need, so Hard generation can occasionally take
up to a minute or so (see `GENERATION_TIME_BUDGET_SECONDS` in `config.py`).
Bounded hypothesis-testing ("assume this, propagate, check for a
contradiction") is also available during play-time reasoning and
occasionally shows up in Hard puzzles, but isn't separately mandatory the
way combination is.

See `backend/app/core/generator.py` (`attach_clues_to_cells`,
`select_clue_subset`) and `backend/app/core/reasoner.py` for the actual
algorithm.

### Future: hosting

Currently local-only by design, but nothing in the frontend assumes that
(API calls are all relative paths). Two things would need attention before
hosting for real multi-device/family use: the in-memory `PUZZLES` dict in
`state.py` and the single `backend/data/roster.json` file both assume one
process on one machine - fine behind a single `uvicorn` worker, but would
want a real datastore (or at least file locking) before running multiple
worker processes.
