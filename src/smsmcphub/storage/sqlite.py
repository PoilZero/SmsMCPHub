from __future__ import annotations

import json
import sqlite3
import threading

from smsmcphub.config import ensure_database_parent
from smsmcphub.domain.models import (
    ConversationQuery,
    ConversationSummary,
    Message,
    MessageQuery,
    decode_cursor,
    encode_cursor,
    serialize_datetime,
    to_utc,
)


class SQLiteRepository:
    """Small synchronous SQLite repository suitable for the MVP workload."""

    def __init__(self, database_path: str) -> None:
        ensure_database_parent(database_path)
        self.database_path = database_path
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(database_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA journal_mode = WAL")
        self.initialize()

    def initialize(self) -> None:
        with self._lock, self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS messages (
                  id TEXT PRIMARY KEY,
                  channel TEXT NOT NULL DEFAULT 'sms',
                  source TEXT NOT NULL,
                  sender TEXT NOT NULL,
                  recipient TEXT,
                  body TEXT NOT NULL,
                  received_at TEXT NOT NULL,
                  forwarded_at TEXT,
                  conversation_id TEXT NOT NULL,
                  status TEXT NOT NULL DEFAULT 'unread',
                  dedupe_key TEXT NOT NULL UNIQUE,
                  metadata_json TEXT NOT NULL DEFAULT '{}',
                  raw_payload_json TEXT,
                  created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_messages_received_at
                  ON messages(received_at DESC, created_at DESC, id DESC);
                CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender);
                CREATE INDEX IF NOT EXISTS idx_messages_recipient ON messages(recipient);
                CREATE INDEX IF NOT EXISTS idx_messages_conversation
                  ON messages(conversation_id, received_at DESC, id DESC);
                """
            )

    def healthcheck(self) -> bool:
        with self._lock:
            self._connection.execute("SELECT 1").fetchone()
        return True

    def insert(self, message: Message) -> tuple[Message, bool]:
        raw_payload = (
            json.dumps(message.raw_payload, ensure_ascii=False, separators=(",", ":"))
            if message.raw_payload is not None
            else None
        )
        values = (
            message.id,
            message.channel,
            message.source,
            message.sender,
            message.recipient,
            message.body,
            serialize_datetime(message.received_at),
            serialize_datetime(message.forwarded_at) if message.forwarded_at else None,
            message.conversation_id,
            message.status.value,
            message.dedupe_key,
            json.dumps(message.metadata, ensure_ascii=False, separators=(",", ":")),
            raw_payload,
            serialize_datetime(message.created_at),
        )
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                INSERT OR IGNORE INTO messages (
                  id, channel, source, sender, recipient, body, received_at,
                  forwarded_at, conversation_id, status, dedupe_key,
                  metadata_json, raw_payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
            created = cursor.rowcount == 1
            row = self._connection.execute(
                "SELECT * FROM messages WHERE dedupe_key = ?", (message.dedupe_key,)
            ).fetchone()
        if row is None:
            raise RuntimeError("SQLite insert did not return a message")
        return self._row_to_message(row), created

    def get(self, message_id: str) -> Message | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM messages WHERE id = ?", (message_id,)
            ).fetchone()
        return self._row_to_message(row) if row else None

    def search(self, query: MessageQuery) -> tuple[list[Message], str | None]:
        offset = decode_cursor(query.cursor)
        clauses: list[str] = []
        params: list[object] = []
        if query.sender:
            clauses.append("sender = ?")
            params.append(query.sender)
        if query.recipient:
            clauses.append("recipient = ?")
            params.append(query.recipient)
        if query.keyword:
            clauses.append("body LIKE ? ESCAPE '\\'")
            params.append(f"%{_escape_like(query.keyword)}%")
        if query.since:
            clauses.append("received_at >= ?")
            params.append(serialize_datetime(to_utc(query.since)))
        if query.until:
            clauses.append("received_at <= ?")
            params.append(serialize_datetime(to_utc(query.until)))
        if query.status:
            clauses.append("status = ?")
            params.append(query.status.value)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"""
            SELECT * FROM messages
            {where}
            ORDER BY received_at DESC, created_at DESC, id DESC
            LIMIT ? OFFSET ?
        """
        params.extend((query.limit + 1, offset))
        with self._lock:
            rows = self._connection.execute(sql, params).fetchall()
        has_more = len(rows) > query.limit
        rows = rows[: query.limit]
        next_cursor = encode_cursor(offset + query.limit) if has_more else None
        return [self._row_to_message(row) for row in rows], next_cursor

    def conversations(
        self, query: ConversationQuery
    ) -> tuple[list[ConversationSummary], str | None]:
        offset = decode_cursor(query.cursor)
        sql = """
            SELECT
              m.conversation_id,
              MIN(m.sender) AS peer,
              MAX(m.received_at) AS last_message_at,
              COUNT(*) AS message_count,
              (
                SELECT m2.body
                FROM messages m2
                WHERE m2.conversation_id = m.conversation_id
                ORDER BY m2.received_at DESC, m2.created_at DESC, m2.id DESC
                LIMIT 1
              ) AS preview
            FROM messages m
            GROUP BY m.conversation_id
            ORDER BY last_message_at DESC, m.conversation_id DESC
            LIMIT ? OFFSET ?
        """
        with self._lock:
            rows = self._connection.execute(sql, (query.limit + 1, offset)).fetchall()
        has_more = len(rows) > query.limit
        rows = rows[: query.limit]
        next_cursor = encode_cursor(offset + query.limit) if has_more else None
        summaries = [
            ConversationSummary(
                conversation_id=row["conversation_id"],
                peer=row["peer"],
                last_message_at=_parse_db_datetime(row["last_message_at"]),
                message_count=row["message_count"],
                preview=row["preview"] or "",
            )
            for row in rows
        ]
        return summaries, next_cursor

    def purge_before(self, cutoff) -> int:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                "DELETE FROM messages WHERE received_at < ?", (serialize_datetime(cutoff),)
            )
        return cursor.rowcount

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    @staticmethod
    def _row_to_message(row: sqlite3.Row) -> Message:
        raw_payload = (
            json.loads(row["raw_payload_json"]) if row["raw_payload_json"] is not None else None
        )
        metadata = json.loads(row["metadata_json"] or "{}")
        return Message(
            id=row["id"],
            channel=row["channel"],
            source=row["source"],
            sender=row["sender"],
            recipient=row["recipient"],
            body=row["body"],
            received_at=_parse_db_datetime(row["received_at"]),
            forwarded_at=(_parse_db_datetime(row["forwarded_at"]) if row["forwarded_at"] else None),
            conversation_id=row["conversation_id"],
            status=row["status"],
            dedupe_key=row["dedupe_key"],
            metadata=metadata,
            raw_payload=raw_payload,
            created_at=_parse_db_datetime(row["created_at"]),
        )


def _parse_db_datetime(value: str):
    from datetime import datetime

    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
