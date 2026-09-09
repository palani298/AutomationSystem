from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_host: str = "127.0.0.1"
    app_port: int = 8787
    public_base_url: str = "http://127.0.0.1:8787"

    database_path: Path = ROOT / "data" / "registry.sqlite"
    evidence_dir: Path = ROOT / "evidence"

    allowlist_hosts: str = "127.0.0.1,localhost"

    llm_provider: str = "openai"
    llm_model: str = "gpt-4.1"
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"

    playwright_headless: bool = False
    playwright_slow_mo_ms: int = 80
    max_discovery_steps: int = 14
    action_timeout_ms: int = 8000

    temporal_address: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "capability-forge"

    # Optional Slack/email/ticket URL for admins who do not have the UI open.
    # An open console uses /ws/admin instead (connects on page load, gone on tab close).
    approval_webhook_url: str = ""

    @property
    def allowlist_host_set(self) -> set[str]:
        return {h.strip().lower() for h in self.allowlist_hosts.split(",") if h.strip()}

    @property
    def corebank_url(self) -> str:
        return f"{self.public_base_url.rstrip('/')}/corebank/"


settings = Settings()
