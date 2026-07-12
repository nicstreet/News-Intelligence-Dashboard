from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from news_intelligence.api import routes
from news_intelligence.config import project_root
from news_intelligence.sources.background import SourceAutomationBackgroundRunner


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    routes.automation_runner = SourceAutomationBackgroundRunner(routes.pipeline)
    await routes.automation_runner.start()
    try:
        yield
    finally:
        if routes.automation_runner is not None:
            await routes.automation_runner.stop()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Asterius News Intelligence",
        version="0.2.0",
        lifespan=lifespan,
    )
    app.include_router(routes.router)

    frontend_dir = project_root() / "frontend"
    if frontend_dir.exists():
        app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

        @app.get("/", include_in_schema=False)
        async def dashboard() -> FileResponse:
            return FileResponse(frontend_dir / "index.html")

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok", "service": "news_intelligence"}

    return app


app = create_app()
