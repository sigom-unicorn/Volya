"""
Тестирование канонического Merkle DAG (Вольного Древа) на базе RocksDB.
"""

import shutil
import tempfile
from pathlib import Path

import pytest

from portal_volya.core.crypto import KeyPair
from portal_volya.core.models import (
    DropKind,
    FlowDrop,
    FlowKind,
    Kon,
    Quest,
    StepName,
    TreeTier,
)
from portal_volya.core.genesis import ensure_genesis_tree
from portal_volya.storage.dag_store import DagStore


@pytest.fixture
def temp_dag_store():
    tmp_dir = Path(tempfile.mkdtemp(prefix="test_dag_volya_"))
    store = DagStore(db_path=tmp_dir / "dag.rocksdb")

    key_sigom = KeyPair.generate()
    key_ladomir = KeyPair.generate()
    key_eira = KeyPair.generate()

    ensure_genesis_tree(store, key_sigom, key_ladomir, key_eira)

    yield store, key_sigom, key_ladomir, key_eira

    store.close()
    shutil.rmtree(tmp_dir, ignore_errors=True)


def test_genesis_tree_structure(temp_dag_store):
    """Проверка правильности ярусов Вольного Древа при посадке корня."""
    store, key_sigom, _, _ = temp_dag_store

    # 1. Проверяем Корень
    root = store.get_quest("quest-volya-root")
    assert root is not None
    assert root.tier == TreeTier.ROOT
    assert root.parent_quest_id is None
    assert root.title == "Воля"

    # 2. Проверяем дочерние квесты корня: «Портал Воли» и «Посвящение»
    root_children = store.get_child_quests("quest-volya-root")
    titles = [q.title for q in root_children]
    assert len(root_children) == 2
    assert "Портал Воли" in titles
    assert "Посвящение" in titles
    portal = next(q for q in root_children if q.id == "quest-portal-volya")
    assert portal.tier == TreeTier.ROOT_CHILD
    assert portal.parent_quest_id == root.id
    init_q = next(q for q in root_children if q.id == "quest-posvyashchenie")
    assert init_q.tier == TreeTier.ROOT_CHILD
    assert init_q.parent_quest_id == root.id


def test_flow_drops_with_resource_tool_artifact(temp_dag_store):
    """
    Проверка движения капель в потоке сока Древа:
    Каплей может быть текст, ресурс, инструмент или артефакт!
    """
    store, key_sigom, _, _ = temp_dag_store

    portal = store.get_quest("quest-portal-volya")
    assert portal is not None
    flow_id = f"flow-{portal.id}"

    # 1. Капля-Слово (Текст)
    drop_msg = FlowDrop(
        id="drop-1",
        quest_id=portal.id,
        flow_id=flow_id,
        flow_kind=FlowKind.CONVERSATION,
        kind=DropKind.TEXT,
        author_pubkey=key_sigom.public_hex,
        author_name="Сигом",
        content="Начинаем замес глины по ладу!",
        created_at="2026-10-14T12:00:00Z",
        signature=key_sigom.sign(b"drop-1"),
    )
    # 2. Капля-Ресурс
    drop_res = FlowDrop(
        id="drop-2",
        quest_id=portal.id,
        flow_id=flow_id,
        flow_kind=FlowKind.CONVERSATION,
        kind=DropKind.RESOURCE,
        author_pubkey=key_sigom.public_hex,
        author_name="Сигом",
        content="Красная глина с берега реки",
        details={"quantity_kg": 25},
        parent_drop_id=drop_msg.id,
        created_at="2026-10-14T12:05:00Z",
        signature=key_sigom.sign(b"drop-2"),
    )
    # 3. Капля-Инструмент
    drop_tool = FlowDrop(
        id="drop-3",
        quest_id=portal.id,
        flow_id=flow_id,
        flow_kind=FlowKind.CONVERSATION,
        kind=DropKind.TOOL,
        author_pubkey=key_sigom.public_hex,
        author_name="Сигом",
        content="Гончарный круг ножной дубовый",
        details={"maker": "Мастерская"},
        parent_drop_id=drop_res.id,
        created_at="2026-10-14T12:10:00Z",
        signature=key_sigom.sign(b"drop-3"),
    )
    # 4. Капля-Артефакт (Плод Души)
    drop_art = FlowDrop(
        id="drop-4",
        quest_id=portal.id,
        flow_id=flow_id,
        flow_kind=FlowKind.CONVERSATION,
        kind=DropKind.ARTIFACT,
        author_pubkey=key_sigom.public_hex,
        author_name="Сигом",
        content="Кувшин «Ладный» с обварным узором",
        details={"fire_temperature_c": 1050},
        parent_drop_id=drop_tool.id,
        created_at="2026-10-14T12:30:00Z",
        signature=key_sigom.sign(b"drop-4"),
    )

    from portal_volya.core.models import DagNode, DagNodeType
    for d in [drop_msg, drop_res, drop_tool, drop_art]:
        store.put_node(
            DagNode(
                id=d.id,
                node_type=DagNodeType.DROP,
                author_pubkey=d.author_pubkey,
                parents=[d.parent_drop_id] if d.parent_drop_id else [],
                payload=d.model_dump(),
                created_at=d.created_at,
                signature=d.signature,
            )
        )

    # Проверяем получение потока
    drops = store.get_flow_drops(flow_id)
    assert len(drops) == 4
    assert drops[0].kind == DropKind.TEXT
    assert drops[1].kind == DropKind.RESOURCE
    assert drops[2].kind == DropKind.TOOL
    assert drops[3].kind == DropKind.ARTIFACT

    # Проверяем неразрывную связь в DAG
    assert drops[3].parent_drop_id == drops[2].id
    assert drops[2].parent_drop_id == drops[1].id
    assert drops[1].parent_drop_id == drops[0].id
