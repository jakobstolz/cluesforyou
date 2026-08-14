"""FastAPI application entrypoint.

Mounts the JSON API under /api, then serves the plain HTML/CSS/JS frontend
as static files for everything else. The API router must be included
*before* the static mount, or the static mount would shadow it.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from backend.app.api.routes import router as api_router

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


class NoCacheMiddleware(BaseHTTPMiddleware):
    """FastAPI's StaticFiles doesn't set Cache-Control, so browsers fall
    back to heuristic caching and can serve a static asset (e.g. main.js)
    straight from disk cache after a deploy, without even asking the
    server - a real, confusing "the new feature just doesn't work" bug for
    anyone who's visited the site before (concretely hit this with the
    password gate/timer JS after a deploy). `no-cache` forces revalidation
    on every load - still cheap (a 304 via the ETag StaticFiles already
    sends when nothing changed), but guarantees a change is never silently
    missed. This is a small personal app with a handful of tiny assets, so
    the extra round-trip cost is negligible - not worth a fingerprinted-
    filename build step just to avoid it."""

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-cache"
        return response


app = FastAPI(title="CluesForYou")
app.add_middleware(NoCacheMiddleware)

app.include_router(api_router, prefix="/api")

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
