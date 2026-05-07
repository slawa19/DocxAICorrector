from pathlib import Path


def resolve_repo_root(start: Path) -> Path:
    start = start.resolve()
    for candidate in (start, *start.parents):
        if (candidate / "config.toml").exists() and (candidate / "prompts").is_dir() and (candidate / "pyproject.toml").exists():
            return candidate
    raise RuntimeError("Could not resolve DocxAICorrector repository root")


BASE_DIR = resolve_repo_root(Path(__file__).resolve())
PROMPTS_DIR = BASE_DIR / "prompts"
ENV_PATH = BASE_DIR / ".env"
CONFIG_PATH = BASE_DIR / "config.toml"
SYSTEM_PROMPT_PATH = PROMPTS_DIR / "system_prompt.txt"
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
