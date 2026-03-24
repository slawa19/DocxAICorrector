from __future__ import annotations

import os
import subprocess
import sys
import time
import tomllib
from pathlib import Path

import config
import generation


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_streamlit_config_disables_costly_file_watching() -> None:
    config_text = (REPO_ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    streamlit_config = tomllib.loads(config_text)

    assert streamlit_config["server"]["fileWatcherType"] == "none"
    assert streamlit_config["server"]["runOnSave"] is False


def test_load_system_prompt_reads_from_disk_once(monkeypatch, tmp_path) -> None:
    prompt_path = tmp_path / "system_prompt.txt"
    prompt_path.write_text("system prompt", encoding="utf-8")
    calls: list[Path] = []
    original_read_text = Path.read_text

    def counting_read_text(self: Path, *args, **kwargs) -> str:
        if self == prompt_path:
            calls.append(self)
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(config, "SYSTEM_PROMPT_PATH", prompt_path)
    monkeypatch.setattr(Path, "read_text", counting_read_text)
    config.load_system_prompt.cache_clear()

    try:
        assert config.load_system_prompt() == "system prompt"
        assert config.load_system_prompt() == "system prompt"
    finally:
        config.load_system_prompt.cache_clear()

    assert calls == [prompt_path]


def test_get_client_reuses_singleton_instance(monkeypatch, tmp_path) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("OPENAI_API_KEY=test-key\n", encoding="utf-8")
    created_instances: list[object] = []

    class FakeOpenAI:
        def __init__(self, *, api_key: str):
            self.api_key = api_key
            created_instances.append(self)

    monkeypatch.setattr(config, "ENV_PATH", dotenv_path)
    monkeypatch.setattr(config, "OpenAI", FakeOpenAI)
    monkeypatch.setattr(config, "_CLIENT", None)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    try:
        first = config.get_client()
        second = config.get_client()
    finally:
        config._CLIENT = None

    assert first is second
    assert len(created_instances) == 1


def test_ensure_pandoc_available_is_cached(monkeypatch) -> None:
    calls: list[str] = []

    def fake_get_pandoc_version() -> str:
        calls.append("pandoc")
        return "3.1"

    generation.ensure_pandoc_available.cache_clear()
    monkeypatch.setattr(generation.pypandoc, "get_pandoc_version", fake_get_pandoc_version)

    try:
        generation.ensure_pandoc_available()
        generation.ensure_pandoc_available()
    finally:
        generation.ensure_pandoc_available.cache_clear()

    assert calls == ["pandoc"]


def test_cold_import_budget_is_within_contract() -> None:
    budget_seconds = float(os.getenv("DOCX_AI_STARTUP_IMPORT_BUDGET_SECONDS", "20"))
    started_at = time.perf_counter()
    result = subprocess.run(
        [sys.executable, "-c", "import app"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=max(30.0, budget_seconds + 10.0),
    )
    elapsed_seconds = time.perf_counter() - started_at

    assert result.returncode == 0, result.stdout + result.stderr
    assert elapsed_seconds <= budget_seconds, (
        f"Cold import exceeded budget: {elapsed_seconds:.2f}s > {budget_seconds:.2f}s"
    )