from __future__ import annotations

import base64
import hashlib
import hmac
from urllib.parse import quote_plus


def _signature(timestamp: str, secret: str) -> str:
    digest = hmac.new(secret.encode(), f"{timestamp}\n{secret}".encode(), hashlib.sha256).digest()
    return quote_plus(base64.b64encode(digest).decode())


def test_health_and_webhook_ingestion(client):
    assert client.get("/healthz").json() == {"status": "ok"}
    response = client.post(
        "/api/v1/providers/phone-main/webhook",
        data={"from": "+8613800000000", "content": "验证码 123456"},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["accepted"] is True
    assert result["duplicates"] == 0
    assert len(result["message_ids"]) == 1

    messages = client.get("/api/v1/messages", params={"keyword": "123456"})
    assert messages.status_code == 200
    assert messages.json()["messages"][0]["body"] == "验证码 123456"


def test_duplicate_webhook_is_idempotent(client):
    body = {
        "from": "10086",
        "content": "event with timestamp",
        "timestamp": "1730000000000",
    }
    first = client.post(
        "/api/v1/providers/phone-main/webhook",
        data=body,
    ).json()
    second = client.post(
        "/api/v1/providers/phone-main/webhook",
        data=body,
    ).json()
    assert first["duplicates"] == 0
    assert second["duplicates"] == 1
    assert second["message_ids"] == first["message_ids"]
    assert client.get("/api/v1/messages").json()["messages"]


def test_signed_webhook_and_unknown_provider(client):
    # The fixture provider is unsigned; unknown routes should not be accepted.
    assert client.post("/api/v1/providers/missing/webhook", data={}).status_code == 404


def test_json_mapping_webhook(client):
    response = client.post(
        "/api/v1/providers/phone-main/webhook",
        json={
            "from": "+8613900000000",
            "content": "JSON message",
            "receive_time": "2026-09-03T10:20:30Z",
            "device_mark": "main-phone",
        },
    )
    assert response.status_code == 200
    message = client.get(f"/api/v1/messages/{response.json()['message_ids'][0]}").json()
    assert message["received_at"] == "2026-09-03T10:20:30Z"
    assert message["metadata"]["device_mark"] == "main-phone"
