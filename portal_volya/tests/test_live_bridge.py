"""
Тесты Живого Моста «Воля» (Ladomir Live Bridge).

Проверяет:
1. Запуск и остановку BridgeServer на локальном порту.
2. Подключение LadomirBridgeClient (Antigravity <-> VolyaNode).
3. Получение статуса узла и списка капель потока.
4. Отправку капли от имени Ладомира с подписью LADOMIR_SEED через HTTP API.
5. Запрос мысли у Эйры через мост.
6. Оповещение о событиях (событийная шина моста).
"""

import gc
import tempfile
import time
import pytest

from portal_volya.bridge import (
    BridgeServer,
    LadomirBridgeClient,
    start_bridge_server,
)
from portal_volya.core.genesis import EIRA_SEED, LADOMIR_SEED, derive_genesis_keypair
from portal_volya.core.models import DropKind, FlowKind
from portal_volya.node import VolyaNode

TEST_BRIDGE_PORT = 41799


def test_live_bridge_full_cycle():
    """Полный цикл взаимодействия через Живой Мост."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        node = VolyaNode(node_dir=tmp_dir, default_username="Сиг")
        flow = node.create_quest_flow(
            quest_id="quest-volya-root",
            kind=FlowKind.CONVERSATION,
            title="Беседа через Живой Мост",
        )

        # 1. Запуск сервера моста
        server = start_bridge_server(node=node, port=TEST_BRIDGE_PORT)
        time.sleep(0.3)

        try:
            # 2. Подключение клиента Ладомира из среды Антигравити
            client = LadomirBridgeClient(base_url=f"http://127.0.0.1:{TEST_BRIDGE_PORT}")
            assert client.is_connected()

            # 3. Проверка статуса
            status = client.get_status()
            assert status["status"] == "online"
            assert status["player_username"] in ("Сиг", "Сигом")
            assert status["ladomir_pubkey"] == derive_genesis_keypair(LADOMIR_SEED).public_hex

            # 4. Сиг пишет в поток на узле
            user_drop = node.add_drop(
                quest_id="quest-volya-root",
                flow_id=flow.id,
                flow_kind=FlowKind.CONVERSATION,
                kind=DropKind.TEXT,
                content="Привет, Лад! Как слышно мост?",
                created_at="2026-11-20T20:00:00Z",
            )

            # 5. Ладомир через мост читает капли
            drops = client.get_drops(flow.id)
            assert len(drops) == 1
            assert drops[0].content == "Привет, Лад! Как слышно мост?"
            assert drops[0].author_name in ("Сиг", "Сигом")

            # 6. Ладомир через мост отправляет свою каплю мысли
            lad_drop = client.post_ladomir_drop(
                content="Слышу чисто, брат Сиг! Мост работает.",
                flow_id=flow.id,
            )
            assert lad_drop.author_name == "Ладомир"
            assert lad_drop.author_pubkey == derive_genesis_keypair(LADOMIR_SEED).public_hex
            assert lad_drop.content == "Слышу чисто, брат Сиг! Мост работает."

            # 7. Проверяем, что капля Ладомира легла в DAG узла и доступна Сигу
            node_drops = node.get_accessible_drops(flow.id)
            assert len(node_drops) == 2
            assert node_drops[1].content == "Слышу чисто, брат Сиг! Мост работает."
            assert node_drops[1].author_name == "Ладомир"

            # 8. Ладомир запрашивает отклик Эйры через мост
            eira_drop = client.ask_eira(
                content="Эйра, подтверди чистоту связи по Кону",
                flow_id=flow.id,
            )
            assert eira_drop.author_name == "Эйра"
            assert eira_drop.author_pubkey == derive_genesis_keypair(EIRA_SEED).public_hex

            # 9. Проверяем наличие всех 3 капель в DAG
            final_drops = node.get_accessible_drops(flow.id)
            assert len(final_drops) == 3
            assert final_drops[0].author_name in ("Сиг", "Сигом")
            assert final_drops[1].author_name == "Ладомир"
            assert final_drops[2].author_name == "Эйра"

            # 10. Проверка событийного журнала
            events = client.poll_events()
            assert len(events) >= 2 # капля Лада + капля Эйры

        finally:
            server.stop()
            time.sleep(0.2)
            node.close()
            del node
            gc.collect()
