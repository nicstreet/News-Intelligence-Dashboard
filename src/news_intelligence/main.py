from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from news_intelligence.api.routes import router
from news_intelligence.config import project_root


def create_app() -> FastAPI:
    app = FastAPI(title="News Intelligence", version="0.1.0")
    app.include_router(router)

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
