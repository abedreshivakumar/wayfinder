"""The FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from wayfinder.api import error_handlers
from wayfinder.api.routers import explain, graph
from wayfinder.services import build_services


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
    return app
