"""Launcher for the CluesForYou webapp.

Local (dev, auto-reload on file changes):
    python cluesforyou.py
    -> http://127.0.0.1:8000

LAN (test from your phone over the same WiFi):
    Same command - it already binds 0.0.0.0, so from another device on
    your network visit http://<this-machine's-LAN-IP>:8000

Hosted (e.g. Render): the platform sets the PORT env var, which is what
switches this into production mode (no auto-reload, binds whatever port
the platform assigns) - nothing else to configure.
"""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    port = int(os.environ.get("PORT", 8000))
    # No PORT env var set -> plain local run -> keep the dev convenience
    # of auto-reload. A hosting platform injecting PORT switches this off
    # automatically, no separate flag to remember to set.
    reload = "PORT" not in os.environ
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=port, reload=reload)


if __name__ == "__main__":
    main()
