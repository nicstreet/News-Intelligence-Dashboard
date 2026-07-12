from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import datetime, timedelta
from typing import Any

from news_intelligence.pipeline import NewsIntelligencePipeline
from news_intelligence.sources.scheduler import SourceScheduler


class SourceAutomationBackgroundRunner:
    def __init__(self, pipeline: NewsIntelligencePipeline) -> None:
        self._pipeline = pipeline
        self._task: asyncio.Task[None] | None = None
        self._last_tick_at: datetime | None = None
        self._last_error: str | None = None

    async def start(self) -> None:
        if not bool(self._pipeline.config.automation.get("enabled", False)):
            return
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._run_loop())
        if bool(self._pipeline.config.automation.get("poll_due_on_startup", False)):
            await self.run_once(reason="startup")
        retention = self._retention_settings()
        if bool(retention.get("apply_on_startup", False)):
            await self.run_once(reason="startup_retention", apply_retention=True)

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def run_once(
        self,
        *,
        reason: str = "manual",
        force_sources: bool = False,
        apply_retention: bool | None = None,
    ) -> dict[str, Any]:
        scheduler = SourceScheduler(self._pipeline)
        try:
            return await asyncio.to_thread(
                scheduler.run_once,
                force_sources=force_sources,
                apply_retention=apply_retention,
                reason=reason,
            )
        except Exception as exc:
            self._last_error = str(exc)
            raise

    def status(self) -> dict[str, Any]:
        interval_seconds = SourceScheduler(self._pipeline).interval_seconds()
        running = self._task is not None and not self._task.done()
        next_tick_at = None
        if running and self._last_tick_at is not None:
            next_tick_at = self._last_tick_at + timedelta(seconds=interval_seconds)
        return {
            "enabled": bool(self._pipeline.config.automation.get("enabled", False)),
            "running": running,
            "interval_seconds": interval_seconds,
            "last_tick_at": self._last_tick_at.isoformat() if self._last_tick_at else None,
            "next_tick_at": next_tick_at.isoformat() if next_tick_at else None,
            "last_error": self._last_error,
        }

    async def _run_loop(self) -> None:
        scheduler = SourceScheduler(self._pipeline)
        interval_seconds = scheduler.interval_seconds()
        while True:
            await asyncio.sleep(interval_seconds)
            self._last_tick_at = self._pipeline.clock()
            try:
                await self.run_once(reason="scheduled")
                self._last_error = None
            except Exception as exc:
                self._last_error = str(exc)

    def _retention_settings(self) -> dict[str, Any]:
        settings = self._pipeline.config.automation.get("retention", {})
        return settings if isinstance(settings, dict) else {}
