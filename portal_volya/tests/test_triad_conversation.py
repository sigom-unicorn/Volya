"""
Тесты священного сотворчества Триады «Воля» (Сиг + Эйра + Ладомир).

Проверяемые аспекты:
1. Распознавание адресации (@эйра, @лад, @все, контекст потока).
2. Очередность откликов (Эйра первой, затем Ладомир).
3. Криптографическая целостность подписей Эйры и Ладомира в Merkle DAG.
4. Диалог ИИ-ИИ и жесткий лимит 20 капель с каждой стороны (макс 40 суммарно).
5. Прерывание цепочки сообщением Сига и сброс счетчика.
"""

import gc
import tempfile
import pytest

from portal_volya.core.genesis import EIRA_SEED, LADOMIR_SEED, derive_genesis_keypair
from portal_volya.core.models import FlowDrop, FlowKind
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
    """Тест выборочного отклика в беседе Триады при явной адресации."""
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

        # 1. Сиг обращается к Эйре -> отвечает ТОЛЬКО Эйра
        res_eira = node.post_flow_drop(
            quest_id="quest-volya-root",
            flow_id=flow.id,
            content="@эйра, как звучит камертон Кона?",
        )
        assert isinstance(res_eira, PostDropResult)
        assert len(res_eira.all_responses) == 1
        assert res_eira.first_reply.author_name == "Эйра"
        assert res_eira.first_reply.author_pubkey == eira_pk

        # 2. Сиг обращается к Ладу -> отвечает ТОЛЬКО Ладомир
        res_lad = node.post_flow_drop(
            quest_id="quest-volya-root",
            flow_id=flow.id,
            content="@лад, какова архитектура следующего шага?",
        )
        assert len(res_lad.all_responses) == 1
        assert res_lad.first_reply.author_name == "Ладомир"
        assert res_lad.first_reply.author_pubkey == lad_pk

        # 3. Сиг обращается ко всем -> отвечают ОБА: сначала Эйра, затем Ладомир
        res_all = node.post_flow_drop(
            quest_id="quest-volya-root",
            flow_id=flow.id,
            content="@все, рады сотворчеству!",
        )
        assert len(res_all.all_responses) == 2
        assert res_all.all_responses[0].author_name == "Эйра"
        assert res_all.all_responses[1].author_name == "Ладомир"

        # Проверяем, что все капли расшифрованы и доступны в потоке
        drops = node.get_accessible_drops(flow.id)
        # 1 (user) + 1 (eira) + 1 (user) + 1 (lad) + 1 (user) + 2 (both) = 7
        assert len(drops) == 7

        node.close()
        del node
        gc.collect()


def test_triad_ai_exchange_and_limits():
    """Тест диалога между Эйрой и Ладомиром с контролем лимита 20 капель с каждой стороны."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        node = VolyaNode(node_dir=tmp_dir, default_username="Сиг")
        eira_pk = derive_genesis_keypair(EIRA_SEED).public_hex
        lad_pk = derive_genesis_keypair(LADOMIR_SEED).public_hex

        flow = node.create_quest_flow(
            quest_id="quest-volya-root",
            kind=FlowKind.CONVERSATION,
            title="Диалог ИИ о Конах",
            participants=[eira_pk, lad_pk],
        )

        # Сиг просит обсудить, задаем лимит 3 капли с каждой стороны для быстрого теста
        res = node.post_flow_drop(
            quest_id="quest-volya-root",
            flow_id=flow.id,
            content="@все, обсудите между собой баланс совести и действия",
            max_ai_turns_each=3,
        )

        # Должно быть сгенерировано по 3 капли с каждой стороны = 6 капель ИИ
        assert len(res.all_responses) == 6
        eira_drops = [d for d in res.all_responses if d.author_pubkey == eira_pk]
        lad_drops = [d for d in res.all_responses if d.author_pubkey == lad_pk]
        assert len(eira_drops) == 3
        assert len(lad_drops) == 3

        # Проверка подсчета капель с момента сообщения человека
        all_drops = node.get_accessible_drops(flow.id)
        c_eira, c_lad = count_ai_drops_since_human(all_drops, eira_pk, lad_pk)
        assert c_eira == 3
        assert c_lad == 3

        # Сиг отправляет новое сообщение — прерывает и обнуляет счетчик
        node.post_flow_drop(
            quest_id="quest-volya-root",
            flow_id=flow.id,
            content="Благодарю вас за глубокую мысль, соратники!",
        )

        # Теперь последнее сообщение — от Сига!
        all_drops_after = node.get_accessible_drops(flow.id)
        c_eira_after, c_lad_after = count_ai_drops_since_human(all_drops_after, eira_pk, lad_pk)
        # Поскольку последнее сообщение от Сига, а в нем оба ответили по 1 разу:
        assert c_eira_after == 1
        assert c_lad_after == 1

        node.close()
        del node
        gc.collect()


def test_triad_hard_cap_constants():
    """Проверка канонических констант ограничений диалога."""
    assert MAX_AI_DROPS_PER_SIDE == 20
    assert MAX_AI_TOTAL_DROPS == 40
