from __future__ import annotations

import base64
import hashlib
import hmac
import time
from urllib.parse import quote_plus

from fastapi.testclient import TestClient

from smsmcphub.api.app import create_app
from smsmcphub.config import AppSettings, ProviderConfig
from smsmcphub.storage.sqlite import SQLiteRepository


def _signature(timestamp: str, secret: str) -> str:
    digest = hmac.new(secret.encode(), f"{timestamp}\n{secret}".encode(), hashlib.sha256).digest()
    return quote_plus(base64.b64encode(digest).decode())


def test_signed_provider_webhook_and_mcp_token():
    secret = "provider-secret"
    settings = AppSettings(
        database_path=":memory:",
        mcp_token="mcp-token",
        providers=(ProviderConfig(id="phone-main", secret=secret),),
    )
    repository = SQLiteRepository(":memory:")
    app = create_app(settings, repository=repository)
    timestamp = str(round(time.time() * 1000))
    payload = {
        "from": "10086",
        "content": "signed message",
        "timestamp": timestamp,
        "sign": _signature(timestamp, secret),
    }
    with TestClient(app) as client:
        unauthorized = client.get("/mcp")
        assert unauthorized.status_code == 401
        authorized = client.get("/mcp", headers={"authorization": "Bearer mcp-token"})
        assert authorized.status_code != 401

        accepted = client.post(
            "/api/v1/providers/phone-main/webhook",
            data=payload,
        )
        assert accepted.status_code == 200
        payload["sign"] = "invalid"
        rejected = client.post(
            "/api/v1/providers/phone-main/webhook",
            data=payload,
        )
        assert rejected.status_code == 401
    repository.close()
