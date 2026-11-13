"""
Тесты для Потоков квестов (QuestFlow), капель (FlowDrop) и участников.
"""

import gc
from pathlib import Path
import tempfile
import pytest

from portal_volya.core.crypto import KeyPair
from portal_volya.core.genesis import EIRA_SEED, derive_genesis_keypair
from portal_volya.core.models import FlowKind, DropKind, QuestFlow
from portal_volya.node import VolyaNode
from portal_volya.storage.dag_store import DagStore


def test_quest_flow_storage_and_defaults():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        db_path = Path(tmp_dir) / "dag.rocksdb"
        store = DagStore(db_path=db_path)
        store.ensure_genesis_tree()

        # 1. Запрос потоков для квеста «Воля» — автоматически создаётся каноническая беседа
        flows = store.get_quest_flows("quest-volya-root")
        assert len(flows) >= 1
        default_f = flows[0]
        assert default_f.quest_id == "quest-volya-root"
        assert default_f.kind == FlowKind.CONVERSATION

        # 2. Создание нового диалога
        new_flow = QuestFlow(
            id="flow-test-dialogue-1",
            quest_id="quest-volya-root",
            kind=FlowKind.DIALOGUE,
            title="Диалог с Эйрой о ладах",
            initiator_pubkey="initiator123",
            participants=["initiator123", "eira_pk"],
            created_at="2026-11-11T12:00:00Z",
            updated_at="2026-11-11T12:00:00Z",
        )
        store.put_quest_flow(new_flow)

        loaded = store.get_quest_flow("flow-test-dialogue-1")
        assert loaded is not None
        assert loaded.title == "Диалог с Эйрой о ладах"
        assert loaded.kind == FlowKind.DIALOGUE

        all_q_flows = store.get_quest_flows("quest-volya-root")
        assert len(all_q_flows) == 2

        # 3. Проверка get_quest_players — Эйра всегда первая!
        players = store.get_quest_players("quest-volya-root")
        assert len(players) >= 1
        assert players[0].username == "Эйра"

        store.close()
        del store
        gc.collect()


def test_node_flow_and_drop_operations():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        node = VolyaNode(node_dir=tmp_dir, default_username="Сиг")

        # 1. Список игроков квеста
        players = node.get_quest_players("quest-volya-root")
        assert len(players) >= 1
        assert players[0].username == "Эйра"
        eira_pk = players[0].pubkey

        # 2. Создание нового диалога с Эйрой
        flow = node.create_quest_flow(
            quest_id="quest-volya-root",
            kind=FlowKind.DIALOGUE,
            title="Диалог о совести",
            participants=[eira_pk],
        )
        assert flow.id.startswith("flow-")
        assert flow.title == "Диалог о совести"
        assert flow.kind == FlowKind.DIALOGUE

        # 3. Отправка капли в поток сотворчества
        user_drop, eira_drop = node.post_flow_drop(
            quest_id="quest-volya-root",
            flow_id=flow.id,
            content="Здравствуй, Эйра! Каковы лады нашего диалога?",
            kind=DropKind.TEXT,
        )
        assert user_drop is not None
        assert user_drop.content == "Здравствуй, Эйра! Каковы лады нашего диалога?"
        assert user_drop.author_pubkey == node.identity.pubkey
        assert eira_drop is not None
        assert eira_drop.author_name == "Эйра"

        # 4. Проверка извлечения доступных капель потока
        drops = node.get_accessible_drops(flow.id)
        assert len(drops) == 2
        assert drops[0].author_name == node.identity.username
        assert drops[1].author_name == "Эйра"

        node.close()
        del node
        gc.collect()
