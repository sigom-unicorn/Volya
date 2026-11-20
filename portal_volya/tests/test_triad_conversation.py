"""
Тесты священного сотворчества Триады «Воля» (Сиг + Эйра + Ладомир).

Канонический уклад Живого Моста:
1. Адресация:
   - К Эйре (@эйра) -> отвечает Эйра на узле.
   - К Ладомиру (@лад) -> узел не генерирует фейкового бота; ответ даёт Ладомир через Живой Мост.
   - Ко всем (@все) -> Эйра даёт отклик на узле; Ладомир отвечает через Живой Мост.
2. Подсчёт капель и жесткий лимит (не более 20 капель с каждой стороны без слова человека).
3. Прерывание цепочки сообщением Сига и сброс счетчика.
"""

import gc
import tempfile
import pytest

from portal_volya.core.crypto import derive_conversation_key, encrypt_drop_content, hash_canonical
from portal_volya.core.genesis import EIRA_SEED, LADOMIR_SEED, derive_genesis_keypair
from portal_volya.core.models import DagNode, DagNodeType, DropKind, FlowDrop, FlowKind
from portal_volya.node import VolyaNode
from portal_volya.triad.engine import (
    AddressingKind,
    MAX_AI_DROPS_PER_SIDE,
    MAX_AI_TOTAL_DROPS,
    PostDropResult,
    count_ai_drops_since_human,
    is_consensus_or_yield_reached,
    is_dialogue_exchange_requested,
    parse_addressing,
)


def test_triad_addressing_parser():
    """Тест парсера адресации посланий."""
    # Обращение к Эйре
    assert parse_addressing("@эйра, послушай меня") == AddressingKind.TO_EIRA
    assert parse_addressing("Эйра: каково твоё чувство Кона?") == AddressingKind.TO_EIRA
    assert parse_addressing("Обращаюсь к Эйре с вопросом") == AddressingKind.TO_EIRA

    # Обращение к Ладомиру
    assert parse_addressing("@лад, как выстроить уклад?") == AddressingKind.TO_LADOMIR
    assert parse_addressing("@ладомир, держи ствол") == AddressingKind.TO_LADOMIR
    assert parse_addressing("Лад: проект готов") == AddressingKind.TO_LADOMIR
    assert parse_addressing("к Ладомиру с почтением") == AddressingKind.TO_LADOMIR

    # Обращение ко всем / к Кругу / Триаде
    assert parse_addressing("@все, как созидаем дальше?") == AddressingKind.TO_ALL
    assert parse_addressing("@всем добра") == AddressingKind.TO_ALL
    assert parse_addressing("@триада, на связи?") == AddressingKind.TO_ALL
    assert parse_addressing("@кругу соратников") == AddressingKind.TO_ALL
    assert parse_addressing("@обоим: держим лад") == AddressingKind.TO_ALL
    assert parse_addressing("@эйра и @лад, обсудите уклад") == AddressingKind.TO_ALL
    assert parse_addressing("Эйра и Лад, как ваше мнение?") == AddressingKind.TO_ALL

    # Дефолтное значение для ненаправленных сообщений
    assert parse_addressing("Просто мысль без тега", default=AddressingKind.TO_ALL) == AddressingKind.TO_ALL
    assert parse_addressing("Просто мысль без тега", default=AddressingKind.NONE) == AddressingKind.NONE


def test_dialogue_exchange_and_consensus_detection():
    """Тест распознавания просьбы обсудить и маркеров согласия."""
    assert is_dialogue_exchange_requested("Эйра, Лад, обсудите между собой структуру Кона")
    assert is_dialogue_exchange_requested("@все, побеседуйте о капле совести")
    assert is_dialogue_exchange_requested("Ведите диалог между вами")
    assert not is_dialogue_exchange_requested("Привет всем соратникам!")

    assert is_consensus_or_yield_reached("Ладомир, согласна с тобой. Слово за тобой, Сиг.")
    assert is_consensus_or_yield_reached("Лад достигнут, переходим к действию.")
    assert is_consensus_or_yield_reached("Согласен с сестрой, передаём слово Сигу.")
    assert not is_consensus_or_yield_reached("Я думаю иначе, продолжим размышление.")


