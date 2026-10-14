"""
Локальный сокровенный сейф игрока (Vault & Sovereign Identity).

Обеспечивает:
1. Хранение суверенной криптографической идентичности игрока (Ed25519 KeyPair).
2. Безопасное локальное сохранение личных потоков («Личный диалог», «Личная беседа»),
   которые НИКОГДА не передаются в публичный блокчейн и принадлежат только человеку.
3. Локальные черновики и заметки игрока.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

from portal_volya.core.crypto import KeyPair, hash_canonical
from portal_volya.core.models import FlowMessage, QuestFlow


def create_flow_message(
    sender: KeyPair,
    author: str,
    content: str,
    created_at: str,
    action: str | None = None,
) -> FlowMessage:
    """Создание и подписание канонического сообщения потока сотворчества."""
    msg_body = {
        "author": author,
        "author_pubkey": sender.public_hex,
        "content": content,
        "created_at": created_at,
        "action": action,
    }
    msg_id = hash_canonical(msg_body)
    signature = sender.sign_canonical(msg_body)
    return FlowMessage(
        id=msg_id,
        author=author,
        author_pubkey=sender.public_hex,
        content=content,
        created_at=created_at,
        signature=signature,
        action=action,
    )


class SovereignIdentity:
    """Суверенная идентичность вольного игрока на локальном устройстве."""

    def __init__(self, keypair: KeyPair, username: str, bio: str = "") -> None:
        self.keypair = keypair
        self.username = username
        self.bio = bio

    @property
    def pubkey(self) -> str:
        return self.keypair.public_hex

    def to_dict(self) -> dict:
        return {
            "private_key_hex": self.keypair.private_hex,
            "public_key_hex": self.keypair.public_hex,
            "username": self.username,
            "bio": self.bio,
        }

    @classmethod
    def from_dict(cls, data: dict) -> SovereignIdentity:
        keypair = KeyPair.from_private_hex(data["private_key_hex"])
        return cls(keypair=keypair, username=data["username"], bio=data.get("bio", ""))


class LocalVault:
    """Локальный сейф для сокровенных данных и личных бесед игрока."""

    def __init__(
        self,
        vault_dir: str | Path = "portal_volya/storage",
        identity_file: str = "identity.json",
        db_file: str = "vault.db",
    ) -> None:
        self.vault_dir = Path(vault_dir)
        self.vault_dir.mkdir(parents=True, exist_ok=True)
        self.identity_path = self.vault_dir / identity_file
        self.db_path = self.vault_dir / db_file
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS private_flows (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    initiator_pubkey TEXT NOT NULL,
                    data_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    # -----------------------------------------------------------------
    # Управление суверенной идентичностью
    # -----------------------------------------------------------------

    def has_identity(self) -> bool:
        """Проверка наличия сохраненной идентичности на этом устройстве."""
        return self.identity_path.exists()

    def save_identity(self, identity: SovereignIdentity) -> None:
        """Сохранение суверенной идентичности."""
        with open(self.identity_path, "w", encoding="utf-8") as f:
            json.dump(identity.to_dict(), f, ensure_ascii=False, indent=2)

    def load_identity(self) -> Optional[SovereignIdentity]:
        """Загрузка суверенной идентичности."""
        if not self.has_identity():
            return None
        with open(self.identity_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return SovereignIdentity.from_dict(data)

    def get_or_create_identity(self, default_username: str = "Вольный Игрок") -> SovereignIdentity:
        """Получить существующую идентичность или сгенерировать новую."""
        existing = self.load_identity()
        if existing:
            return existing

        kp = KeyPair.generate()
        identity = SovereignIdentity(keypair=kp, username=default_username, bio="Рождён на узле «Воля»")
        self.save_identity(identity)
        return identity

    # -----------------------------------------------------------------
    # Сокровенные личные потоки (E2EE / Local-Only)
    # -----------------------------------------------------------------

    def save_private_flow(self, flow: QuestFlow) -> None:
        """Сохранение или обновление сокровенного потока."""
        data_json = json.dumps(flow.model_dump(), ensure_ascii=False)
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO private_flows (id, kind, title, initiator_pubkey, data_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title = excluded.title,
                    data_json = excluded.data_json,
                    updated_at = excluded.updated_at;
                """,
                (
                    flow.id,
                    flow.kind,
                    flow.title,
                    flow.initiator_pubkey,
                    data_json,
                    flow.updated_at,
                ),
            )

    def get_private_flow(self, flow_id: str) -> Optional[QuestFlow]:
        """Получение личного потока по ID."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT data_json FROM private_flows WHERE id = ?;", (flow_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            return QuestFlow(**json.loads(row["data_json"]))

    def append_private_message(self, flow_id: str, message: FlowMessage) -> None:
        """Добавление сообщения в личный поток."""
        flow = self.get_private_flow(flow_id)
        if not flow:
            raise ValueError(f"Личный поток {flow_id} не найден в сейфе!")

        flow.messages.append(message)
        flow.updated_at = message.created_at
        self.save_private_flow(flow)

    def list_private_flows(self) -> list[QuestFlow]:
        """Список всех личных потоков, отсортированных по времени обновления."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT data_json FROM private_flows ORDER BY updated_at DESC;"
            )
            rows = cursor.fetchall()
            return [QuestFlow(**json.loads(r["data_json"])) for r in rows]
