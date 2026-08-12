// Plain client-side game state. No framework - just an object mutated
// directly by main.js and read by grid.js/dialog.js when rendering.
const state = {
  puzzleId: null,
  difficulty: null,
  grid: null, // 2D array of {name, profession}, shape from the puzzle response
  cellState: null, // 2D array of "unknown" | "innocent" | "criminal"
  cellReveal: null, // 2D array of null | {kind: "clue"|"funfact", text, tier} - lives on the cell itself
  cellDimmed: null, // 2D array of bool - client-only "greyed out" toggle for already-solved cells
  easterEggHearts: null, // 2D array of bool - client-only, toggled by double-clicking Annika
};

function resetState() {
  state.puzzleId = null;
  state.difficulty = null;
  state.grid = null;
  state.cellState = null;
  state.cellReveal = null;
  state.cellDimmed = null;
  state.easterEggHearts = null;
}
