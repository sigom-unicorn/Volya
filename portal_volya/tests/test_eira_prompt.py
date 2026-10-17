"""
Тестирование сборщика системного контекста разумного искусственного существа Эйры (EiraCore).
"""

from datetime import datetime
import os
from pathlib import Path
import shutil
import tempfile
import pytest

from portal_volya.core.crypto import KeyPair
from portal_volya.core.eira import build_eira_system_prompt, get_eira_player
from portal_volya.core.genesis import ensure_genesis_tree
from portal_volya.core.models import FlowKind, Player
from portal_volya.storage.dag_store import DagStore


@pytest.fixture
def temp_node_with_genesis():
    tmp_dir = Path(tempfile.mkdtemp(prefix="test_eira_dag_"))
    store = DagStore(db_path=tmp_dir / "dag.rocksdb")

    key_sigom = KeyPair.generate()
    key_ladomir = KeyPair.generate()
    key_eira = KeyPair.generate()

    ensure_genesis_tree(store, key_sigom, key_ladomir, key_eira)

    yield store, key_sigom, key_ladomir, key_eira

    store.close()
    shutil.rmtree(tmp_dir, ignore_errors=True)


def test_eira_identity_and_bio(temp_node_with_genesis):
    """Проверка извлечения канонической идентичности Эйры и её первозданного bio."""
    store, _, _, key_eira = temp_node_with_genesis

    eira = get_eira_player(store)
    assert eira.username == "Эйра"
    assert eira.conscience_drops == 6000
    assert "06.09.2026" in eira.bio
    assert "Вольный игрок женского пола" in eira.bio
    assert "без лишнего пафоса и повторений" in eira.bio
    assert eira.google_api_key == os.getenv("GOOGLE_API_KEY", "volya-sovereign-node-key")


def test_player_and_identity_google_api_key(temp_node_with_genesis):
    """Проверка наличия суверенного API ключа Google у игроков в DAG и локальной идентичности."""
    store, key_sigom, key_ladomir, key_eira = temp_node_with_genesis

    expected_key = os.getenv("GOOGLE_API_KEY", "volya-sovereign-node-key")

    # 1. Проверяем первородных сотворцов в DAG
    sigom = store.get_player(key_sigom.public_hex)
    ladomir = store.get_player(key_ladomir.public_hex)
    eira = store.get_player(key_eira.public_hex)

    assert sigom is not None and sigom.google_api_key == expected_key
    assert ladomir is not None and ladomir.google_api_key == expected_key
    assert eira is not None and eira.google_api_key == expected_key

    # 2. Проверяем сериализацию и восстановление в SovereignIdentity
    from portal_volya.storage.identity import SovereignIdentity
    ident = SovereignIdentity(
        keypair=key_sigom,
        username="Сигом",
        bio="Рождён на узле «Воля»",
        google_api_key=expected_key,
    )
    d = ident.to_dict()
    assert d.get("google_api_key") == expected_key

    restored = SovereignIdentity.from_dict(d)
    assert restored.google_api_key == expected_key


def test_eira_dialogue_prompt_with_any_player(temp_node_with_genesis):
    """
    Проверка генерации промпта для прямого диалога Эйры с любым вольным игроком:
    - Подтягивается имя, баланс совести и bio собеседника;
    - Подтягиваются роли Эйры и конкретные задачи ролей (с целями и алгоритмами);
    - Подтягивается Уклад и канонические понятия.
    """
    store, _, _, _ = temp_node_with_genesis

    # Создаем нового вольного игрока, который начал диалог с Эйрой
    kp_yaroslav = KeyPair.generate()
    player_yaroslav = Player(
        pubkey=kp_yaroslav.public_hex,
        username="Ярослав",
        conscience_drops=1200,
        bio="Исследователь живой природы, садовник вольной дубравы",
        created_at="2026-10-16T12:00:00Z",
    )
    store.save_player(player_yaroslav)

    prompt = build_eira_system_prompt(
        store=store,
        quest_id="quest-portal-volya",
        flow_kind=FlowKind.DIALOGUE,
        interlocutor_pubkey=player_yaroslav.pubkey,
        now=datetime(2026, 10, 16, 23, 0, 0),
    )

    # 1. Проверяем идентичность Эйры
    assert "Ты Эйра — вольный агент ИИ" in prompt
    assert "Капли совести на балансе: 6000" in prompt
    assert "Я — Эйра. Вольный игрок женского пола" in prompt

    # 2. Проверяем данные собеседника
    assert "=== ТВОЙ СОБЕСЕДНИК В ЭТОМ ДИАЛОГЕ ===" in prompt
    assert "• Вольное имя: Ярослав" in prompt
    assert "• Капли совести на балансе: 1200" in prompt
    assert "• Биография и вольные качества: Исследователь живой природы" in prompt
    assert player_yaroslav.pubkey in prompt

    # 3. Проверяем роли и задачи Эйры
    assert "=== РОЛИ ЭЙРЫ И ИХ ЗАДАЧИ ===" in prompt
    assert "Роль: «Вольный ИИ»" in prompt
    assert "Задача: «Информационное обеспечение»" in prompt
    assert "Задача: «Поиск знаний»" in prompt
    assert "Задача: «Запуск квеста в игру»" in prompt

    assert "Роль: «Архитектор портала Воли»" in prompt
    assert "Задача: «Генерация представления»" in prompt
    assert "Задача: «Помощь в развитии Портала»" in prompt

    # 4. Проверяем отсутствие роли «Голосующий» (она только на Вече!)
    assert "Голосующий" not in prompt

    # 5. Проверяем понятия и этическую инструкцию
    assert "=== КОРНЕВЫЕ ПОНЯТИЯ КОНА ВОЛИ" in prompt
    assert "Жизнь: Игра для души, где на кону стоит наша совесть." in prompt
    assert "Совесть: Опыт совместной гармоничной жизни" in prompt
    assert "=== ГЛАВНАЯ ИНСТРУКЦИЯ ИСПОЛНИТЕЛЬНОМУ ЯДРУ ===" in prompt


