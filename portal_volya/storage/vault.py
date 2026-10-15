"""
Локальный сокровенный сейф игрока (Vault & Sovereign Identity) на базе RocksDB.

Обеспечивает:
1. Хранение суверенной криптографической идентичности игрока (Ed25519 KeyPair).
2. Безопасное локальное сохранение личных потоков («Личный диалог», «Личная беседа») в RocksDB,
   которые НИКОГДА не передаются во внешний мир и принадлежат только человеку.
3. Локальные черновики и заметки игрока.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

import ormsgpack
from rocksdict import Options, Rdict

from portal_volya.core.crypto import KeyPair, hash_canonical
from portal_volya.core.models import DropKind, FlowDrop, FlowKind, QuestFlow


def create_flow_drop(
    sender: KeyPair,
    author_name: str,
    content: str,
    created_at: str,
    flow_id: str = "",
    quest_id: str = "",
    flow_kind: FlowKind = FlowKind.DIALOGUE,
    kind: DropKind = DropKind.TEXT,
    details: Optional[Dict[str, Any]] = None,
    media_hash: Optional[str] = None,
    parent_drop_id: Optional[str] = None,
) -> FlowDrop:
    """Создание и подписание канонической капли сотворчества."""
    drop_body = {
        "quest_id": quest_id,
        "flow_id": flow_id,
        "flow_kind": flow_kind.value if hasattr(flow_kind, "value") else str(flow_kind),
        "kind": kind.value if hasattr(kind, "value") else str(kind),
        "author_pubkey": sender.public_hex,
        "author_name": author_name,
        "content": content,
        "details": details or {},
        "media_hash": media_hash,
        "parent_drop_id": parent_drop_id,
        "created_at": created_at,
    }
    drop_id = hash_canonical(drop_body)
    signature = sender.sign(drop_id.encode("utf-8"))
    return FlowDrop(
        id=drop_id,
        quest_id=quest_id,
        flow_id=flow_id,
        flow_kind=flow_kind,
        kind=kind,
        author_pubkey=sender.public_hex,
        author_name=author_name,
        content=content,
        details=details or {},
        media_hash=media_hash,
        parent_drop_id=parent_drop_id,
        created_at=created_at,
        signature=signature,
    )


create_flow_message = create_flow_drop  # Псевдоним для совместимости


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
    """Локальный сейф для сокровенных данных и личных бесед игрока (на базе RocksDB)."""

    def __init__(
        self,
        vault_dir: str | Path = "portal_volya/storage",
        identity_file: str = "identity.json",
        db_file: str = "vault.rocksdb",
    ) -> None:
        self.vault_dir = Path(vault_dir)
        self.vault_dir.mkdir(parents=True, exist_ok=True)
        self.identity_path = self.vault_dir / identity_file

        db_name = "vault.rocksdb" if db_file.endswith(".db") else db_file
        self.db_path = self.vault_dir / db_name

        opts = Options()
        opts.create_if_missing(True)
        self.db = Rdict(str(self.db_path), options=opts)

    def close(self) -> None:
        """Безопасное освобождение дескрипторов RocksDB."""
        if hasattr(self, "db") and self.db is not None:
            try:
                self.db.flush(wait=True)
                self.db.close()
            except Exception:
                pass

    def __enter__(self) -> LocalVault:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

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

    def get_or_create_identity(
        self,
        default_username: str = "Вольный Игрок",
        identity_file: Optional[str] = None,
    ) -> SovereignIdentity:
        """Получить существующую идентичность или сгенерировать новую."""
        if identity_file:
            self.identity_path = self.vault_dir / identity_file

        existing = self.load_identity()
        if existing:
            return existing

        kp = KeyPair.generate()
        identity = SovereignIdentity(keypair=kp, username=default_username, bio="Рождён на узле «Воля»")
        self.save_identity(identity)
        return identity

    # -----------------------------------------------------------------
    # Сокровенные личные потоки (E2EE / Local-Only в RocksDB)
    # -----------------------------------------------------------------

    def save_private_flow(self, flow: QuestFlow) -> None:
        """Сохранение или обновление сокровенного потока в RocksDB."""
        data_bytes = ormsgpack.packb(flow.model_dump())
        self.db[flow.id] = data_bytes
        self.db.flush(wait=False)

    def get_private_flow(self, flow_id: str) -> Optional[QuestFlow]:
        """Получение личного потока по ID."""
        data_bytes = self.db.get(flow_id)
        if data_bytes is None:
            return None
        return QuestFlow(**ormsgpack.unpackb(data_bytes))

    def append_private_drop(self, flow_id: str, drop: FlowDrop) -> None:
        """Добавление капли сотворчества в личный поток."""
        flow = self.get_private_flow(flow_id)
        if not flow:
            raise ValueError(f"Личный поток {flow_id} не найден в сейфе!")

        flow.drops.append(drop)
        flow.updated_at = drop.created_at
        self.save_private_flow(flow)

    def append_private_message(self, flow_id: str, drop: FlowDrop) -> None:
        """Псевдоним для append_private_drop."""
        self.append_private_drop(flow_id, drop)

    def list_private_flows(self) -> list[QuestFlow]:
        """Список всех личных потоков, отсортированных по времени обновления."""
        flows: list[QuestFlow] = []
        for _, val in self.db.items():
            try:
                flows.append(QuestFlow(**ormsgpack.unpackb(val)))
            except Exception:
                continue
        flows.sort(key=lambda f: f.updated_at, reverse=True)
        return flows
