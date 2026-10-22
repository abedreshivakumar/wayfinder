"""The FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.types import Scope

from wayfinder.api import error_handlers
from wayfinder.api.routers import ask, browse, explain, graph, trace
from wayfinder.services import build_services


class _UIStaticFiles(StaticFiles):
    """`index.html` (and any other bare `.html`) always revalidates with the browser, so a
    rebuilt UI shows up on the next reload instead of a stale bundle sticking around until
    someone thinks to hard-refresh - every other file here is content-hashed by Vite, so it's
    safe for those to stay cached as long as the browser likes."""

    async def get_response(self, path: str, scope: Scope):
        response = await super().get_response(path, scope)
        if path in ("", ".") or path.endswith(".html"):
            response.headers["Cache-Control"] = "no-cache"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Built once at startup and shared by every request: the services hold the running
    # pyright processes, which are far too slow to start per request.
    services = build_services()
    app.state.services = services
    yield
    services.close()  # stops the pyright processes cleanly


def create_app() -> FastAPI:
    app = FastAPI(title="Wayfinder", lifespan=lifespan)
    error_handlers.register(app)
    app.include_router(graph.router)
    app.include_router(explain.router)
    app.include_router(ask.router)
    app.include_router(browse.router)
    app.include_router(trace.router)
    # The built web UI (`npm run build` in web/), when it exists. Mounted last so the API
    # routes above win.
    ui = Path(__file__).resolve().parents[3] / "web" / "dist"
    if ui.is_dir():
        app.mount("/", _UIStaticFiles(directory=ui, html=True), name="ui")
    return app
