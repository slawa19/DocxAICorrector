from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROMPTS_DIR = BASE_DIR / "prompts"
ENV_PATH = BASE_DIR / ".env"
CONFIG_PATH = BASE_DIR / "config.toml"
SYSTEM_PROMPT_PATH = PROMPTS_DIR / "system_prompt.txt"
RUN_DIR = BASE_DIR / ".run"
APP_LOG_PATH = RUN_DIR / "app.log"

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
