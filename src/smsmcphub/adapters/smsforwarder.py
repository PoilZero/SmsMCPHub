from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote_plus

from smsmcphub.adapters.base import (
    ProviderAdapter,
    ProviderAuthenticationError,
    ProviderPayloadError,
)
from smsmcphub.config import ProviderConfig
from smsmcphub.domain.models import IncomingMessage, parse_datetime


class SmsForwarderAdapter(ProviderAdapter):
    """Adapter for SmsForwarder's HTTP Webhook channel.

    SmsForwarder sends ``from``, ``content``, ``timestamp`` and ``sign`` as a
    form by default. Its configurable JSON template can use arbitrary keys, so
    ``ProviderConfig.mapping`` is applied after parsing.
    """

    name = "smsforwarder"

    _aliases: dict[str, tuple[str, ...]] = {
        "sender": ("from", "sender", "phone", "number", "source"),
        "body": ("content", "message", "body", "msg", "text", "org_content"),
        "recipient": ("to", "recipient", "receiver", "destination", "target"),
        "received_at": (
            "receive_time",
            "received_at",
            "receivedAt",
            "sms_time",
            "date",
            "received_time",
        ),
        "forwarded_at": ("forwarded_at", "forwardedAt", "timestamp"),
        "event_id": ("event_id", "eventId", "message_id", "messageId", "id", "uuid"),
    }

    def verify_request(
        self, body: bytes, headers: Mapping[str, str], config: ProviderConfig
    ) -> None:
        if not config.secret:
            if config.require_signature:
                raise ProviderAuthenticationError("SmsForwarder signature is required")
            return

        payload = self._decode_payload(body, headers)
        timestamp = self._lookup(payload, headers, ("timestamp", "ts"), config)
        signature = self._header(headers, "x-smsmcphub-signature") or self._lookup(
            payload, headers, ("sign", "signature"), config
        )
        if timestamp is None or signature is None:
            raise ProviderAuthenticationError("SmsForwarder timestamp and sign are required")
        timestamp_text = str(timestamp).strip()
        try:
            timestamp_seconds = float(timestamp_text)
            if abs(timestamp_seconds) >= 100_000_000_000:
                timestamp_seconds /= 1000
        except ValueError as exc:
            raise ProviderAuthenticationError("SmsForwarder timestamp is invalid") from exc
        if abs(time.time() - timestamp_seconds) > config.signature_tolerance_seconds:
            raise ProviderAuthenticationError("SmsForwarder request timestamp is too old")

        provided_raw = str(signature).strip()
        provided_candidates = (provided_raw, unquote_plus(provided_raw))
        message = f"{timestamp_text}\n{config.secret}".encode()
        expected = base64.b64encode(
            hmac.new(config.secret.encode("utf-8"), message, hashlib.sha256).digest()
        ).decode("ascii")
        candidates = (expected, quote_plus(expected))
        if not any(
            hmac.compare_digest(provided, candidate)
            for provided in provided_candidates
            for candidate in candidates
        ):
            raise ProviderAuthenticationError("SmsForwarder signature is invalid")

    def parse_messages(
        self, body: bytes, headers: Mapping[str, str], config: ProviderConfig
    ) -> list[IncomingMessage]:
        payload = self._decode_payload(body, headers)
        items: list[Mapping[str, Any]]
        if isinstance(payload, list):
            items = [item for item in payload if isinstance(item, Mapping)]
            if len(items) != len(payload):
                raise ProviderPayloadError("SmsForwarder JSON array must contain objects")
        elif isinstance(payload, Mapping):
            items = [payload]
        else:
            raise ProviderPayloadError("SmsForwarder payload must be an object or array")
        if not items:
            raise ProviderPayloadError("SmsForwarder payload contains no messages")

        parsed: list[IncomingMessage] = []
        for item in items:
            sender = self._field(item, "sender", config)
            content = self._field(item, "body", config)
            if sender is None or content is None:
                raise ProviderPayloadError(
                    "SmsForwarder payload requires sender (from) and content fields"
                )
            try:
                received_at = parse_datetime(self._field(item, "received_at", config))
                forwarded_at = parse_datetime(self._field(item, "forwarded_at", config))
            except ValueError as exc:
                raise ProviderPayloadError(str(exc)) from exc
            event_id = self._field(item, "event_id", config)
            metadata = {
                key: value
                for key, value in item.items()
                if key
                not in {
                    "from",
                    "sender",
                    "phone",
                    "number",
                    "source",
                    "content",
                    "message",
                    "body",
                    "msg",
                    "text",
                    "org_content",
                    "to",
                    "recipient",
                    "receiver",
                    "destination",
                    "target",
                    "receive_time",
                    "received_at",
                    "receivedAt",
                    "sms_time",
                    "date",
                    "received_time",
                    "timestamp",
                    "forwarded_at",
                    "forwardedAt",
                    "event_id",
                    "eventId",
                    "message_id",
                    "messageId",
                    "id",
                    "uuid",
                    "sign",
                    "signature",
                }
            }
            parsed.append(
                IncomingMessage(
                    sender=str(sender),
                    body=str(content),
                    recipient=self._as_optional_text(self._field(item, "recipient", config)),
                    received_at=received_at,
                    forwarded_at=forwarded_at,
                    dedupe_key=self._as_optional_text(event_id),
                    metadata=metadata,
                    raw_payload=dict(item),
                )
            )
        return parsed

    def _field(self, item: Mapping[str, Any], field: str, config: ProviderConfig) -> Any:
        mapping_path = config.mapping.get(field)
        if mapping_path:
            return self._extract(item, mapping_path)
        for alias in self._aliases[field]:
            if alias in item and item[alias] not in (None, ""):
                return item[alias]
        return None

    @staticmethod
    def _extract(value: Any, path: str) -> Any:
        if path in {"$", ""}:
            return value
        current = value
        normalized = path[2:] if path.startswith("$.") else path.lstrip(".")
        for part in normalized.split("."):
            if not part:
                continue
            if isinstance(current, Mapping):
                if part not in current:
                    return None
                current = current[part]
            elif isinstance(current, list) and part.isdigit():
                index = int(part)
                if index >= len(current):
                    return None
                current = current[index]
            else:
                return None
        return current

    def _decode_payload(self, body: bytes, headers: Mapping[str, str]) -> Any:
        content_type = (self._header(headers, "content-type") or "").lower()
        try:
            text = body.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise ProviderPayloadError("SmsForwarder payload must be UTF-8") from exc
        if "application/json" in content_type or text.lstrip().startswith(("{", "[")):
            try:
                return json.loads(text)
            except json.JSONDecodeError as exc:
                raise ProviderPayloadError("SmsForwarder JSON payload is invalid") from exc
        if "application/x-www-form-urlencoded" in content_type or "form-urlencoded" in content_type:
            values = parse_qs(text, keep_blank_values=True)
            return {key: entries[-1] if entries else "" for key, entries in values.items()}
        if ("text/plain" in content_type or not content_type) and "=" in text:
            values = parse_qs(text, keep_blank_values=True)
            return {key: entries[-1] if entries else "" for key, entries in values.items()}
        raise ProviderPayloadError(
            "SmsForwarder requires application/json or application/x-www-form-urlencoded"
        )

    @staticmethod
    def _header(headers: Mapping[str, str], name: str) -> str | None:
        wanted = name.lower()
        for key, value in headers.items():
            if key.lower() == wanted:
                return value
        return None

    def _lookup(
        self,
        payload: Any,
        headers: Mapping[str, str],
        names: tuple[str, ...],
        config: ProviderConfig | None = None,
    ) -> Any:
        header_timestamp = self._header(headers, "x-smsmcphub-timestamp")
        if header_timestamp is not None and "timestamp" in names:
            return header_timestamp
        if isinstance(payload, Mapping):
            for name in names:
                path = config.mapping.get(name) if config else None
                value = self._extract(payload, path) if path else payload.get(name)
                if value not in (None, ""):
                    return value
        return None

    @staticmethod
    def _as_optional_text(value: Any) -> str | None:
        if value in (None, ""):
            return None
        return str(value)
