from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional


class BankDatabase:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self.connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS terminals (
                    terminal_id TEXT PRIMARY KEY,
                    signing_key TEXT NOT NULL,
                    merchant_name TEXT NOT NULL,
                    bank_name TEXT NOT NULL,
                    bank_name_hash TEXT NOT NULL,
                    masked_account_suffix TEXT NOT NULL,
                    account_number TEXT,
                    recipient_bank_code TEXT,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS used_sessions (
                    session_uuid TEXT PRIMARY KEY,
                    terminal_id TEXT NOT NULL,
                    used_at INTEGER NOT NULL,
                    FOREIGN KEY (terminal_id) REFERENCES terminals(terminal_id)
                );

                CREATE INDEX IF NOT EXISTS idx_used_sessions_terminal
                    ON used_sessions(terminal_id);
                """
            )

    def upsert_terminal(
        self,
        *,
        terminal_id: str,
        signing_key: str,
        merchant_name: str,
        bank_name: str,
        bank_name_hash: str,
        masked_account_suffix: str,
        account_number: Optional[str],
        recipient_bank_code: Optional[str],
    ) -> None:
        now = int(time.time() * 1000)
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO terminals (
                    terminal_id, signing_key, merchant_name, bank_name, bank_name_hash,
                    masked_account_suffix, account_number, recipient_bank_code,
                    active, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(terminal_id) DO UPDATE SET
                    signing_key = excluded.signing_key,
                    merchant_name = excluded.merchant_name,
                    bank_name = excluded.bank_name,
                    bank_name_hash = excluded.bank_name_hash,
                    masked_account_suffix = excluded.masked_account_suffix,
                    account_number = excluded.account_number,
                    recipient_bank_code = excluded.recipient_bank_code,
                    active = 1,
                    updated_at = excluded.updated_at
                """,
                (
                    terminal_id,
                    signing_key,
                    merchant_name,
                    bank_name,
                    bank_name_hash,
                    masked_account_suffix,
                    account_number,
                    recipient_bank_code,
                    now,
                    now,
                ),
            )

    def get_terminal(self, terminal_id: str) -> Optional[dict[str, Any]]:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM terminals WHERE terminal_id = ? AND active = 1",
                (terminal_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_terminals_public(self) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT terminal_id, merchant_name, bank_name, masked_account_suffix,
                       recipient_bank_code, created_at, updated_at
                FROM terminals WHERE active = 1 ORDER BY terminal_id
                """
            ).fetchall()
        return [dict(r) for r in rows]

    def consume_session(self, session_uuid: str, terminal_id: str) -> bool:
        """Return True if session was newly consumed, False if replay."""
        now = int(time.time() * 1000)
        with self.connection() as conn:
            existing = conn.execute(
                "SELECT 1 FROM used_sessions WHERE session_uuid = ?",
                (session_uuid,),
            ).fetchone()
            if existing:
                return False
            conn.execute(
                "INSERT INTO used_sessions (session_uuid, terminal_id, used_at) VALUES (?, ?, ?)",
                (session_uuid, terminal_id, now),
            )
        return True

    def purge_expired_sessions(self, max_age_ms: int = 600_000) -> int:
        cutoff = int(time.time() * 1000) - max_age_ms
        with self.connection() as conn:
            cur = conn.execute("DELETE FROM used_sessions WHERE used_at < ?", (cutoff,))
            return cur.rowcount

    def stats(self) -> dict[str, int]:
        with self.connection() as conn:
            terminals = conn.execute(
                "SELECT COUNT(*) AS c FROM terminals WHERE active = 1"
            ).fetchone()["c"]
            sessions = conn.execute("SELECT COUNT(*) AS c FROM used_sessions").fetchone()["c"]
        return {"terminals": terminals, "sessions": sessions}
