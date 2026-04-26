from __future__ import annotations

from dataclasses import dataclass
from os import getenv
from pathlib import Path


@dataclass
class AppConfig:
    telegram_bot_token: str
    db_path: Path
    upload_dir: Path
    llm_provider: str
    llm_api_key: str | None
    llm_model: str
    llm_base_url: str | None
    openrouter_site_url: str | None
    openrouter_app_name: str | None
    manager_chat_id: int | None
    enable_viber_ingest: bool
    viber_host: str
    viber_port: int
    viber_webhook_path: str
    viber_auth_token: str | None


def _env_bool(name: str, default: bool = False) -> bool:
    raw = getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def load_config() -> AppConfig:
    token = getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

    db_path = Path(getenv("APP_DB_PATH", "./data/app.db"))
    upload_dir = Path(getenv("APP_UPLOAD_DIR", "./data/uploads"))
    llm_provider = getenv("LLM_PROVIDER", "openai").strip().lower()
    llm_model = getenv("LLM_MODEL", getenv("OPENAI_MODEL", "gpt-4.1-mini"))
    llm_api_key = getenv("LLM_API_KEY")
    if not llm_api_key:
        if llm_provider == "openrouter":
            llm_api_key = getenv("OPENROUTER_API_KEY")
        else:
            llm_api_key = getenv("OPENAI_API_KEY")
    llm_base_url = getenv("LLM_BASE_URL")
    openrouter_site_url = getenv("OPENROUTER_SITE_URL")
    openrouter_app_name = getenv("OPENROUTER_APP_NAME", "sales-order-bot")
    manager_chat_id_raw = getenv("MANAGER_CHAT_ID")
    manager_chat_id = int(manager_chat_id_raw) if manager_chat_id_raw else None

    enable_viber_ingest = _env_bool("ENABLE_VIBER_INGEST", False)
    viber_host = getenv("VIBER_HOST", "0.0.0.0")
    viber_port = int(getenv("VIBER_PORT", "8088"))
    viber_webhook_path = getenv("VIBER_WEBHOOK_PATH", "/webhook/viber")
    viber_auth_token = getenv("VIBER_AUTH_TOKEN")

    return AppConfig(
        telegram_bot_token=token,
        db_path=db_path,
        upload_dir=upload_dir,
        llm_provider=llm_provider,
        llm_api_key=llm_api_key,
        llm_model=llm_model,
        llm_base_url=llm_base_url,
        openrouter_site_url=openrouter_site_url,
        openrouter_app_name=openrouter_app_name,
        manager_chat_id=manager_chat_id,
        enable_viber_ingest=enable_viber_ingest,
        viber_host=viber_host,
        viber_port=viber_port,
        viber_webhook_path=viber_webhook_path,
        viber_auth_token=viber_auth_token,
    )
