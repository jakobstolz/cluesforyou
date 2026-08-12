// Renders the suspect grid (shape comes from state.grid, not hardcoded).
// Each cell shows name/profession, and once solved, its own attached clue
// or fun fact directly on the card (no separate feed/case-file - the
// reveal lives on the person it belongs to). Tapping any cell opens the
// guess/detail dialog (see dialog.js).

function renderGrid() {
  const gridEl = document.getElementById("grid");
  gridEl.innerHTML = "";

  const numRows = state.grid.length;
  const numCols = state.grid[0].length;
  gridEl.style.gridTemplateColumns = `repeat(${numCols}, 1fr)`;

  for (let r = 0; r < numRows; r++) {
    for (let c = 0; c < numCols; c++) {
      const person = state.grid[r][c];
      const status = state.cellState[r][c];
      const reveal = state.cellReveal[r][c];

      const cellEl = document.createElement("div");
      cellEl.className = "cell";
      cellEl.dataset.row = r;
      cellEl.dataset.col = c;
      cellEl.setAttribute("role", "button");
      cellEl.setAttribute("tabindex", "0");

      const nameEl = document.createElement("div");
      nameEl.className = "cell-name";
      nameEl.textContent = person.name;
      if (state.easterEggHearts[r][c]) {
        const heartEl = document.createElement("span");
        heartEl.className = "easter-egg-heart";
        heartEl.textContent = " ❤️";
        heartEl.setAttribute("aria-hidden", "true");
        nameEl.appendChild(heartEl);
      }

      const profEl = document.createElement("div");
      profEl.className = "cell-profession";
      profEl.textContent = person.profession;

      cellEl.appendChild(nameEl);
      cellEl.appendChild(profEl);

      if (status !== "unknown") {
        cellEl.classList.add(status === "criminal" ? "locked-criminal" : "locked-innocent");

        const label = document.createElement("div");
        label.className = "cell-status-label";
        label.textContent = status === "criminal" ? "Criminal" : "Innocent";
        cellEl.appendChild(label);
      }

      // Always present (even blank pre-reveal) so every cell reserves the
      // same vertical space from the start - cards don't resize as the
      // game progresses. Toggled dim by re-clicking an already-solved cell
      // (see below) so found clues can be visually deprioritized.
      const preview = document.createElement("div");
      preview.className = "cell-clue-preview";
      if (reveal) {
        preview.textContent = reveal.text;
      }
      if (state.cellDimmed[r][c]) {
        preview.classList.add("dimmed");
      }
      cellEl.appendChild(preview);

      const onActivate = () => {
        if (status === "unknown") {
          openCellDialog(r, c);
        } else {
          toggleCellDimmed(r, c);
        }
      };
      cellEl.addEventListener("click", onActivate);
      cellEl.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onActivate();
        }
      });
      // Tiny easter egg: double-clicking Annika (part of the default
      // roster) toggles a heart next to her name. Purely cosmetic,
      // client-only - doesn't touch guess/dialog state.
      if (person.name === "Annika") {
        cellEl.addEventListener("dblclick", () => {
          state.easterEggHearts[r][c] = !state.easterEggHearts[r][c];
          renderGrid();
        });
      }

      gridEl.appendChild(cellEl);
    }
  }
}

// Re-clicking an already-solved cell doesn't reopen the guess dialog (it
// has nothing left to ask) - it toggles that cell's clue preview between
// normal and greyed-out, so a player can visually deprioritize clues
// they've already used and focus on what's still relevant. The preview
// box is already full-size/non-truncated, so there's no separate need to
// reopen anything to re-read the full text.
function toggleCellDimmed(row, col) {
  state.cellDimmed[row][col] = !state.cellDimmed[row][col];
  renderGrid();
}

function findCellEl(row, col) {
  return document.querySelector(`.cell[data-row="${row}"][data-col="${col}"]`);
}

function flashWrongGuess(row, col) {
  const cellEl = findCellEl(row, col);
  if (!cellEl) return;
  cellEl.classList.add("shake");
  setTimeout(() => cellEl.classList.remove("shake"), 400);
}

function highlightHintCell(row, col) {
  const cellEl = findCellEl(row, col);
  if (!cellEl) return;
  cellEl.classList.add("hint-highlight");
  setTimeout(() => cellEl.classList.remove("hint-highlight"), 2000);
}
