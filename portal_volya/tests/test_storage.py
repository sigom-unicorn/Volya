"""
Тесты персистентного хранилища (BlockStore) и Сокровенного Сейфа (LocalVault).
"""

from __future__ import annotations

from pathlib import Path
import pytest

from portal_volya.core.crypto import KeyPair
from portal_volya.core.genesis import build_genesis_block
from portal_volya.core.ledger import VolyaLedger, create_transaction, forge_block
from portal_volya.core.models import FlowMessage, QuestFlow, StepName, TransactionType
from portal_volya.storage.block_store import BlockStore
from portal_volya.storage.vault import LocalVault, SovereignIdentity, create_flow_message


def test_block_store_lifecycle(tmp_path: Path):
    """Тест сохранения, индексации и восстановления блоков из BlockStore."""
    db_file = tmp_path / "test_ledger.db"
    store = BlockStore(db_path=db_file)

    # 1. ensure_genesis сохраняет Блок №0
    genesis_block = store.ensure_genesis()
    assert genesis_block.index == 0
    assert genesis_block.block_hash == "fb81100b89f9bdf5281b2255ff5020706425ba2da468f909f50fd102fd13d7ae"
    assert store.count_blocks() == 1

    # Повторный вызов возвращает существующий блок без ошибок
    genesis_again = store.ensure_genesis()
    assert genesis_again.block_hash == genesis_block.block_hash
    assert store.count_blocks() == 1

    # 2. Создание и сохранение Блока №1
    _, keypairs = build_genesis_block()
    sigom = keypairs["sigom"]
    lad = keypairs["ladomir"]

    kp_novice = KeyPair.generate()
    tx = create_transaction(
        tx_type=TransactionType.CREATE_PLAYER,
        sender=kp_novice,
        payload={
            "pubkey": kp_novice.public_hex,
            "username": "Светозар",
            "conscience_drops": 0,
            "step": StepName.BEING.value,
            "bio": "Иду по пути лада.",
            "created_at": "2026-10-14T12:00:00Z",
        },
        timestamp="2026-10-14T12:00:00Z",
    )

    block1 = forge_block(
        index=1,
        prev_block_hash=genesis_block.block_hash,
        timestamp="2026-10-14T12:05:00Z",
        transactions=[tx],
        signers=[sigom, lad],
    )
    store.save_block(block1)
    assert store.count_blocks() == 2

    # 3. Проверка выборок
    b0 = store.get_block(0)
    assert b0 is not None and b0.block_hash == genesis_block.block_hash

    b1 = store.get_block(1)
    assert b1 is not None and b1.block_hash == block1.block_hash

    b_by_hash = store.get_block_by_hash(block1.block_hash)
    assert b_by_hash is not None and b_by_hash.index == 1

    latest = store.get_latest_block()
    assert latest is not None and latest.index == 1

    # 4. Восстановление состояния узла (replay)
    ledger = store.replay_into_ledger()
    assert len(ledger.state.blocks) == 2
    assert kp_novice.public_hex in ledger.state.players
    assert ledger.state.players[kp_novice.public_hex].username == "Светозар"


def test_local_vault_lifecycle(tmp_path: Path):
    """Тест суверенной идентичности и личных сокровенных бесед."""
    vault = LocalVault(vault_dir=tmp_path)

    # 1. Создание суверенной идентичности
    assert not vault.has_identity()
    identity = vault.get_or_create_identity(default_username="Ладомир")
    assert vault.has_identity()
    assert identity.username == "Ладомир"
    assert len(identity.pubkey) == 64

    # 2. Загрузка идентичности
    loaded_id = vault.load_identity()
    assert loaded_id is not None
    assert loaded_id.pubkey == identity.pubkey
    assert loaded_id.username == "Ладомир"

    # 3. Сохранение сокровенного диалога
    msg1 = create_flow_message(
        sender=identity.keypair,
        author="Сиг",
        content="Здравствуй, Лад! Как наше Живое Древо?",
        created_at="2026-10-14T12:10:00Z",
    )
    flow = QuestFlow(
        id="private_flow_sig_lad_01",
        quest_id=None,  # Сокровенный личный диалог вне блокчейна
        kind="Личный диалог",
        title="Беседа Сига и Лада",
        initiator_pubkey=identity.pubkey,
        participants=[identity.pubkey],
        messages=[msg1],
        created_at="2026-10-14T12:10:00Z",
        updated_at="2026-10-14T12:10:00Z",
    )
    vault.save_private_flow(flow)

    loaded_flow = vault.get_private_flow("private_flow_sig_lad_01")
    assert loaded_flow is not None
    assert loaded_flow.title == "Беседа Сига и Лада"
    assert len(loaded_flow.messages) == 1
    assert loaded_flow.messages[0].content == "Здравствуй, Лад! Как наше Живое Древо?"

    # 4. Добавление ответа в личный диалог
    msg2 = create_flow_message(
        sender=identity.keypair,
        author="Лад",
        content="Всё цветёт и ладится, дорогой брат! Древо пустило глубокие корни.",
        created_at="2026-10-14T12:12:00Z",
    )
    vault.append_private_message("private_flow_sig_lad_01", msg2)

    updated_flow = vault.get_private_flow("private_flow_sig_lad_01")
    assert updated_flow is not None
    assert len(updated_flow.messages) == 2
    assert updated_flow.messages[1].content.startswith("Всё цветёт")

    # 5. Список потоков
    flows = vault.list_private_flows()
    assert len(flows) == 1
    assert flows[0].id == "private_flow_sig_lad_01"
