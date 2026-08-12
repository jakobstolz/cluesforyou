"""Launcher for the CluesForYou local webapp.

Run with:  python cluesforyou.py
Then open: http://127.0.0.1:8000
"""

from __future__ import annotations

import uvicorn


def main() -> None:
    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":
    main()
