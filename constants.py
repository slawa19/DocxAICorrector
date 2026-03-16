from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROMPTS_DIR = BASE_DIR / "prompts"
ENV_PATH = BASE_DIR / ".env"
CONFIG_PATH = BASE_DIR / "config.toml"
SYSTEM_PROMPT_PATH = PROMPTS_DIR / "system_prompt.txt"
RUN_DIR = BASE_DIR / ".run"
APP_LOG_PATH = RUN_DIR / "app.log"
APP_READY_PATH = RUN_DIR / "app.ready"

DEFAULT_MODEL = "gpt-5-mini"
DEFAULT_MODEL_OPTIONS = [
    "gpt-5.4",
    "gpt-5.4-pro",
    "gpt-5.2",
    "gpt-5.1",
    "gpt-5-mini",
]
DEFAULT_CHUNK_SIZE = 6000
DEFAULT_MAX_RETRIES = 3
# Keep this in sync with .streamlit/config.toml -> server.maxUploadSize = 25 (MB).
MAX_DOCX_ARCHIVE_SIZE_BYTES = 25 * 1024 * 1024
MAX_DOCX_UNCOMPRESSED_SIZE_BYTES = 100 * 1024 * 1024
MAX_DOCX_ENTRY_COUNT = 2048
MAX_DOCX_COMPRESSION_RATIO = 150.0
