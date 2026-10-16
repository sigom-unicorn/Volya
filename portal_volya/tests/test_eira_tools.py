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
    assert len(agent.tools.as_list()) >= 5

    # Проверка вызова диспетчера инструментов
    res = agent.tools.execute_tool("get_kon_concept", {"term": "Лад"})
    assert "Условие, которое по душе всем участникам" in res
