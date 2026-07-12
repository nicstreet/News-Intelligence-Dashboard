from __future__ import annotations

import shutil
from contextlib import suppress
from pathlib import Path
from uuid import uuid4

from pytest import MonkeyPatch

from news_intelligence.config import load_config


def test_eodhd_api_token_uses_gitignored_local_file_and_environment_override(
    monkeypatch: MonkeyPatch,
) -> None:
    config_dir = _temporary_config_dir()
    try:
        _write_minimal_config(config_dir)
        monkeypatch.delenv("EODHD_TEST_TOKEN", raising=False)

        config = load_config(config_dir)

        assert config.eodhd_api_token == "local-token"
        assert config.eodhd_enabled is False
        assert config.eodhd["historical_eod"]["endpoint"] == "/eod/{symbol}"
        assert config.eodhd["historical_eod"]["default_period"] == "w"

        monkeypatch.setenv("EODHD_TEST_TOKEN", "env-token")

        assert load_config(config_dir).eodhd_api_token == "env-token"
    finally:
        with suppress(OSError):
            shutil.rmtree(config_dir)


def test_eodhd_local_secret_file_is_gitignored() -> None:
    root = Path(__file__).resolve().parents[2]

    assert "config/*.local.yaml" in (root / ".gitignore").read_text(encoding="utf-8")
    assert (root / "config" / "eodhd.local.example.yaml").exists()


def _temporary_config_dir() -> Path:
    root = Path(__file__).resolve().parents[2]
    config_dir = root / ".testdata" / "config-secrets" / uuid4().hex
    config_dir.mkdir(parents=True, exist_ok=False)
    return config_dir


def _write_minimal_config(config_dir: Path) -> None:
    (config_dir / "event-rules.yaml").write_text(
        "version: rules-test\nrules: []\n",
        encoding="utf-8",
    )
    (config_dir / "instrument-relationships.yaml").write_text(
        "version: resolver-test\ninstruments: {}\n",
        encoding="utf-8",
    )
    (config_dir / "source-credibility.yaml").write_text(
        "version: sources-test\nsources: {}\n",
        encoding="utf-8",
    )
    (config_dir / "freshness-half-lives.yaml").write_text(
        "version: freshness-test\n",
        encoding="utf-8",
    )
    (config_dir / "runtime.yaml").write_text(
        "environment: test\n",
        encoding="utf-8",
    )
    (config_dir / "sec-edgar.yaml").write_text(
        "enabled: false\n",
        encoding="utf-8",
    )
    (config_dir / "eodhd.yaml").write_text(
        "\n".join(
            [
                "enabled: false",
                "api_token_env: EODHD_TEST_TOKEN",
                "historical_eod:",
                "  endpoint: /eod/{symbol}",
                "  default_period: d",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (config_dir / "eodhd.local.yaml").write_text(
        "\n".join(
            [
                "api_token: local-token",
                "historical_eod:",
                "  default_period: w",
                "",
            ]
        ),
        encoding="utf-8",
    )
