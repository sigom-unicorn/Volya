"""
Тестирование связки суверенного узла VolyaNode и разумного агента Эйры (EiraAgent).
"""

from datetime import datetime, timezone
from pathlib import Path
import shutil
import tempfile
from unittest.mock import MagicMock, patch
import pytest

from portal_volya.core.crypto import KeyPair
from portal_volya.core.genesis import EIRA_SEED, derive_genesis_keypair, ensure_genesis_tree
from portal_volya.core.models import DropKind, FlowKind, FlowSummary
from portal_volya.eira import EiraReply
from portal_volya.node import VolyaNode
from portal_volya.storage.identity import SovereignIdentity


@pytest.fixture
def temp_volya_node():
    tmp_dir = Path(tempfile.mkdtemp(prefix="test_node_eira_"))

    # Создаём тестовую личность игрока Сигома
    keypair = KeyPair.generate()
    identity = SovereignIdentity(
        keypair=keypair,
        username="Сигом Тестовый",
        bio="Человек, автор и созидатель",
        google_api_key="TEST_API_KEY",
    )

    node = VolyaNode(node_dir=tmp_dir, identity=identity)

    # Инициализируем корневой генезис
    k_sigom = keypair
    k_ladomir = KeyPair.generate()
    k_eira = derive_genesis_keypair(EIRA_SEED)
    ensure_genesis_tree(node.dag_store, k_sigom, k_ladomir, k_eira)

    yield node

    node.close()
    shutil.rmtree(tmp_dir, ignore_errors=True)


def test_ask_eira_integration(temp_volya_node):
    """
    Проверка полного цикла диалога с Эйрой через VolyaNode:
    - шифрование капли игрока (E2EE ECDH);
    - мыслительный ответ Эйры;
    - шифрование и подпись капли Эйры ключом Эйры;
    - расшифровка и доступность капель в get_accessible_drops.
    """
    node = temp_volya_node
    eira_kp = derive_genesis_keypair(EIRA_SEED)
    eira_pk = eira_kp.public_hex

    # Мокаем generate_reply, чтобы тест работал мгновенно и оффлайн
    mock_reply = EiraReply(
        text="Здравствуй, брат Сигом. Лад — это когда всем участникам по душе.",
        tools_called=["get_kon_concept"],
    )

    with patch.object(node.eira, "generate_reply", return_value=mock_reply) as mock_gen:
        user_drop, eira_drop = node.ask_eira(
            content="Эйра, расскажи о понятии Лад.",
            quest_id="quest-volya-root",
            flow_id="flow-dialogue-eira-test",
        )

        assert mock_gen.called
        call_kwargs = mock_gen.call_args.kwargs
        assert call_kwargs["message"] == "Эйра, расскажи о понятии Лад."
        assert call_kwargs["quest_id"] == "quest-volya-root"
        assert call_kwargs["flow_kind"] == FlowKind.DIALOGUE
        assert call_kwargs["interlocutor_pubkey"] == node.identity.pubkey

        # 1. Проверяем каплю игрока
        assert user_drop.author_pubkey == node.identity.pubkey
        assert user_drop.content == "Эйра, расскажи о понятии Лад."
        assert user_drop.recipients == [eira_pk]

        # 2. Проверяем каплю Эйры
        assert eira_drop.author_pubkey == eira_pk
        assert eira_drop.author_name == "Эйра"
        assert eira_drop.content == mock_reply.text
        assert eira_drop.recipients == [node.identity.pubkey]
        assert eira_drop.details == {"tools_called": ["get_kon_concept"]}
        assert eira_drop.parent_drop_id == user_drop.id

        # 3. Проверяем, что обе капли сохранены в Merkle DAG
        dag_user = node.dag_store.get_node(user_drop.id)
        assert dag_user is not None
        assert dag_user.author_pubkey == node.identity.pubkey
        # В самом узле DAG контент зашифрован ChaCha20Poly1305
        assert dag_user.payload["content"] != "Эйра, расскажи о понятии Лад."

        dag_eira = node.dag_store.get_node(eira_drop.id)
        assert dag_eira is not None
        assert dag_eira.author_pubkey == eira_pk
        # Контент ответа Эйры в DAG тоже зашифрован
        assert dag_eira.payload["content"] != mock_reply.text

        # 4. Проверяем дешифрование истории потока для игрока
        accessible_drops = node.get_accessible_drops("flow-dialogue-eira-test")
        assert len(accessible_drops) == 2
        assert accessible_drops[0].content == "Эйра, расскажи о понятии Лад."
        assert accessible_drops[1].content == mock_reply.text


