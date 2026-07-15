import os
from pathlib import Path


def resolve_repo_root(start: Path) -> Path:
    """Best-effort writable working root.

    In a dev checkout this is the repository root, identified by the stable
    ``pyproject.toml`` + ``scripts/`` marker. When the package is installed as a
    wheel (no checkout on disk) it falls back to ``DOCX_AI_HOME`` or the current
    working directory, so runtime artifacts land somewhere writable instead of
    raising at import time. Read-only resources (prompts/config) do NOT use this —
    they ship inside the package (see RESOURCE_ROOT)."""
    start = start.resolve()
    for candidate in (start, *start.parents):
        if (candidate / "pyproject.toml").exists() and (candidate / "scripts").is_dir():
            return candidate
    override = os.environ.get("DOCX_AI_HOME", "").strip()
    return Path(override).resolve() if override else Path.cwd().resolve()


# Read-only packaged resources (prompts + default config). Resolved relative to
# this module, so `import docxaicorrector` works from an installed wheel with no
# repository checkout on the path.
RESOURCE_ROOT = Path(__file__).resolve().parent.parent / "resources"
PROMPTS_DIR = RESOURCE_ROOT / "prompts"
CONFIG_PATH = RESOURCE_ROOT / "config.toml"
SYSTEM_PROMPT_PATH = PROMPTS_DIR / "system_prompt.txt"

# Writable working root: runtime artifacts, .env, and logs. Repo root in a
# checkout; DOCX_AI_HOME / cwd when installed.
BASE_DIR = resolve_repo_root(Path(__file__).resolve())
ENV_PATH = BASE_DIR / ".env"
RUN_DIR = BASE_DIR / ".run"
UI_RESULT_ARTIFACTS_DIR = RUN_DIR / "ui_results"
STRUCTURE_MANIFESTS_DIR = RUN_DIR / "structure_manifests"
SEGMENT_RESULT_REGISTRY_DIR = RUN_DIR / "segment_results"
JOB_RESULT_REGISTRY_DIR = RUN_DIR / "job_results"
APP_LOG_PATH = RUN_DIR / "app.log"
APP_READY_PATH = RUN_DIR / "app.ready"

DEFAULT_CHUNK_SIZE = 6000
DEFAULT_MAX_RETRIES = 3
# Keep this in sync with .streamlit/config.toml -> server.maxUploadSize = 25 (MB).
MAX_DOCX_ARCHIVE_SIZE_BYTES = 25 * 1024 * 1024
MAX_DOCX_UNCOMPRESSED_SIZE_BYTES = 100 * 1024 * 1024
MAX_DOCX_ENTRY_COUNT = 2048
MAX_DOCX_COMPRESSION_RATIO = 150.0