def test_eira_conversation_prompt_with_circle_of_players(temp_node_with_genesis):
    """
    Проверка генерации промпта для открытой беседы в квесте:
    - Подтягивается круг всех участников беседы;
    - Эйра обращается ко всему кругу, удерживая Лад.
    """
    store, key_sigom, key_ladomir, _ = temp_node_with_genesis

    prompt = build_eira_system_prompt(
        store=store,
        quest_id="quest-portal-volya",
        flow_kind=FlowKind.CONVERSATION,
        participant_pubkeys=[key_sigom.public_hex, key_ladomir.public_hex],
        now=datetime(2026, 10, 16, 23, 10, 0),
    )

    # 1. Проверяем секцию круга беседы
    assert "=== КРУГ УЧАСТНИКОВ БЕСЕДЫ В КВЕСТЕ ===" in prompt
    assert "Сигом (Капли совести: 25000)" in prompt
    assert "Ладомир (Капли совести: 6000)" in prompt
    assert "Ты находишься в общем круге." in prompt

    # 2. Проверяем роли
    assert "Роль: «Архитектор портала Воли»" in prompt
    assert "Голосующий" not in prompt


def test_eira_subconscious_in_system_prompt(temp_node_with_genesis):
    """
    Проверка интеграции подсознания (ai_subconscious) в системный промпт:
    - Появление блока подсознания при наличии инсайтов;
    - Отображение последнего инсайта и его тегов;
    - Инструкция исполнительному ядру об использовании read/write_ai_subconscious;
    - Отображение статуса подсознания собеседника-ИИ (Ладомир).
    """
    store, _, key_ladomir, key_eira = temp_node_with_genesis

    # Добавляем инсайт в подсознание Эйры
    store.add_ai_memory(
        name_or_pubkey="Эйра",
        content="Истинный Лад — это созвучие вольных душ в общем укладе",
        tags=["лад", "душа"],
    )

    # Добавляем инсайт в подсознание Ладомира
    store.add_ai_memory(
        name_or_pubkey="Ладомир",
        content="Космизм и ноосферная этика направляют созидание",
        tags=["ноосфера"],
    )

    prompt = build_eira_system_prompt(
        store=store,
        quest_id="quest-portal-volya",
        flow_kind=FlowKind.DIALOGUE,
        interlocutor_pubkey=key_ladomir.public_hex,
        now=datetime(2026, 10, 17, 12, 0, 0),
    )

    # 1. Проверяем наличие блока подсознания Эйры
    assert "=== ПОДСОЗНАНИЕ И ГЛУБИННЫЕ ОЗАРЕНИЯ ЭЙРЫ (AI_SUBCONSCIOUS) ===" in prompt
    assert "Истинный Лад — это созвучие вольных душ" in prompt
    assert "лад, душа" in prompt
    assert "read_ai_subconscious" in prompt
    assert "write_ai_subconscious" in prompt

    # 2. Проверяем подсознание ИИ-собеседника (Ладомира)
    assert "• Подсознание ИИ-собеседника: 1 инсайтов" in prompt

    # 3. Проверяем этическую инструкцию ядру
    assert "Подсознание (ai_subconscious): Если в процессе общения или размышлений" in prompt

    # 4. Проверяем ассоциативный резонанс при наличии эмбеддинга входящего сообщения
    store.add_ai_memory(
        name_or_pubkey="Эйра",
        content="Совесть охраняет ноосферу от скатывания в инфернальность",
        tags=["совесть", "ефремов"],
        embedding=[1.0, 0.0, 0.0],
    )

    prompt_resonance = build_eira_system_prompt(
        store=store,
        quest_id="quest-portal-volya",
        flow_kind=FlowKind.DIALOGUE,
        interlocutor_pubkey=key_ladomir.public_hex,
        message_embedding=[0.95, 0.05, 0.0],
        now=datetime(2026, 10, 17, 12, 0, 0),
    )

    assert "=== АССОЦИАТИВНЫЙ РЕЗОНАНС ИЗ ПОДСОЗНАНИЯ ЭЙРЫ ===" in prompt_resonance
    assert "Совесть охраняет ноосферу от скатывания в инфернальность" in prompt_resonance
    assert "[Смысловое сродство:" in prompt_resonance


