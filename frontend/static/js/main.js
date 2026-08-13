// Wiring: screen navigation, generate/guess/hint/new-puzzle, roster entry points.

function showSection(id) {
  for (const section of ["setup-section", "roster-section", "game-section"]) {
    document.getElementById(section).classList.toggle("hidden", section !== id);
  }
}

// Solve timer: starts when a puzzle is generated, freezes on win. Not part
// of `state` - it's a runtime handle (setInterval id), not game data.
let timerIntervalId = null;

function formatElapsed(ms) {
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function tickTimerDisplay() {
  document.getElementById("timer-display").textContent = formatElapsed(Date.now() - state.startTime);
}

function stopTimer() {
  if (timerIntervalId !== null) {
    clearInterval(timerIntervalId);
    timerIntervalId = null;
  }
}

function finishTimer() {
  // Freezes the toolbar display and mirrors the final time into the win
  // banner - called from every path that can trigger a win (a guess or a
  // hint completing the puzzle).
  stopTimer();
  const elapsed = formatElapsed(Date.now() - state.startTime);
  document.getElementById("timer-display").textContent = elapsed;
  document.getElementById("win-time").textContent = `(${elapsed})`;
}

// Password gate: not real security (the API stays open regardless) - just
// a fun "find the password" barrier before the actual app content shows,
// per the site being "shipped" to friends/family as a puzzle in itself.
const UNLOCK_STORAGE_KEY = "cfy_unlocked";
const SITE_PASSWORD = "1234";

document.addEventListener("DOMContentLoaded", () => {
  initPasswordGate();
});

function initPasswordGate() {
  if (localStorage.getItem(UNLOCK_STORAGE_KEY) === "1") {
    unlockApp();
    return;
  }
  document.getElementById("password-form").addEventListener("submit", onPasswordSubmit);
  document.getElementById("password-input").focus();
}

function onPasswordSubmit(event) {
  event.preventDefault();
  const input = document.getElementById("password-input");
  if (input.value === SITE_PASSWORD) {
    localStorage.setItem(UNLOCK_STORAGE_KEY, "1");
    unlockApp();
  } else {
    document.getElementById("password-error").classList.remove("hidden");
    input.value = "";
    input.focus();
  }
}

function unlockApp() {
  document.getElementById("password-gate").classList.add("hidden");
  document.getElementById("app-content").classList.remove("hidden");
  initApp();
}

function initApp() {
  initRosterUI();
  initDialogUI();
  refreshRosterStatus();

  document.getElementById("generate-btn").addEventListener("click", onGenerateClick);
  document.getElementById("manage-roster-btn").addEventListener("click", onManageRosterClick);
  document.getElementById("roster-back-btn").addEventListener("click", onRosterBackClick);
  document.getElementById("hint-btn").addEventListener("click", onHintClick);
  document.getElementById("new-puzzle-btn").addEventListener("click", onNewPuzzleClick);
}

async function onManageRosterClick() {
  showSection("roster-section");
  await refreshRosterStatus();
  renderRosterList();
}

async function onRosterBackClick() {
  showSection("setup-section");
  await refreshRosterStatus();
}

async function onGenerateClick() {
  const errorEl = document.getElementById("setup-error");
  errorEl.classList.add("hidden");

  const difficulty = document.querySelector('input[name="difficulty"]:checked').value;
  const seed = document.getElementById("seed-input").value.trim();

  const btn = document.getElementById("generate-btn");
  btn.disabled = true;
  const originalLabel = btn.textContent;
  btn.textContent = "Generating…";

  try {
    const data = await api.generatePuzzle(difficulty, seed);
    startGame(data);
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.classList.remove("hidden");
  } finally {
    btn.textContent = originalLabel;
    await refreshRosterStatus(); // re-enables the button if the roster still qualifies
  }
}

function startGame(data) {
  resetState();
  state.puzzleId = data.puzzle_id;
  state.difficulty = data.difficulty;

  // Grid dimensions come from the puzzle response itself - never hardcoded,
  // so the frontend doesn't care what shape the backend's grid actually is.
  const numRows = data.grid.length;
  const numCols = data.grid[0].length;

  state.grid = Array.from({ length: numRows }, () => Array(numCols).fill(null));
  for (const row of data.grid) {
    for (const cell of row) {
      state.grid[cell.row][cell.col] = { name: cell.name, profession: cell.profession };
    }
  }

  state.cellState = Array.from({ length: numRows }, () => Array(numCols).fill("unknown"));
  state.cellState[data.starter.row][data.starter.col] = data.starter.status;

  state.cellReveal = Array.from({ length: numRows }, () => Array(numCols).fill(null));
  state.cellReveal[data.starter.row][data.starter.col] = {
    kind: "clue",
    text: data.first_clue.text,
    tier: data.first_clue.tier,
  };

  state.cellDimmed = Array.from({ length: numRows }, () => Array(numCols).fill(false));
  state.easterEggHearts = Array.from({ length: numRows }, () => Array(numCols).fill(false));

  document.getElementById("difficulty-badge").textContent = data.difficulty;
  document.getElementById("seed-display").textContent = `Seed: ${data.seed}`;
  const hintMsg = document.getElementById("hint-message");
  hintMsg.textContent = "";
  hintMsg.classList.add("hidden");
  document.getElementById("win-banner").classList.add("hidden");
  document.getElementById("win-time").textContent = "";
  showSection("game-section");

  state.startTime = Date.now();
  stopTimer(); // in case a previous game's interval is somehow still running
  tickTimerDisplay();
  timerIntervalId = setInterval(tickTimerDisplay, 1000);

  renderGrid();
}

async function submitGuess(row, col, guess) {
  try {
    const result = await api.guess(state.puzzleId, row, col, guess);
    if (!result.correct) {
      flashWrongGuess(row, col);
      showDialogWrongGuess();
      return;
    }

    state.cellState[row][col] = guess;
    if (result.reveal) {
      state.cellReveal[row][col] = result.reveal;
    }
    renderGrid();
    refreshDialogIfOpen(row, col);

    if (result.solved) {
      finishTimer();
      document.getElementById("win-banner").classList.remove("hidden");
      closeCellDialog();
    }
  } catch (err) {
    console.error(err);
  }
}

async function onHintClick() {
  const msgEl = document.getElementById("hint-message");
  msgEl.classList.remove("hidden");

  try {
    const result = await api.hint(state.puzzleId);
    if (!result.available) {
      msgEl.textContent = "No hint available yet - try a guess first.";
      return;
    }

    state.cellState[result.row][result.col] = result.value;
    if (result.reveal) {
      state.cellReveal[result.row][result.col] = result.reveal;
    }
    renderGrid();
    highlightHintCell(result.row, result.col);
    refreshDialogIfOpen(result.row, result.col);
    msgEl.textContent = `Hint: ${result.reason}`;

    if (result.solved) {
      finishTimer();
      document.getElementById("win-banner").classList.remove("hidden");
    }
  } catch (err) {
    msgEl.textContent = err.message;
  }
}

async function onNewPuzzleClick() {
  stopTimer();
  resetState();
  showSection("setup-section");
  await refreshRosterStatus();
}
