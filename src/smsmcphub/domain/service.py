from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from smsmcphub.domain.models import (
    ConversationQuery,
    ConversationResult,
    IncomingMessage,
    LatestMessageResult,
    Message,
    MessageQuery,
    MessageSearchResult,
    make_conversation_id,
    make_fallback_dedupe_key,
    normalize_address,
    to_utc,
)


class MessageService:
    def __init__(
        self,
        repository,
        *,
        save_raw_payload: bool = False,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.save_raw_payload = save_raw_payload
        self.clock = clock or (lambda: datetime.now(UTC))

    def ingest(
        self,
        source: str,
        messages: list[IncomingMessage],
        *,
        provider_id: str | None = None,
        save_raw_payload: bool | None = None,
    ) -> tuple[list[Message], int]:
        stored: list[Message] = []
        duplicates = 0
        preserve_raw = self.save_raw_payload if save_raw_payload is None else save_raw_payload
        for incoming in messages:
            now = to_utc(self.clock())
            sender = normalize_address(incoming.sender) or incoming.sender.strip()
            recipient = normalize_address(incoming.recipient)
            received_at = to_utc(incoming.received_at or now)
            forwarded_at = to_utc(incoming.forwarded_at) if incoming.forwarded_at else None
            dedupe = incoming.dedupe_key or make_fallback_dedupe_key(source, incoming)
            namespace = provider_id or source
            dedupe_key = f"{source}:{namespace}:{dedupe}"
            metadata = dict(incoming.metadata)
            if provider_id:
                metadata.setdefault("provider_id", provider_id)
            message = Message(
                id=f"msg_{uuid.uuid4().hex}",
                channel="sms",
                source=source,
                sender=sender,
                recipient=recipient,
                body=incoming.body.strip(),
                received_at=received_at,
                forwarded_at=forwarded_at,
                conversation_id=make_conversation_id(sender, recipient),
                dedupe_key=dedupe_key,
                metadata=metadata,
                raw_payload=incoming.raw_payload if preserve_raw else None,
                created_at=now,
            )
            persisted, created = self.repository.insert(message)
            stored.append(persisted)
            if not created:
                duplicates += 1
        return stored, duplicates

    def get(self, message_id: str) -> Message | None:
        return self.repository.get(message_id)

    def search(self, query: MessageQuery) -> MessageSearchResult:
        messages, next_cursor = self.repository.search(query)
        return MessageSearchResult(messages=messages, next_cursor=next_cursor)

    def latest(
        self,
        *,
        sender: str | None = None,
        keyword: str | None = None,
        within_minutes: int = 10,
    ) -> LatestMessageResult:
        if within_minutes < 1 or within_minutes > 1440:
            raise ValueError("within_minutes must be between 1 and 1440")
        now = to_utc(self.clock())
        query = MessageQuery(
            sender=sender,
            keyword=keyword,
            since=now - timedelta(minutes=within_minutes),
            until=now,
            limit=1,
        )
        result = self.search(query)
        return LatestMessageResult(
            found=bool(result.messages),
            message=result.messages[0] if result.messages else None,
        )

    def conversations(self, query: ConversationQuery) -> ConversationResult:
        conversations, next_cursor = self.repository.conversations(query)
        return ConversationResult(conversations=conversations, next_cursor=next_cursor)
