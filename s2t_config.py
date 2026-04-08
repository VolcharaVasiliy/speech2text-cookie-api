from __future__ import annotations

import os
import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
COLLECTION_ROOT = PROJECT_ROOT / "collection"
DEFAULT_BASE_URL = "https://speech2text.ru"
DEFAULT_ACCEPT_LANGUAGE = "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

ENV_VAR_ALIASES: dict[str, tuple[str, ...]] = {
    "base_url": ("S2T_BASE_URL",),
    "accept_language": ("S2T_ACCEPT_LANGUAGE",),
    "user_agent": ("S2T_USER_AGENT",),
    "cookie_header": ("S2T_COOKIE_HEADER", "S2T_COOKIE"),
    "job_id": ("S2T_JOB_ID",),
    "audio_file_name": ("S2T_AUDIO_FILE_NAME", "S2T_AUDIO_FILE"),
    "client_id": ("S2T_CLIENT_ID",),
}


def parse_bru_vars(env_file: Path) -> dict[str, str]:
    if not env_file.is_file():
        return {}

    values: dict[str, str] = {}
    content = env_file.read_text(encoding="utf-8")
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line in {"vars {", "}"}:
            continue
        name, separator, value = line.partition(":")
        if not separator:
            continue
        values[name.strip()] = value.strip().strip('"')
    return values


def resolve_project_root() -> Path:
    return PROJECT_ROOT


def resolve_collection_root() -> Path:
    return COLLECTION_ROOT


def default_env_file() -> Path:
    configured = os.getenv("S2T_ENV_FILE")
    if configured:
        return Path(configured)

    primary = COLLECTION_ROOT / "environments" / "local.bru"
    if primary.exists():
        return primary

    return COLLECTION_ROOT / "environments" / "local.bru.example"


def default_reports_root() -> Path:
    configured = os.getenv("S2T_REPORTS_ROOT")
    if configured:
        return Path(configured)
    if os.getenv("VERCEL"):
        return Path("/tmp/s2t-bru-reports")
    return PROJECT_ROOT / "tmp" / "reports"


def default_browser_executable() -> Path:
    configured = os.getenv("S2T_BROWSER_EXE")
    if configured:
        return Path(configured)

    candidates = (
        Path(r"C:\Users\gamer\AppData\Local\Yandex\YandexBrowser\Application\browser.exe"),
        Path(r"F:\DD\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0]


def default_bru_cmd() -> Path | None:
    configured = os.getenv("BRU_CMD")
    if configured:
        return Path(configured)

    located = shutil.which("bru")
    if located:
        return Path(located)

    candidates = (
        Path(r"F:\DevTools\Portable\bin\bru.cmd"),
        Path(r"F:\DevTools\Portable\BrunoCli\bru.cmd"),
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def default_nodejs_root() -> Path | None:
    configured = os.getenv("NODEJS_ROOT")
    if configured:
        return Path(configured)

    node_path = shutil.which("node")
    if node_path:
        return Path(node_path).resolve().parent

    candidate = Path(r"F:\DevTools\Portable\NodeJS")
    if candidate.exists():
        return candidate
    return None


def load_runtime_defaults(env_file: Path | None = None) -> dict[str, str]:
    resolved_env_file = env_file or default_env_file()
    values = parse_bru_vars(resolved_env_file)

    defaults = {
        "base_url": DEFAULT_BASE_URL,
        "accept_language": DEFAULT_ACCEPT_LANGUAGE,
        "user_agent": DEFAULT_USER_AGENT,
    }
    for key, value in defaults.items():
        values.setdefault(key, value)

    for key, env_names in ENV_VAR_ALIASES.items():
        for env_name in env_names:
            env_value = os.getenv(env_name)
            if env_value:
                values[key] = env_value
                break

    return values
