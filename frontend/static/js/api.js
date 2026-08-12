// Thin fetch wrappers around the backend JSON API.
const api = {
  async getRoster() {
    return api._json("/api/roster");
  },
  async addRosterEntry(name, profession) {
    return api._json("/api/roster", "POST", { name, profession });
  },
  async updateRosterEntry(id, name, profession) {
    return api._json(`/api/roster/${id}`, "PUT", { name, profession });
  },
  async deleteRosterEntry(id) {
    return api._json(`/api/roster/${id}`, "DELETE", null, /* expectBody */ false);
  },
  async generatePuzzle(difficulty) {
    return api._json("/api/puzzle", "POST", { difficulty });
  },
  async guess(puzzleId, row, col, guess) {
    return api._json("/api/guess", "POST", { puzzle_id: puzzleId, row, col, guess });
  },
  async hint(puzzleId) {
    return api._json("/api/hint", "POST", { puzzle_id: puzzleId });
  },
  async _json(url, method = "GET", payload = null, expectBody = true) {
    const opts = { method };
    if (payload !== null) {
      opts.headers = { "Content-Type": "application/json" };
      opts.body = JSON.stringify(payload);
    }
    const resp = await fetch(url, opts);
    const data = expectBody && resp.status !== 204 ? await resp.json().catch(() => ({})) : {};
    if (!resp.ok) {
      const detail = Array.isArray(data.detail)
        ? data.detail.map((d) => d.msg).join("; ")
        : data.detail || `Request failed (${resp.status})`;
      throw new Error(detail);
    }
    return data;
  },
};
