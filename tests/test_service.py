from __future__ import annotations

from datetime import UTC, datetime

from smsmcphub.domain.models import ConversationQuery, IncomingMessage, MessageQuery


def test_service_normalizes_and_deduplicates(service):
    clock = datetime(2026, 9, 3, 2, 0, tzinfo=UTC)
    service.clock = lambda: clock
    incoming = IncomingMessage(
        sender=" +86 138-0000-0000 ",
        recipient="+86 139 0000 0000",
        body="hello",
        dedupe_key="provider-event-1",
    )
    stored, duplicates = service.ingest("smsforwarder", [incoming])
    again, duplicates_again = service.ingest("smsforwarder", [incoming])
    assert duplicates == 0
    assert duplicates_again == 1
    assert stored[0].id == again[0].id
    assert stored[0].sender == "+8613800000000"
    assert stored[0].recipient == "+8613900000000"
    assert stored[0].conversation_id == again[0].conversation_id


def test_search_cursor_and_conversations(service):
    for index in range(3):
        service.ingest(
            "smsforwarder",
            [
                IncomingMessage(
                    sender=f"1008{index}",
                    body=f"message {index}",
                    received_at=datetime(2026, 9, 3, 1, index, tzinfo=UTC),
                    dedupe_key=f"event-{index}",
                )
            ],
        )
    first_page = service.search(MessageQuery(limit=2))
    assert len(first_page.messages) == 2
    assert first_page.next_cursor
    second_page = service.search(MessageQuery(limit=2, cursor=first_page.next_cursor))
    assert len(second_page.messages) == 1
    conversations = service.conversations(ConversationQuery())
    assert len(conversations.conversations) == 3


def test_provider_id_namespaces_dedupe_keys(service):
    incoming = IncomingMessage(sender="10086", body="same", dedupe_key="event-1")
    first, first_duplicates = service.ingest("smsforwarder", [incoming], provider_id="phone-a")
    second, second_duplicates = service.ingest("smsforwarder", [incoming], provider_id="phone-b")
    assert first_duplicates == 0
    assert second_duplicates == 0
    assert first[0].id != second[0].id
    assert first[0].metadata["provider_id"] == "phone-a"
    assert second[0].metadata["provider_id"] == "phone-b"
