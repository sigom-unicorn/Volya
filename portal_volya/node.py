"""
Живой двигатель суверенного децентрализованного узла «Воля» (VolyaNode).

Работает на базе Merkle DAG (Живого Древа) и сверхбыстрого RocksDB (LSM-Tree).
Никаких блоков, никакого майнинга, никаких очередей и мемпулов.
Каждая мысль, капля, квест, инструмент, ресурс или артефакт записывается атомарно за 1 мс.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

from portal_volya.core.crypto import KeyPair, hash_canonical
from portal_volya.core.genesis import (
    EIRA_SEED,
    LADOMIR_SEED,
    SIGOM_SEED,
    derive_genesis_keypair,
)
from portal_volya.core.models import (
    AIMemory,
    DagNode,
    DagNodeType,
    DropKind,
    FlowDrop,
    FlowKind,
    Kon,
    Lad,
    Player,
    Quest,
    Role,
    StepName,
    TreeTier,
)
from portal_volya.storage.dag_store import DagStore
from portal_volya.storage.vault import LocalVault, SovereignIdentity


class VolyaNode:
    """Суверенный узел вольного игрока в Живом Древе «Воля»."""

    def __init__(
        self,
        node_dir: str | Path = "portal_volya/storage",
        default_username: str = "Вольный Игрок",
    ) -> None:
        self.node_dir = Path(node_dir)
        self.node_dir.mkdir(parents=True, exist_ok=True)

        # 1. Сокровенный Сейф (Личность игрока Ed25519)
        self.vault = LocalVault(
            vault_dir=self.node_dir,
            identity_file="identity.json",
            db_file="vault.rocksdb",
        )
        self.identity: SovereignIdentity = self.vault.get_or_create_identity(
            default_username=default_username
        )

        # 2. Несокрушимая память Живого Древа на RocksDB (Merkle DAG)
        self.rocksdb_path = self.node_dir / "dag.rocksdb"
        self.dag_store = DagStore(db_path=self.rocksdb_path)

    def close(self) -> None:
        """Безопасная остановка узла и освобождение дескрипторов RocksDB."""
        if hasattr(self, "vault") and self.vault is not None:
            self.vault.close()
        if hasattr(self, "dag_store") and self.dag_store is not None:
            self.dag_store.close()

    def __enter__(self) -> VolyaNode:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    # -----------------------------------------------------------------
    # Свойства состояния
    # -----------------------------------------------------------------

    @property
    def my_player(self) -> Optional[Player]:
        """Текущее состояние игрока в Древе по публичному ключу."""
        return self.dag_store.get_player(self.identity.pubkey)

    # -----------------------------------------------------------------
    # Действия в Живом Древе (Атомарные узлы DAG)
    # -----------------------------------------------------------------

    def register_me(
        self,
        created_at: str,
        bio: str = "",
        ai_subconscious: Optional[list[AIMemory]] = None,
    ) -> Player:
        """Первородное волеизъявление на вход в игру под своим именем."""
        player = Player(
            pubkey=self.identity.pubkey,
            username=self.identity.username,
            conscience_drops=0,
            bio=bio or self.identity.bio,
            ai_subconscious=ai_subconscious,
            created_at=created_at,
        )
        node_id = hash_canonical(player.model_dump())
        sig = self.identity.keypair.sign(node_id.encode("utf-8"))

        dag_node = DagNode(
            id=node_id,
            node_type=DagNodeType.PLAYER,
            author_pubkey=self.identity.pubkey,
            parents=[],
            payload=player.model_dump(),
            created_at=created_at,
            signature=sig,
        )
        self.dag_store.put_node(dag_node)
        return player

    def create_quest(
        self,
        title: str,
        kon: Kon,
        parent_quest_id: Optional[str],
        tier: TreeTier,
        created_at: str,
        quest_id: Optional[str] = None,
    ) -> Quest:
        """Порождение новой ветви Древа (квеста)."""
        qid = quest_id or f"quest-{uuid.uuid4().hex[:12]}"
        quest = Quest(
            id=qid,
            parent_quest_id=parent_quest_id,
            tier=tier,
            title=title,
            kon=kon,
            owner_pubkey=self.identity.pubkey,
            created_at=created_at,
        )
        node_id = hash_canonical(quest.model_dump())
        sig = self.identity.keypair.sign(node_id.encode("utf-8"))

        parents = [parent_quest_id] if parent_quest_id else []
        dag_node = DagNode(
            id=node_id,
            node_type=DagNodeType.QUEST,
            author_pubkey=self.identity.pubkey,
            parents=parents,
            payload=quest.model_dump(),
            created_at=created_at,
            signature=sig,
        )
        self.dag_store.put_node(dag_node)
        return quest

    def add_drop(
        self,
        quest_id: str,
        flow_id: str,
        flow_kind: FlowKind,
        kind: DropKind,
        content: str,
        created_at: str,
        details: Optional[Dict[str, Any]] = None,
        media_hash: Optional[str] = None,
        parent_drop_id: Optional[str] = None,
    ) -> FlowDrop:
        """
        Вливание новой капли сока в Поток сотворчества:
        Слово, Аудио, Видео, Документ, Ресурс, Инструмент или Артефакт (Плод Души).
        """
        drop_data = {
            "quest_id": quest_id,
            "flow_id": flow_id,
            "flow_kind": flow_kind.value if hasattr(flow_kind, "value") else str(flow_kind),
            "kind": kind.value if hasattr(kind, "value") else str(kind),
            "author_pubkey": self.identity.pubkey,
            "author_name": self.identity.username,
            "content": content,
            "details": details or {},
            "media_hash": media_hash,
            "parent_drop_id": parent_drop_id,
            "created_at": created_at,
        }
        drop_id = hash_canonical(drop_data)
        sig = self.identity.keypair.sign(drop_id.encode("utf-8"))

        drop = FlowDrop(
            id=drop_id,
            quest_id=quest_id,
            flow_id=flow_id,
            flow_kind=flow_kind,
            kind=kind,
            author_pubkey=self.identity.pubkey,
            author_name=self.identity.username,
            content=content,
            details=details or {},
            media_hash=media_hash,
            parent_drop_id=parent_drop_id,
            created_at=created_at,
            signature=sig,
        )

        parents = [parent_drop_id] if parent_drop_id else [quest_id]
        dag_node = DagNode(
            id=drop_id,
            node_type=DagNodeType.DROP,
            author_pubkey=self.identity.pubkey,
            parents=parents,
            payload=drop.model_dump(),
            created_at=created_at,
            signature=sig,
        )
        self.dag_store.put_node(dag_node)
        return drop
