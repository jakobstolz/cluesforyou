// Roster management: fetching, rendering, and editing the shared pool of
// (name, profession) pairs puzzles are sampled from.

const ROSTER_MIN_SIZE = 25;
let rosterCache = [];

async function refreshRosterStatus() {
  try {
    const data = await api.getRoster();
    rosterCache = data.people;
  } catch (err) {
    document.getElementById("roster-status").textContent = `Couldn't load roster: ${err.message}`;
    return rosterCache;
  }
  updateRosterStatusText();
  return rosterCache;
}

function updateRosterStatusText() {
  const count = rosterCache.length;

  const statusEl = document.getElementById("roster-status");
  const generateBtn = document.getElementById("generate-btn");
  if (count >= ROSTER_MIN_SIZE) {
    statusEl.textContent = `${count} people ready to play.`;
    generateBtn.disabled = false;
  } else {
    statusEl.textContent = `${count}/${ROSTER_MIN_SIZE} people - add ${ROSTER_MIN_SIZE - count} more to play.`;
    generateBtn.disabled = true;
  }

  const countLine = document.getElementById("roster-count-line");
  if (countLine) {
    countLine.textContent =
      count >= ROSTER_MIN_SIZE
        ? `${count} people in the roster.`
        : `${count}/${ROSTER_MIN_SIZE} people - need ${ROSTER_MIN_SIZE - count} more to play.`;
  }
}

function renderRosterList() {
  const listEl = document.getElementById("roster-list");
  listEl.innerHTML = "";
  for (const person of rosterCache) {
    const li = document.createElement("li");
    li.className = "roster-row";

    const info = document.createElement("span");
    info.className = "roster-row-info";
    info.textContent = `${person.name} — ${person.profession}`;

    const deleteBtn = document.createElement("button");
    deleteBtn.type = "button";
    deleteBtn.className = "roster-delete-btn";
    deleteBtn.textContent = "✕";
    deleteBtn.setAttribute("aria-label", `Remove ${person.name} the ${person.profession}`);
    deleteBtn.addEventListener("click", () => onDeleteRosterEntry(person.id));

    li.appendChild(info);
    li.appendChild(deleteBtn);
    listEl.appendChild(li);
  }
}

function showRosterError(message) {
  const errorEl = document.getElementById("roster-error");
  errorEl.textContent = message;
  errorEl.classList.remove("hidden");
}

function clearRosterError() {
  document.getElementById("roster-error").classList.add("hidden");
}

async function onDeleteRosterEntry(id) {
  clearRosterError();
  try {
    await api.deleteRosterEntry(id);
    await refreshRosterStatus();
    renderRosterList();
  } catch (err) {
    showRosterError(err.message);
  }
}

async function onAddPersonSubmit(event) {
  event.preventDefault();
  clearRosterError();

  const nameInput = document.getElementById("add-person-name");
  const profInput = document.getElementById("add-person-profession");

  try {
    await api.addRosterEntry(nameInput.value.trim(), profInput.value.trim());
    nameInput.value = "";
    profInput.value = "";
    nameInput.focus();
    await refreshRosterStatus();
    renderRosterList();
  } catch (err) {
    showRosterError(err.message);
  }
}

function initRosterUI() {
  document.getElementById("add-person-form").addEventListener("submit", onAddPersonSubmit);
}
