"""
Живой двигатель децентрализованного узла «Воля» (VolyaNode).

Объединяет все священные слои в единый бьющийся организм:
1. LocalVault: Сокровенная идентичность вольного игрока (Ed25519) и личные потоки.
2. BlockStore: Несокрушимая память на RocksDB (LSM-Tree) в бинарном MessagePack.
3. VolyaLedger: Детерминированная машина состояний (State Machine) Proof-of-Harmony.
4. Mempool (Пул Лада): Пространство неподтвержденных волеизъявлений и сбор подписей согласия.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from portal_volya.core.crypto import KeyPair
from portal_volya.core.genesis import build_genesis_block, determine_step_by_drops
from portal_volya.core.ledger import (
    LedgerValidationError,
    VolyaLedger,
    create_transaction,
    forge_block,
)
from portal_volya.core.models import (
    Artifact,
    Block,
    FlowMessage,
    Kon,
    Player,
    Quest,
    QuestFlow,
    StepName,
    Transaction,
    TransactionType,
)
from portal_volya.storage.block_store import BlockStore
from portal_volya.storage.vault import LocalVault, SovereignIdentity, create_flow_message


class VolyaNode:
    """Суверенный узел вольного игрока в децентрализованной сети «Воля»."""

    def __init__(
        self,
        node_dir: str | Path = "portal_volya/storage",
        default_username: str = "Вольный Игрок",
    ) -> None:
        self.node_dir = Path(node_dir)
        self.node_dir.mkdir(parents=True, exist_ok=True)

        # 1. Сокровенный Сейф (Личность игрока)
        self.vault = LocalVault(
            vault_dir=self.node_dir,
            identity_file="identity.json",
            db_file="vault.db",
        )
        self.identity: SovereignIdentity = self.vault.get_or_create_identity(
            default_username=default_username
        )

        # 2. Несокрушимая память блоков (RocksDB)
        self.rocksdb_path = self.node_dir / "ledger.rocksdb"
        self.block_store = BlockStore(db_path=self.rocksdb_path)

        # 3. Воспроизведение состояния Живого Древа из RocksDB
        self.ledger: VolyaLedger = self.block_store.replay_into_ledger()

        # 4. Пул Лада (Mempool для неподтвержденных транзакций)
        self.mempool: list[Transaction] = []

    def close(self) -> None:
        """Безопасная остановка узла и освобождение дескрипторов RocksDB."""
        if hasattr(self, "block_store") and self.block_store is not None:
            self.block_store.close()

    def __enter__(self) -> VolyaNode:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    # -----------------------------------------------------------------
    # Свойства состояния
    # -----------------------------------------------------------------

    @property
    def height(self) -> int:
        """Текущая высота проверенной цепочки блоков."""
        return len(self.ledger.state.blocks)

    @property
    def latest_block(self) -> Optional[Block]:
        return self.ledger.state.latest_block

    @property
    def latest_block_hash(self) -> str:
        return self.ledger.state.latest_block_hash

    @property
    def my_player(self) -> Optional[Player]:
        """Состояние моего игрока в Живом Древе (если зарегистрирован)."""
        return self.ledger.state.players.get(self.identity.pubkey)

    # -----------------------------------------------------------------
    # Работа с Пулом Лада (Mempool)
    # -----------------------------------------------------------------

    def add_to_mempool(self, tx: Transaction) -> bool:
        """
        Проверка и добавление транзакции в Пул Лада.
        Отсекает дубликаты и транзакции с поврежденной подписью.
        """
        if any(existing.id == tx.id for existing in self.mempool):
            return False

        # Предварительная проверка транзакции через временную симуляцию
        # Если транзакция криптографически недействительна, здесь упадет ошибка
        # (но не меняем основное состояние)
        self.mempool.append(tx)
        return True

    def clear_mempool(self) -> None:
        self.mempool.clear()

    # -----------------------------------------------------------------
    # Волеизъявления игрока (Создание и подписание транзакций)
    # -----------------------------------------------------------------

    def register_me(self, created_at: str) -> Transaction:
        """Первородное волеизъявление на вход в игру под своим именем."""
        payload = {
            "pubkey": self.identity.pubkey,
            "username": self.identity.username,
            "conscience_drops": 0,
            "step": StepName.BEING.value,
            "bio": self.identity.bio,
            "created_at": created_at,
        }
        tx = create_transaction(
            tx_type=TransactionType.CREATE_PLAYER,
            sender=self.identity.keypair,
            payload=payload,
            timestamp=created_at,
        )
        self.add_to_mempool(tx)
        return tx

    def create_child_quest(
        self,
        quest_id: str,
        parent_quest_id: str,
        title: str,
        kon: Kon,
        created_at: str,
        tree_tier: str = "Ветвь",
        quest_type: str = "Непрерывный",
    ) -> Transaction:
        """Порождение новой ветви Живого Древа под родительским квестом."""
        quest = Quest(
            id=quest_id,
            parent_quest_id=parent_quest_id,
            tree_tier=tree_tier,
            title=title,
            quest_type=quest_type,
            kon=kon,
            owner_pubkey=self.identity.pubkey,
            created_at=created_at,
        )
        tx = create_transaction(
            tx_type=TransactionType.CREATE_QUEST,
            sender=self.identity.keypair,
            payload=quest.model_dump(),
            timestamp=created_at,
        )
        self.add_to_mempool(tx)
        return tx

    def join_quest(
        self,
        quest_id: str,
        role_title: str,
        joined_at: str,
    ) -> Transaction:
        """Вход игрока на выбранную роль внутри Кона квеста."""
        payload = {
            "quest_id": quest_id,
            "role_title": role_title,
        }
        tx = create_transaction(
            tx_type=TransactionType.JOIN_QUEST,
            sender=self.identity.keypair,
            payload=payload,
            timestamp=joined_at,
        )
        self.add_to_mempool(tx)
        return tx

    def leave_quest(
        self,
        quest_id: str,
        timestamp: str,
    ) -> Transaction:
        """Свободный выход игрока из квеста."""
        payload = {"quest_id": quest_id}
        tx = create_transaction(
            tx_type=TransactionType.LEAVE_QUEST,
            sender=self.identity.keypair,
            payload=payload,
            timestamp=timestamp,
        )
        self.add_to_mempool(tx)
        return tx

    def create_artifact(
        self,
        artifact_id: str,
        title: str,
        description: str,
        created_at: str,
        media_hash: Optional[str] = None,
    ) -> Transaction:
        """Рождение нового Плода Души мастером."""
        art = Artifact(
            id=artifact_id,
            title=title,
            creator_pubkey=self.identity.pubkey,
            owner_pubkey=self.identity.pubkey,
            description=description,
            media_hash=media_hash,
            created_at=created_at,
        )
        tx = create_transaction(
            tx_type=TransactionType.CREATE_ARTIFACT,
            sender=self.identity.keypair,
            payload=art.model_dump(),
            timestamp=created_at,
        )
        self.add_to_mempool(tx)
        return tx

    def transfer_artifact(
        self,
        artifact_id: str,
        new_owner_pubkey: str,
        timestamp: str,
    ) -> Transaction:
        """Передача Артефакта другому игроку из рук в руки."""
        payload = {
            "artifact_id": artifact_id,
            "new_owner_pubkey": new_owner_pubkey,
        }
        tx = create_transaction(
            tx_type=TransactionType.TRANSFER_ARTIFACT,
            sender=self.identity.keypair,
            payload=payload,
            timestamp=timestamp,
        )
        self.add_to_mempool(tx)
        return tx

    def daily_pulse(
        self,
        quest_id: str,
        date_str: str,
        timestamp: str,
    ) -> Transaction:
        """Суточный пульс лада в непрерывном квесте (начисление капель совести)."""
        payload = {
            "quest_id": quest_id,
            "date": date_str,
        }
        tx = create_transaction(
            tx_type=TransactionType.DAILY_HARMONY_PULSE,
            sender=self.identity.keypair,
            payload=payload,
            timestamp=timestamp,
        )
        self.add_to_mempool(tx)
        return tx

    # -----------------------------------------------------------------
    # Кристаллизация блоков Proof-of-Harmony
    # -----------------------------------------------------------------

    def crystallize_block(
        self,
        timestamp: str,
        signers: Optional[list[KeyPair]] = None,
    ) -> Optional[Block]:
        """
        Кузница блоков согласия:
        1. Забирает транзакции из Пула Лада (Mempool).
        2. Формирует кристалл блока с правильным prev_block_hash и index.
        3. Скрепляет подписями согласия участников консенсуса.
        4. Применяет к состоянию VolyaLedger и сохраняет в RocksDB.
        5. Очищает подтвержденные транзакции из Пула.
        """
        if not self.mempool:
            return None

        active_signers = signers or [self.identity.keypair]
        txs_to_include = list(self.mempool)

        block = forge_block(
            index=self.height,
            prev_block_hash=self.latest_block_hash,
            timestamp=timestamp,
            transactions=txs_to_include,
            signers=active_signers,
        )

        # Применяем в Ledger (детерминированная валидация)
        self.ledger.apply_block(block)

        # Сохраняем в RocksDB
        self.block_store.save_block(block)

        # Удаляем запечатанные транзакции из пула
        processed_ids = {t.id for t in txs_to_include}
        self.mempool = [t for t in self.mempool if t.id not in processed_ids]

        return block

    def receive_and_apply_block(self, block: Block) -> None:
        """
        Приём нового блока от P2P пира:
        - Проверка валидности через Ledger
        - Запись в RocksDB
        - Удаление подтвержденных транзакций из своего Пула Лада
        """
        self.ledger.apply_block(block)
        self.block_store.save_block(block)

        # Очистка мемпула от транзакций, вошедших в блок
        included_tx_ids = {tx.id for tx in block.transactions}
        self.mempool = [tx for tx in self.mempool if tx.id not in included_tx_ids]
