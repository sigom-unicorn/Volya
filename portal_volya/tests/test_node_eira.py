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
from portal_volya.core.models import FlowKind
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
