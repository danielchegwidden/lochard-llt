"""Lochard Board Portal – FastAPI backend + React SPA (Databricks App)."""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from server import db, migrations
from server.routes import agents, ai, boardpack, commentary, export, insights, market, platform, scorecard

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("lochard")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.pool.open(wait=True, timeout=60.0)
    try:
        log.info("migrations applied: %s", migrations.migrate())
        log.info("seeded: %s", migrations.seed())
    except Exception:  # noqa: BLE001 – keep serving; /healthz reports DB state
        log.exception("migration/seed failed")
    yield
    db.pool.close()


app = FastAPI(title="Lochard Board Portal", lifespan=lifespan)
for r in (scorecard.router, insights.router, commentary.router, market.router, boardpack.router, ai.router,
          agents.router, platform.router, export.router):
    app.include_router(r)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": str(exc)[:300]})


DIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend", "dist")
if os.path.isdir(os.path.join(DIST, "assets")):
    app.mount("/assets", StaticFiles(directory=os.path.join(DIST, "assets")), name="assets")


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    if path.startswith("api/"):
        return JSONResponse(status_code=404, content={"detail": "not found"})
    f = os.path.join(DIST, path)
    if path and os.path.isfile(f):
        return FileResponse(f)
    index = os.path.join(DIST, "index.html")
    return FileResponse(index) if os.path.exists(index) else JSONResponse({"detail": "frontend not built"}, 404)
