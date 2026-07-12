from __future__ import annotations

from collections.abc import Generator
from contextlib import suppress
from pathlib import Path
from uuid import uuid4

import pytest


@pytest.fixture
def isolated_database() -> Generator[Path, None, None]:
    output_dir = Path(__file__).resolve().parents[1] / ".testdata" / "isolated"
    output_dir.mkdir(parents=True, exist_ok=True)
    database_path = output_dir / f"news_test_{uuid4().hex}.db"
    yield database_path
    with suppress(OSError):
        database_path.unlink()
