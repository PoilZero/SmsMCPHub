from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel

from smsmcphub.adapters.base import ProviderAuthenticationError, ProviderPayloadError
from smsmcphub.adapters.smsforwarder import SmsForwarderAdapter
from smsmcphub.config import AppSettings, ProviderConfig
from smsmcphub.domain.models import MessageQuery, MessageStatus
from smsmcphub.domain.service import MessageService
from smsmcphub.mcp.server import create_mcp_server
from smsmcphub.storage.sqlite import SQLiteRepository


class IngestResponse(BaseModel):
    accepted: bool
    message_ids: list[str]
    duplicates: int


class ProviderBinding:
    def __init__(self, config: ProviderConfig, adapter) -> None:
        self.config = config
        self.adapter = adapter


class ProviderRegistry:
    def __init__(self, configs: tuple[ProviderConfig, ...]) -> None:
        self._bindings: dict[str, ProviderBinding] = {}
        for config in configs:
            adapter = _adapter_for(config)
            self._bindings[config.id] = ProviderBinding(config, adapter)

    def get(self, provider_id: str) -> ProviderBinding | None:
        return self._bindings.get(provider_id)


def create_app(
    settings: AppSettings | None = None,
    *,
    repository: SQLiteRepository | None = None,
    service: MessageService | None = None,
) -> FastAPI:
    settings = settings or AppSettings.from_env()
    repository = repository or SQLiteRepository(settings.database_path)
    service = service or MessageService(repository, save_raw_payload=settings.save_raw_payload)
    registry = ProviderRegistry(settings.providers or _default_providers())
    mcp = create_mcp_server(service)
    mcp_app = _make_mcp_http_app(mcp)

    app = FastAPI(title="SmsMCPHub", version="0.1.0", lifespan=mcp_app.lifespan)
    app.state.settings = settings
    app.state.repository = repository
    app.state.service = service
    app.state.providers = registry
    app.state.mcp = mcp

    @app.middleware("http")
    async def mcp_authentication(request: Request, call_next):
        token = settings.mcp_token
        mcp_prefix = settings.mcp_path.rstrip("/") or "/mcp"
        if token and (
            request.url.path == mcp_prefix or request.url.path.startswith(f"{mcp_prefix}/")
        ):
            authorization = request.headers.get("authorization", "")
            if authorization != f"Bearer {token}":
                return _json_error_response(401, "MCP authentication required")
        return await call_next(request)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        try:
            repository.healthcheck()
        except Exception as exc:
            raise HTTPException(status_code=503, detail="storage unavailable") from exc
        return {"status": "ok"}

    @app.post(
        "/api/v1/providers/{provider_id}/webhook",
        response_model=IngestResponse,
    )
    async def provider_webhook(provider_id: str, request: Request) -> IngestResponse:
        binding = registry.get(provider_id)
        if binding is None:
            raise HTTPException(status_code=404, detail="unknown provider")
        body = await request.body()
        headers: Mapping[str, str] = request.headers
        try:
            binding.adapter.verify_request(body, headers, binding.config)
            incoming = binding.adapter.parse_messages(body, headers, binding.config)
        except ProviderAuthenticationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except ProviderPayloadError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        stored, duplicates = service.ingest(
            binding.adapter.name,
            incoming,
            provider_id=provider_id,
            save_raw_payload=(binding.config.save_raw_payload or settings.save_raw_payload),
        )
        return IngestResponse(
            accepted=True,
            message_ids=[message.id for message in stored],
            duplicates=duplicates,
        )

    @app.get("/api/v1/messages/{message_id}")
    def get_message(message_id: str) -> dict[str, Any]:
        message = service.get(message_id)
        if message is None:
            raise HTTPException(status_code=404, detail="message not found")
        return message.model_dump(mode="json")

    @app.get("/api/v1/messages")
    def search_messages(
        sender: str | None = None,
        recipient: str | None = None,
        keyword: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        status: MessageStatus | None = None,
        limit: int = Query(default=20, ge=1, le=100),
        cursor: str | None = None,
    ) -> dict[str, Any]:
        query = MessageQuery(
            sender=sender,
            recipient=recipient,
            keyword=keyword,
            since=since,
            until=until,
            status=status,
            limit=limit,
            cursor=cursor,
        )
        try:
            result = service.search(query)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return result.model_dump(mode="json")

    # FastMCP owns its session lifecycle; it is mounted after the API routes.
    app.mount(settings.mcp_path.rstrip("/") or "/mcp", mcp_app)
    return app


def _default_providers() -> tuple[ProviderConfig, ...]:
    return (ProviderConfig(id="smsforwarder"),)


def _adapter_for(config: ProviderConfig):
    if config.type.lower() == "smsforwarder":
        if config.transport.lower() != "webhook":
            raise ValueError("SmsForwarder MVP adapter only supports webhook transport")
        return SmsForwarderAdapter()
    raise ValueError(f"Unsupported provider type: {config.type}")


def _make_mcp_http_app(mcp):
    if hasattr(mcp, "http_app"):
        return mcp.http_app(path="/", transport="streamable-http")
    if hasattr(mcp, "streamable_http_app"):
        return mcp.streamable_http_app()
    raise RuntimeError("Installed FastMCP does not expose an HTTP ASGI app")


def _json_error_response(status_code: int, detail: str):
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=status_code, content={"detail": detail})
