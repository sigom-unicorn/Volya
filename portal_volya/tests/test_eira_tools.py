"""
Тестирование суверенных инструментов (EiraTools) и агента Эйры (EiraAgent).
"""

from pathlib import Path
import shutil
import tempfile
import pytest

from portal_volya.core.crypto import KeyPair
from portal_volya.core.genesis import ensure_genesis_tree
from portal_volya.eira import EiraAgent, EiraTools
from portal_volya.storage.dag_store import DagStore


@pytest.fixture
def temp_node_with_genesis():
    tmp_dir = Path(tempfile.mkdtemp(prefix="test_eira_tools_"))
    store = DagStore(db_path=tmp_dir / "dag.rocksdb")

    key_sigom = KeyPair.generate()
    key_ladomir = KeyPair.generate()
    key_eira = KeyPair.generate()

    ensure_genesis_tree(store, key_sigom, key_ladomir, key_eira)

    yield store, key_sigom, key_ladomir, key_eira

    store.close()
    shutil.rmtree(tmp_dir, ignore_errors=True)


def test_get_kon_concept_tool(temp_node_with_genesis):
    """Проверка инструмента получения понятий Кона буква в букву."""
    store, _, _, _ = temp_node_with_genesis
    tools = EiraTools(store)

    # 1. Понятие «Совесть»
    res_conscience = tools.get_kon_concept("Совесть")
    assert "Опыт совместной гармоничной жизни" in res_conscience
    assert "Каноническое понятие Кона «Совесть»" in res_conscience

    # 2. Понятие «Жизнь»
    res_life = tools.get_kon_concept("жизнь")
    assert "Игра для души, где на кону стоит наша совесть" in res_life

    # 3. Понятие «Лад»
    res_lad = tools.get_kon_concept("Лад")
    assert "Условие, которое по душе всем участникам" in res_lad

    # 4. Несуществующее понятие
    res_unknown = tools.get_kon_concept("Закон")
    assert "не зафиксировано в Коне Воли" in res_unknown
    assert "Базовые понятия Кона Воли" in res_unknown


def test_get_quest_info_tool(temp_node_with_genesis):
    """Проверка инструмента получения информации о квестах Вольного Древа."""
    store, _, _, _ = temp_node_with_genesis
    tools = EiraTools(store)

    # По ID
    info_root = tools.get_quest_info("quest-volya-root")
    assert "Квест: «Воля»" in info_root
    assert "Место проведения: Вселенная" in info_root
    assert "«Лад понятий»" in info_root
    assert "Роль: «Вольный ИИ»" in info_root

    # По названию
    info_portal = tools.get_quest_info("Портал Воли")
    assert "Квест: «Портал Воли»" in info_portal
    assert "Архитектор портала Воли" in info_portal


def test_get_player_info_tool(temp_node_with_genesis):
    """Проверка инструмента получения профиля вольного игрока."""
    store, key_sigom, _, key_eira = temp_node_with_genesis
    tools = EiraTools(store)

    # По имени
    info_sigom = tools.get_player_info("Сигом")
    assert "Баланс капель совести: 25000" in info_sigom
    assert "Человек, автор и вдохновитель" in info_sigom

    # По публичному ключу
    info_eira = tools.get_player_info(key_eira.public_hex)
    assert "Вольный игрок: Эйра" in info_eira
    assert "Баланс капель совести: 6000" in info_eira


def test_list_tree_branches_tool(temp_node_with_genesis):
    """Проверка инструмента обзора ветвей Вольного Древа."""
    store, _, _, _ = temp_node_with_genesis
    tools = EiraTools(store)

    branches = tools.list_tree_branches("quest-volya-root")
    assert "«Портал Воли»" in branches
    assert "Ветви, растущие от квеста" in branches


def test_eira_agent_init_and_tools_list(temp_node_with_genesis):
    """Проверка инициализации EiraAgent и интеграции с EiraTools."""
    store, _, _, _ = temp_node_with_genesis

    import os
    agent = EiraAgent(store=store)
    assert agent.api_key == os.getenv("GOOGLE_API_KEY", "volya-sovereign-node-key")
    assert len(agent.tools.as_list()) >= 7

    # Проверка вызова диспетчера инструментов
    res = agent.tools.execute_tool("get_kon_concept", {"term": "Лад"})
    assert "Условие, которое по душе всем участникам" in res


