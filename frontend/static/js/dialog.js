// The per-person dialog: opened by tapping any grid cell. Unsolved -> a
// guess prompt (Innocent/Criminal). Solved -> that cell's own attached
// clue or fun fact, read-only, for review.

let dialogCell = null; // {row, col} of whichever cell's dialog is currently open

function openCellDialog(row, col) {
  dialogCell = { row, col };
  const person = state.grid[row][col];
  const status = state.cellState[row][col];
  const reveal = state.cellReveal[row][col];

  document.getElementById("dialog-name").textContent = person.name;
  document.getElementById("dialog-profession").textContent = person.profession;
  document.getElementById("dialog-wrong-msg").classList.add("hidden");

  const controls = document.getElementById("dialog-guess-controls");
  const revealBox = document.getElementById("dialog-reveal");

  if (status === "unknown") {
    controls.classList.remove("hidden");
    revealBox.classList.add("hidden");
  } else {
    controls.classList.add("hidden");
    revealBox.classList.remove("hidden");

    const label = document.getElementById("dialog-status-label");
    label.textContent = status === "criminal" ? "Criminal" : "Innocent";
    label.classList.remove("status-criminal", "status-innocent");
    label.classList.add(status === "criminal" ? "status-criminal" : "status-innocent");

    document.getElementById("dialog-reveal-text").textContent = reveal ? reveal.text : "";
  }

  const dialogEl = document.getElementById("cell-dialog");
  if (!dialogEl.open) {
    dialogEl.showModal();
  }
}

function closeCellDialog() {
  document.getElementById("cell-dialog").close();
  dialogCell = null;
}

// Called after a guess/hint changes a cell's state, so an already-open
// dialog for that same cell reflects the result immediately.
function refreshDialogIfOpen(row, col) {
  if (dialogCell && dialogCell.row === row && dialogCell.col === col) {
    openCellDialog(row, col);
  }
}

function showDialogWrongGuess() {
  document.getElementById("dialog-wrong-msg").classList.remove("hidden");
}

function initDialogUI() {
  document.getElementById("dialog-guess-innocent").addEventListener("click", () => {
    if (dialogCell) submitGuess(dialogCell.row, dialogCell.col, "innocent");
  });
  document.getElementById("dialog-guess-criminal").addEventListener("click", () => {
    if (dialogCell) submitGuess(dialogCell.row, dialogCell.col, "criminal");
  });
  document.getElementById("dialog-close-btn").addEventListener("click", closeCellDialog);
  document.getElementById("cell-dialog").addEventListener("close", () => {
    dialogCell = null;
  });
}
