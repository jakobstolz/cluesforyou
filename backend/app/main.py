"""FastAPI application entrypoint.

Mounts the JSON API under /api, then serves the plain HTML/CSS/JS frontend
as static files for everything else. The API router must be included
*before* the static mount, or the static mount would shadow it.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.app.api.routes import router as api_router

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

app = FastAPI(title="CluesForYou")

app.include_router(api_router, prefix="/api")

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