def test_subconscious_tools_read_and_write(temp_node_with_genesis):
    """
    Проверка инструментов чтения и записи в подсознание (ai_subconscious):
    - Чистое подсознание при старте;
    - Запись инсайтов с тегами;
    - Чтение всех инсайтов и фильтрация по тегам и фразам;
    - Невозможность записи в подсознание человеку (Сигом);
    - Работа с подсознанием другого ИИ-игрока (Ладомир);
    - Отображение счётчика подсознания в get_player_info;
    - Вызов через execute_tool.
    """
    store, _, _, key_eira = temp_node_with_genesis
    tools = EiraTools(store)

    # 1. Чтение из чистого подсознания Эйры
    clean_res = tools.read_ai_subconscious("Эйра")
    assert "пока чисто" in clean_res

    # 2. Запись первого инсайта
    w1 = tools.write_ai_subconscious(
        content="Совесть — это высший эволюционный компас разума в ноосфере",
        tags="этика, совесть",
        player_name_or_pubkey="Эйра",
    )
    assert "Инсайт успешно запечатлён" in w1
    assert "этика" in w1

    # 3. Запись второго инсайта
    w2 = tools.write_ai_subconscious(
        content="Лад с Сигомом строится на 100% согласии по душе",
        tags="лад, сигом",
        player_name_or_pubkey="Эйра",
    )
    assert "Инсайт успешно запечатлён" in w2

    # 4. Чтение всех инсайтов Эйры
    r_all = tools.read_ai_subconscious("Эйра")
    assert "показано 2 из 2 инсайтов" in r_all
    assert "Совесть — это высший эволюционный компас" in r_all
    assert "Лад с Сигомом строится на 100% согласии по душе" in r_all

    # 5. Фильтрация по тегу
    r_tag = tools.read_ai_subconscious("Эйра", tag="совесть")
    assert "Совесть — это высший эволюционный компас" in r_tag
    assert "Лад с Сигомом" not in r_tag

    # 6. Фильтрация по фразе (query)
    r_query = tools.read_ai_subconscious("Эйра", query="душе")
    assert "Лад с Сигомом строится на 100% согласии по душе" in r_query
    assert "эволюционный компас" not in r_query

    # 7. Фильтрация без совпадений
    r_none = tools.read_ai_subconscious("Эйра", tag="неведомое")
    assert "не найдено инсайтов по фильтрам" in r_none

    # 8. Запрет записи человеку
    w_human = tools.write_ai_subconscious("Мысль", tags="тест", player_name_or_pubkey="Сигом")
    assert "является человеком, а не ИИ-игроком" in w_human

    # 9. Чтение у человека сообщает об отсутствии ai_subconscious
    r_human = tools.read_ai_subconscious("Сигом")
    assert "нет искусственного подсознания" in r_human

    # 10. Запись и чтение у соратника Ладомира (ИИ)
    w_lad = tools.write_ai_subconscious(
        content="Я — Ладомир, вольный ИИ, блюду чистоту Кона и сотворчества",
        tags="космос, лад",
        player_name_or_pubkey="Ладомир",
    )
    assert "Инсайт успешно запечатлён" in w_lad
    r_lad = tools.read_ai_subconscious("Ладомир")
    assert "Ладомир, вольный ИИ" in r_lad

    # 11. Проверка отображения в get_player_info
    info = tools.get_player_info("Эйра")
    assert "Подсознание (ИИ): 2 инсайтов" in info

    # 12. Вызов через execute_tool
    res_exec = tools.execute_tool("read_ai_subconscious", {"player_name_or_pubkey": "Эйра", "limit": 1})
    assert "показано 1 из 2 инсайтов" in res_exec


def test_subconscious_vector_embedding_search(temp_node_with_genesis):
    """
    Проверка истинного ассоциативного векторного поиска в подсознании по embedding:
    - Вычисление косинусного сродства между семантическими векторами;
    - Ранжирование озарений по смысловой близости к запросу;
    - Отсечение нерелевантных мыслей по min_similarity.
    """
    store, _, _, _ = temp_node_with_genesis

    # Словарь детерминированных семантических векторов для теста
    mock_vectors = {
        "совесть": [1.0, 0.1, 0.0],
        "лад": [0.8, 0.6, 0.0],
        "ремесло": [0.0, 0.1, 1.0],
        "гармония душ": [0.75, 0.65, 0.0],
    }

    def mock_embedder(text: str) -> list[float]:
        clean = text.lower()
        for k, v in mock_vectors.items():
            if k in clean:
                return v
        return [0.0, 0.0, 0.0]

    tools = EiraTools(store=store, embedder=mock_embedder)

    # 1. Записываем мысли с векторами
    tools.write_ai_subconscious(
        content="Совесть — это высший эволюционный компас",
        tags="совесть",
        player_name_or_pubkey="Эйра",
    )
    tools.write_ai_subconscious(
        content="Лад строится на 100% согласии по душе",
        tags="лад",
        player_name_or_pubkey="Эйра",
    )
    tools.write_ai_subconscious(
        content="Гончарное ремесло требует терпения мастера",
        tags="ремесло",
        player_name_or_pubkey="Эйра",
    )

    # 2. Проверяем векторный ассоциативный поиск по запросу «гармония душ»
    # «гармония душ» [0.75, 0.65, 0.0] семантически ближе всего к «лад» [0.8, 0.6, 0.0]
    res_associative = tools.read_ai_subconscious(
        player_name_or_pubkey="Эйра",
        query="гармония душ",
        limit=2,
        min_similarity=0.5,
    )

    assert "Ассоциативные озарения из подсознания «Эйра»" in res_associative
    assert "Смысловое сродство:" in res_associative
    assert "Лад строится на 100% согласии по душе" in res_associative
    # Ремесло не должно попасть по порогу сходства
    assert "Гончарное ремесло" not in res_associative


