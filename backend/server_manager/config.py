import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

SERVER_MANAGER_DIR = Path(__file__).resolve().parent
load_dotenv(SERVER_MANAGER_DIR / ".env")


def _env(name: str) -> Optional[str]:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _required(name: str) -> str:
    value = _env(name)
    if value is None:
        raise RuntimeError(f"Set {name} in server_manager/.env")
    return value


def _int(name: str, default: int) -> int:
    raw = _env(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    log_level: str
    api_key: str
    fernet_key: str
    public_url: str
    firebase_service_account_path: Optional[str]
    install_timeout_s: int
    install_poll_interval_s: int
    traffic_sync_interval_s: int
    health_interval_s: int
    monitoring_sync_interval_s: int
    subscription_sync_interval_s: int
    monitoring_targets_path: Optional[str]
    panel_request_timeout_s: int
    sub_path: str
    remnawave_base_url: Optional[str]
    remnawave_api_token: Optional[str]
    remnawave_sync_interval_s: int

    @property
    def panel_request_timeout(self) -> float:
        return float(self.panel_request_timeout_s)


def _service_account_path() -> Optional[str]:
    raw = (
        _env("FIREBASE_SERVICE_ACCOUNT_PATH")
        or _env("FIREBASE_CREDENTIALS_PATH")
        or _env("GOOGLE_APPLICATION_CREDENTIALS")
    )
    if raw is None:
        return None
    candidate = Path(raw).expanduser()
    if candidate.is_absolute():
        return str(candidate)
    candidates = [
        Path.cwd() / candidate,
        SERVER_MANAGER_DIR / candidate,
        SERVER_MANAGER_DIR.parent / candidate,
        SERVER_MANAGER_DIR.parent / "bot" / candidate,
        SERVER_MANAGER_DIR.parent / "bot_admin" / candidate,
    ]
    for path in candidates:
        if path.exists():
            return str(path)
    return str(candidates[0])


def _load_settings() -> Settings:
    public_url = _required("MANAGER_PUBLIC_URL").rstrip("/")
    return Settings(
        host=_env("MANAGER_HOST") or "0.0.0.0",
        port=_int("MANAGER_PORT", 8080),
        log_level=(_env("MANAGER_LOG_LEVEL") or "info").lower(),
        api_key=_required("MANAGER_API_KEY"),
        fernet_key=_required("SERVER_MANAGER_FERNET_KEY"),
        public_url=public_url,
        firebase_service_account_path=_service_account_path(),
        install_timeout_s=_int("INSTALL_TIMEOUT_S", 900),
        install_poll_interval_s=_int("INSTALL_POLL_INTERVAL_S", 3),
        traffic_sync_interval_s=_int("TRAFFIC_SYNC_INTERVAL_S", 300),
        health_interval_s=_int("HEALTH_INTERVAL_S", 120),
        monitoring_sync_interval_s=_int("MONITORING_SYNC_INTERVAL_S", 60),
        subscription_sync_interval_s=_int("SUBSCRIPTION_SYNC_INTERVAL_S", 300),
        monitoring_targets_path=_env("MONITORING_TARGETS_PATH"),
        panel_request_timeout_s=_int("PANEL_REQUEST_TIMEOUT_S", 30),
        sub_path=(_env("MANAGER_SUB_PATH") or "/sub").rstrip("/") or "/sub",
        # Remnawave
        remnawave_base_url=_env("REMNAWAVE_BASE_URL"),
        remnawave_api_token=_env("REMNAWAVE_API_TOKEN"),
        remnawave_sync_interval_s=_int("REMNAWAVE_SYNC_INTERVAL_S", 300),
    )


settings = _load_settings()
