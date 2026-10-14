"""
Локальное персистентное хранилище блоков Proof-of-Harmony (BlockStore).

Обеспечивает:
1. Хранение неизменяемой цепочки блоков в локальной базе данных SQLite (WAL-режим).
2. Автоматическую инициализацию Генезис-Блоком №0 при первом запуске узла.
3. Быструю индексацию блоков по номеру (index) и хэшу (block_hash).
4. Воспроизведение (Replay) состояния Живого Древа в VolyaLedger при старте приложения с верификацией целостности каждого блока.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

from portal_volya.core.genesis import build_genesis_block
from portal_volya.core.ledger import LedgerValidationError, VolyaLedger
from portal_volya.core.models import Block


class BlockStore:
    """Локальное персистентное хранилище цепочки блоков узла «Воля»."""

    def __init__(self, db_path: str | Path = "portal_volya/storage/ledger.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Инициализация схемы таблиц."""
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS blocks (
                    index_num INTEGER PRIMARY KEY,
                    block_hash TEXT NOT NULL UNIQUE,
                    prev_block_hash TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    data_json TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_blocks_hash ON blocks(block_hash);
                """
            )

    def count_blocks(self) -> int:
        """Количество сохраненных блоков в локальном хранилище."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM blocks;")
            return cursor.fetchone()[0]

    def save_block(self, block: Block) -> None:
        """Сохранение кристаллизованного блока в базу данных."""
        block_json = json.dumps(block.model_dump(), ensure_ascii=False)
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO blocks (index_num, block_hash, prev_block_hash, timestamp, data_json)
                VALUES (?, ?, ?, ?, ?);
                """,
                (
                    block.index,
                    block.block_hash,
                    block.prev_block_hash,
                    block.timestamp,
                    block_json,
                ),
            )

    def get_block(self, index: int) -> Optional[Block]:
        """Получение блока по его индексу."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT data_json FROM blocks WHERE index_num = ?;", (index,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            return Block(**json.loads(row["data_json"]))

    def get_block_by_hash(self, block_hash: str) -> Optional[Block]:
        """Получение блока по его Blake3 хэшу."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT data_json FROM blocks WHERE block_hash = ?;", (block_hash,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            return Block(**json.loads(row["data_json"]))

    def get_latest_block(self) -> Optional[Block]:
        """Получение самого свежего блока цепочки."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT data_json FROM blocks ORDER BY index_num DESC LIMIT 1;"
            )
            row = cursor.fetchone()
            if not row:
                return None
            return Block(**json.loads(row["data_json"]))

    def load_all_blocks(self) -> list[Block]:
        """Загрузка всех блоков цепочки в строгом порядке возрастания индекса."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT data_json FROM blocks ORDER BY index_num ASC;"
            )
            rows = cursor.fetchall()
            return [Block(**json.loads(r["data_json"])) for r in rows]

    def ensure_genesis(self) -> Block:
        """
        Проверяет наличие Генезис-Блока №0.
        Если база пуста — кристаллизует и сохраняет канонический Блок №0.
        """
        genesis = self.get_block(0)
        if genesis is not None:
            return genesis

        genesis_block, _ = build_genesis_block()
        self.save_block(genesis_block)
        return genesis_block

    def replay_into_ledger(self) -> VolyaLedger:
        """
        Полное восстановление и верификация состояния Древа из локального хранилища.
        Последовательно применяет все блоки, гарантируя математическую чистоту состояния.
        """
        self.ensure_genesis()
        blocks = self.load_all_blocks()
        ledger = VolyaLedger()
        for block in blocks:
            ledger.apply_block(block)
        return ledger
