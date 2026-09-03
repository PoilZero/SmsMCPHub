from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ProviderConfig:
    """Runtime configuration for one inbound provider."""

    id: str
    type: str = "smsforwarder"
    transport: str = "webhook"
    secret: str | None = None
    mapping: dict[str, str] = field(default_factory=dict)
    require_signature: bool = False
    signature_tolerance_seconds: int = 3600
    save_raw_payload: bool = False


@dataclass(frozen=True)
class AppSettings:
    """Application settings with environment-based defaults."""

    database_path: str = "./data/smsmcphub.db"
    save_raw_payload: bool = False
    retention_days: int = 30
    mcp_path: str = "/mcp"
    mcp_token: str | None = None
    providers: tuple[ProviderConfig, ...] = field(default_factory=tuple)

    @classmethod
    def from_env(cls) -> AppSettings:
        mapping_text = os.getenv("SMSFORWARDER_MAPPING", "")
        mapping: dict[str, str] = {}
        if mapping_text:
            try:
                parsed = json.loads(mapping_text)
            except json.JSONDecodeError as exc:
                raise ValueError("SMSFORWARDER_MAPPING must be valid JSON") from exc
            if not isinstance(parsed, dict) or not all(
                isinstance(key, str) and isinstance(value, str) for key, value in parsed.items()
            ):
                raise ValueError("SMSFORWARDER_MAPPING must be a JSON object of strings")
            mapping = parsed

        database_path = os.getenv("SMSMCPHUB_DATABASE_PATH", "./data/smsmcphub.db")
        save_raw = _read_bool(os.getenv("SMSMCPHUB_SAVE_RAW_PAYLOAD"), default=False)
        require_signature = _read_bool(os.getenv("SMSFORWARDER_REQUIRE_SIGNATURE"), default=False)
        secret = os.getenv("SMSFORWARDER_SECRET") or None
        provider = ProviderConfig(
            id=os.getenv("SMSMCPHUB_PROVIDER_ID", "smsforwarder"),
            secret=secret,
            mapping=mapping,
            require_signature=require_signature,
            signature_tolerance_seconds=_read_int(
                os.getenv("SMSFORWARDER_SIGNATURE_TOLERANCE_SECONDS"), default=3600
            ),
            save_raw_payload=save_raw,
        )
        return cls(
            database_path=database_path,
            save_raw_payload=save_raw,
            retention_days=max(0, _read_int(os.getenv("SMSMCPHUB_RETENTION_DAYS"), default=30)),
            mcp_path=os.getenv("SMSMCPHUB_MCP_PATH", "/mcp"),
            mcp_token=os.getenv("SMSMCPHUB_MCP_TOKEN") or None,
            providers=(provider,),
        )


def _read_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _read_int(value: str | None, *, default: int) -> int:
    if value is None or not value.strip():
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"Expected integer setting, got {value!r}") from exc


def ensure_database_parent(path: str) -> None:
    if path == ":memory:":
        return
    Path(path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
