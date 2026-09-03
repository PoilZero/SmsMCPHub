from __future__ import annotations

import base64
import hashlib
import hmac
import time
from urllib.parse import quote_plus

import pytest

from smsmcphub.adapters.base import ProviderAuthenticationError, ProviderPayloadError
from smsmcphub.adapters.smsforwarder import SmsForwarderAdapter
from smsmcphub.config import ProviderConfig


def _signature(timestamp: str, secret: str) -> str:
    data = f"{timestamp}\n{secret}".encode()
    digest = hmac.new(secret.encode(), data, hashlib.sha256).digest()
    return quote_plus(base64.b64encode(digest).decode())


def test_parses_smsforwarder_default_form():
    adapter = SmsForwarderAdapter()
    payload = (
        "from=%2B8613800000000&content=%E9%AA%8C%E8%AF%81%E7%A0%81+123456&timestamp=1730000000000"
    )
    messages = adapter.parse_messages(
        payload.encode(),
        {"content-type": "application/x-www-form-urlencoded"},
        ProviderConfig(id="phone-main"),
    )
    assert len(messages) == 1
    assert messages[0].sender == "+8613800000000"
    assert messages[0].body == "验证码 123456"
    assert messages[0].forwarded_at is not None
    assert messages[0].received_at is None


def test_parses_custom_json_mapping_and_metadata():
    adapter = SmsForwarderAdapter()
    payload = (
        b'{"payload":{"number":"13800000000","text":"hello",'
        b'"when":1730000000000,"event":"e-1"},"device":"main"}'
    )
    config = ProviderConfig(
        id="phone-main",
        mapping={
            "sender": "$.payload.number",
            "body": "$.payload.text",
            "received_at": "$.payload.when",
            "event_id": "$.payload.event",
        },
    )
    messages = adapter.parse_messages(payload, {"content-type": "application/json"}, config)
    assert messages[0].sender == "13800000000"
    assert messages[0].dedupe_key == "e-1"
    assert messages[0].received_at is not None
    assert messages[0].metadata == {
        "payload": {
            "number": "13800000000",
            "text": "hello",
            "when": 1730000000000,
            "event": "e-1",
        },
        "device": "main",
    }


def test_verifies_smsforwarder_signature_and_rejects_replay():
    adapter = SmsForwarderAdapter()
    secret = "test-secret"
    timestamp = str(round(time.time() * 1000))
    body = f"from=10086&content=hello&timestamp={timestamp}&sign={_signature(timestamp, secret)}"
    config = ProviderConfig(id="phone-main", secret=secret)
    adapter.verify_request(
        body.encode(), {"content-type": "application/x-www-form-urlencoded"}, config
    )

    old = "1000000000000"
    replay = f"from=10086&content=hello&timestamp={old}&sign={_signature(old, secret)}"
    with pytest.raises(ProviderAuthenticationError):
        adapter.verify_request(
            replay.encode(), {"content-type": "application/x-www-form-urlencoded"}, config
        )


def test_signature_mapping_supports_nested_json_template():
    adapter = SmsForwarderAdapter()
    secret = "test-secret"
    timestamp = str(round(time.time() * 1000))
    payload = (
        '{"data":{"from":"10086","content":"hello"},'
        f'"auth":{{"timestamp":"{timestamp}","sign":"{_signature(timestamp, secret)}"}}'
        "}"
    )
    config = ProviderConfig(
        id="phone-main",
        secret=secret,
        mapping={"timestamp": "$.auth.timestamp", "signature": "$.auth.sign"},
    )
    adapter.verify_request(payload.encode(), {"content-type": "application/json"}, config)


def test_missing_required_fields_are_rejected():
    adapter = SmsForwarderAdapter()
    with pytest.raises(ProviderPayloadError):
        adapter.parse_messages(
            b"content=hello",
            {"content-type": "application/x-www-form-urlencoded"},
            ProviderConfig(id="phone-main"),
        )