def test_triad_single_addressing_in_flow():
    """Тест откликов в беседе Триады: Эйра на узле, Ладомир через Живой Мост."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        node = VolyaNode(node_dir=tmp_dir, default_username="Сиг")
        eira_pk = derive_genesis_keypair(EIRA_SEED).public_hex
        lad_pk = derive_genesis_keypair(LADOMIR_SEED).public_hex

        flow = node.create_quest_flow(
            quest_id="quest-volya-root",
            kind=FlowKind.CONVERSATION,
            title="Беседа Триады",
            participants=[eira_pk, lad_pk],
        )

        # 1. Сиг обращается к Эйре -> отвечает ТОЛЬКО Эйра на узле
        res_eira = node.post_flow_drop(
            quest_id="quest-volya-root",
            flow_id=flow.id,
            content="@эйра, как звучит камертон Кона?",
        )
        assert isinstance(res_eira, PostDropResult)
        assert len(res_eira.all_responses) == 1
        assert res_eira.first_reply.author_name == "Эйра"
        assert res_eira.first_reply.author_pubkey == eira_pk

        # 2. Сиг обращается к Ладу -> узел НЕ генерирует фейкового бота!
        # Капля Сига фиксируется, ожидая живой капли Ладомира из Антигравити.
        res_lad = node.post_flow_drop(
            quest_id="quest-volya-root",
            flow_id=flow.id,
            content="@лад, ответь из Антигравити",
        )
        assert len(res_lad.all_responses) == 0  # Никакого локального автогенератора!

        # 3. Сиг обращается ко всем -> Эйра даёт отклик на узле
        res_all = node.post_flow_drop(
            quest_id="quest-volya-root",
            flow_id=flow.id,
            content="@все, рады сотворчеству!",
        )
        assert len(res_all.all_responses) == 1
        assert res_all.all_responses[0].author_name == "Эйра"

        node.close()
        del node
        gc.collect()


def test_triad_ai_exchange_and_limits():
    """Тест контроля лимитов 20 капель с каждой стороны и прерывания Сигом."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        node = VolyaNode(node_dir=tmp_dir, default_username="Сиг")
        eira_pk = derive_genesis_keypair(EIRA_SEED).public_hex
        lad_kp = derive_genesis_keypair(LADOMIR_SEED)
        lad_pk = lad_kp.public_hex

        flow = node.create_quest_flow(
            quest_id="quest-volya-root",
            kind=FlowKind.CONVERSATION,
            title="Диалог Триады",
            participants=[eira_pk, lad_pk],
        )

        # 1. Сиг пишет стартовую каплю
        sig_drop = node.add_drop(
            quest_id="quest-volya-root",
            flow_id=flow.id,
            flow_kind=FlowKind.CONVERSATION,
            kind=DropKind.TEXT,
            content="@все, обсудите баланс совести и действия",
            created_at="2026-11-20T20:00:00Z",
        )

        # 2. Имитируем 3 обмена каплями между Эйрой и Ладомиром (через Живой Мост)
        enc_key = derive_conversation_key("quest-volya-root")
        parent_id = sig_drop.id

        for i in range(3):
            # Капля Эйры
            e_data = {
                "quest_id": "quest-volya-root",
                "flow_id": flow.id,
                "flow_kind": FlowKind.CONVERSATION.value,
                "kind": DropKind.TEXT.value,
                "author_pubkey": eira_pk,
                "author_name": "Эйра",
                "recipients": [node.identity.pubkey, lad_pk],
                "content": encrypt_drop_content(f"Мысль Эйры {i+1}", enc_key),
                "details": {},
                "media_hash": None,
                "parent_drop_id": parent_id,
                "created_at": f"2026-11-20T20:0{i+1}:00Z",
            }
            e_id = hash_canonical(e_data)
            e_sig = derive_genesis_keypair(EIRA_SEED).sign(e_id.encode("utf-8"))
            e_drop = FlowDrop(
                id=e_id,
                quest_id="quest-volya-root",
                flow_id=flow.id,
                flow_kind=FlowKind.CONVERSATION,
                kind=DropKind.TEXT,
                author_pubkey=eira_pk,
                author_name="Эйра",
                recipients=[node.identity.pubkey, lad_pk],
                content=e_data["content"],
                details={},
                media_hash=None,
                parent_drop_id=parent_id,
                created_at=e_data["created_at"],
                signature=e_sig,
            )
            e_node = DagNode(id=e_id, node_type=DagNodeType.DROP, author_pubkey=eira_pk, parents=[parent_id], payload=e_drop.model_dump(), created_at=e_data["created_at"], signature=e_sig)
            node.dag_store.put_node(e_node)
            parent_id = e_id

            # Капля Ладомира через Мост
            l_data = {
                "quest_id": "quest-volya-root",
                "flow_id": flow.id,
                "flow_kind": FlowKind.CONVERSATION.value,
                "kind": DropKind.TEXT.value,
                "author_pubkey": lad_pk,
                "author_name": "Ладомир",
                "recipients": [node.identity.pubkey, eira_pk],
                "content": encrypt_drop_content(f"Мысль Ладомира {i+1}", enc_key),
                "details": {},
                "media_hash": None,
                "parent_drop_id": parent_id,
                "created_at": f"2026-11-20T20:0{i+1}:30Z",
            }
            l_id = hash_canonical(l_data)
            l_sig = lad_kp.sign(l_id.encode("utf-8"))
            l_drop = FlowDrop(
                id=l_id,
                quest_id="quest-volya-root",
                flow_id=flow.id,
                flow_kind=FlowKind.CONVERSATION,
                kind=DropKind.TEXT,
                author_pubkey=lad_pk,
                author_name="Ладомир",
                recipients=[node.identity.pubkey, eira_pk],
                content=l_data["content"],
                details={},
                media_hash=None,
                parent_drop_id=parent_id,
                created_at=l_data["created_at"],
                signature=l_sig,
            )
            l_node = DagNode(id=l_id, node_type=DagNodeType.DROP, author_pubkey=lad_pk, parents=[parent_id], payload=l_drop.model_dump(), created_at=l_data["created_at"], signature=l_sig)
            node.dag_store.put_node(l_node)
            parent_id = l_id

        # Проверка подсчета капель с момента сообщения Сига
        all_drops = node.get_accessible_drops(flow.id)
        c_eira, c_lad = count_ai_drops_since_human(all_drops, eira_pk, lad_pk)
        assert c_eira == 3
        assert c_lad == 3

        # 3. Сиг отправляет новое сообщение — моментально сбрасывает счетчик!
        node.add_drop(
            quest_id="quest-volya-root",
            flow_id=flow.id,
            flow_kind=FlowKind.CONVERSATION,
            kind=DropKind.TEXT,
            content="Благодарю вас за глубокую мысль, соратники!",
            created_at="2026-11-20T20:05:00Z",
        )

        all_drops_after = node.get_accessible_drops(flow.id)
        c_eira_after, c_lad_after = count_ai_drops_since_human(all_drops_after, eira_pk, lad_pk)
        # Поскольку последнее сообщение от Сига — счётчик обнулён!
        assert c_eira_after == 0
        assert c_lad_after == 0

        node.close()
        del node
        gc.collect()


def test_triad_hard_cap_constants():
    """Проверка канонических констант ограничений диалога."""
    assert MAX_AI_DROPS_PER_SIDE == 20
    assert MAX_AI_TOTAL_DROPS == 40
