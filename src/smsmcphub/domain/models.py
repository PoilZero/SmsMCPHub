from __future__ import annotations

import base64
import hashlib
import json
import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MessageStatus(StrEnum):
    UNREAD = "unread"
    READ = "read"
    ARCHIVED = "archived"


class IncomingMessage(BaseModel):
    """Provider-neutral message produced by an adapter."""

    model_config = ConfigDict(extra="forbid")

    sender: str
    body: str
    recipient: str | None = None
    received_at: datetime | None = None
    forwarded_at: datetime | None = None
    dedupe_key: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    raw_payload: dict[str, Any] | list[Any] | str | None = None

    @field_validator("sender", "body")
    @classmethod
    def required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value


class Message(BaseModel):
    """Canonical persisted SMS message."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    channel: str = "sms"
    source: str
    sender: str
    recipient: str | None = None
    body: str
    received_at: datetime
    forwarded_at: datetime | None = None
    conversation_id: str
    status: MessageStatus = MessageStatus.UNREAD
    dedupe_key: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    raw_payload: dict[str, Any] | list[Any] | str | None = None
    created_at: datetime


class MessageQuery(BaseModel):
    sender: str | None = None
    recipient: str | None = None
    keyword: str | None = None
    since: datetime | None = None
    until: datetime | None = None
    status: MessageStatus | None = None
    limit: int = Field(default=20, ge=1, le=100)
    cursor: str | None = None

    @field_validator("sender", "recipient")
    @classmethod
    def normalize_address_filter(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return normalize_address(cleaned) or cleaned or None

    @field_validator("keyword")
    @classmethod
    def clean_keyword(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("since", "until")
    @classmethod
    def normalize_datetime(cls, value: datetime | None) -> datetime | None:
        return to_utc(value) if value else None


class ConversationQuery(BaseModel):
    limit: int = Field(default=20, ge=1, le=100)
    cursor: str | None = None


class MessageSearchResult(BaseModel):
    messages: list[Message]
    next_cursor: str | None = None


class LatestMessageResult(BaseModel):
    found: bool
    message: Message | None = None


class ConversationSummary(BaseModel):
    conversation_id: str
    peer: str | None = None
    last_message_at: datetime
    message_count: int
    preview: str


class ConversationResult(BaseModel):
    conversations: list[ConversationSummary]
    next_cursor: str | None = None


def to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def serialize_datetime(value: datetime) -> str:
    return to_utc(value).isoformat().replace("+00:00", "Z")


def parse_datetime(value: str | int | float | datetime | None) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return to_utc(value)
    if isinstance(value, (int, float)) or (
        isinstance(value, str) and re.fullmatch(r"-?\d+(?:\.\d+)?", value.strip())
    ):
        number = float(value)
        if abs(number) >= 100_000_000_000:
            number /= 1000
        return datetime.fromtimestamp(number, tz=UTC)
    text = str(value).strip()
    normalized = text.replace("Z", "+00:00")
    try:
        return to_utc(datetime.fromisoformat(normalized))
    except ValueError:
        pass
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%b %d, %Y %I:%M:%S %p",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    raise ValueError(f"Unsupported datetime value: {value!r}")


def normalize_address(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    if text.startswith("+"):
        return "+" + re.sub(r"\D", "", text[1:])
    if re.search(r"\d", text):
        return re.sub(r"[\s().-]", "", text)
    return text


def make_conversation_id(sender: str, recipient: str | None) -> str:
    addresses = sorted((sender, recipient or ""))
    digest = hashlib.sha256("|".join(addresses).encode("utf-8")).hexdigest()[:24]
    return f"conv_{digest}"


def make_fallback_dedupe_key(source: str, message: IncomingMessage) -> str:
    payload = {
        "source": source,
        "sender": normalize_address(message.sender),
        "recipient": normalize_address(message.recipient),
        "body": message.body,
        "received_at": serialize_datetime(message.received_at) if message.received_at else None,
        "forwarded_at": serialize_datetime(message.forwarded_at) if message.forwarded_at else None,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def encode_cursor(offset: int) -> str:
    if offset < 0:
        raise ValueError("cursor offset cannot be negative")
    raw = str(offset).encode("ascii")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        offset = int(base64.urlsafe_b64decode(padded.encode("ascii")).decode("ascii"))
    except (ValueError, UnicodeError, base64.binascii.Error) as exc:
        raise ValueError("invalid cursor") from exc
    if offset < 0:
        raise ValueError("invalid cursor")
    return offset