def test_ask_eira_ephemeral(temp_volya_node):
    """Проверка быстрого эфемерного обращения к Эйре без фиксации в DAG."""
    node = temp_volya_node

    mock_reply = EiraReply(
        text="Эфемерный ответ для быстрого осмысления.",
        tools_called=[],
    )

    with patch.object(node.eira, "generate_reply", return_value=mock_reply) as mock_gen:
        reply = node.ask_eira_ephemeral("Сколько капель у меня на балансе?", quest_id="quest-volya-root")
        assert reply.text == "Эфемерный ответ для быстрого осмысления."
        assert mock_gen.called


def test_flow_summary_model_and_dag_store(temp_volya_node):
    """Проверка модели FlowSummary и методов сохранения/извлечения в RocksDB."""
    node = temp_volya_node
    from portal_volya.core.models import FlowSummary

    flow_id = "flow-test-summary-store"

    # Сначала саммари нет
    assert node.dag_store.get_latest_flow_summary(flow_id) is None
    assert node.dag_store.get_flow_summaries(flow_id) == []

    # Сохраняем первый кристалл памяти
    s1 = FlowSummary(
        summary="Начало пути. Обсудили понятие Лада.",
        last_drop_id="drop-hash-001",
        created_at="2026-10-17T18:00:00Z",
    )
    node.dag_store.put_flow_summary(flow_id, s1)

    latest = node.dag_store.get_latest_flow_summary(flow_id)
    assert latest is not None
    assert latest.summary == "Начало пути. Обсудили понятие Лада."
    assert latest.last_drop_id == "drop-hash-001"

    # Сохраняем второй кристалл
    s2 = FlowSummary(
        summary="Продолжение. Договорились о сборке окна на PySide6.",
        last_drop_id="drop-hash-020",
        created_at="2026-10-17T19:00:00Z",
    )
    node.dag_store.put_flow_summary(flow_id, s2)

    all_sums = node.dag_store.get_flow_summaries(flow_id)
    assert len(all_sums) == 2
    assert all_sums[0].last_drop_id == "drop-hash-001"
    assert all_sums[1].last_drop_id == "drop-hash-020"

    latest2 = node.dag_store.get_latest_flow_summary(flow_id)
    assert latest2.last_drop_id == "drop-hash-020"


def test_ask_eira_auto_summarization(temp_volya_node):
    """
    Проверка автоматического срабатывания сжатия памяти (FlowSummary),
    когда число не сжатых капель в потоке превышает порог (summary_threshold=15).
    """
    node = temp_volya_node
    flow_id = "flow-dialogue-eira-auto-sum"
    quest_id = "quest-volya-root"

    # Эмулируем накопление 16 капель в потоке
    for i in range(16):
        node.add_drop(
            quest_id=quest_id,
            flow_id=flow_id,
            flow_kind=FlowKind.DIALOGUE,
            kind=DropKind.TEXT,
            content=f"Мысль номер {i}",
            created_at=f"2026-10-17T18:{i:02d}:00Z",
        )

    mock_reply = EiraReply(
        text="Я всё помню и готова созидать дальше.",
        tools_called=[],
    )

    with patch.object(node.eira, "summarize_flow", return_value="Сжатый кристалл первых 16 капель") as mock_sum:
        with patch.object(node.eira, "generate_reply", return_value=mock_reply) as mock_gen:
            user_drop, eira_drop = node.ask_eira(
                content="Эйра, подведи итог.",
                quest_id=quest_id,
                flow_id=flow_id,
            )

            # Проверяем, что сжатие вызвалось
            assert mock_sum.called
            # Проверяем, что кристалл памяти записан в RocksDB
            latest = node.dag_store.get_latest_flow_summary(flow_id)
            assert latest is not None
            assert latest.summary == "Сжатый кристалл первых 16 капель"

            # Проверяем, что generate_reply получил саммари и скользящее окно
            assert mock_gen.called
            call_kwargs = mock_gen.call_args.kwargs
            assert call_kwargs["flow_summary"] == "Сжатый кристалл первых 16 капель"
            # История не должна превышать max_active_history (12 капель)
            history = call_kwargs["conversation_history"]
            assert len(history) <= 12

