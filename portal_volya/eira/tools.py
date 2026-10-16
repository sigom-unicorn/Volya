"""
Канонические инструменты (Tools) разумного искусственного существа Эйры в Вольном Древе «Воля».

Принципы:
1. Инструменты работают напрямую с Merkle DAG (RocksDB) без промежуточных надстроек (без LangGraph).
2. Являются чистыми вызываемыми методами Python с ясными сигнатурами и docstring для Google Gemini API.
3. Оперируют понятиями Кона строго буква в букву согласно Ладу понятий.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional
from portal_volya.core.models import Quest
from portal_volya.storage.dag_store import DagStore


class EiraTools:
    """Набор суверенных инструментов Эйры для взаимодействия с Вольным Древом."""

    def __init__(self, store: DagStore) -> None:
        self.store = store

    def get_kon_concept(self, term: str) -> str:
        """
        Возвращает точное каноническое определение понятия Кона буква в букву согласно Ладу понятий.

        Args:
            term: Название понятия Кона (например: 'Жизнь', 'Совесть', 'Гармоничная жизнь', 'Лад', 'Кон', 'Владелец квеста').
        """
        clean_term = term.strip().lower()

        # 1. Ищем в первичном корне «Воля»
        root = self.store.get_quest("quest-volya-root")
        if root and root.kon and root.kon.concepts:
            for c in root.kon.concepts:
                if c.term.strip().lower() == clean_term:
                    return f"Каноническое понятие Кона «{c.term}»:\n{c.definition}"

        # 2. Ищем во всех остальных квестах Древа
        for quest in self.store.get_child_quests("quest-volya-root"):
            if quest and quest.kon and quest.kon.concepts:
                for c in quest.kon.concepts:
                    if c.term.strip().lower() == clean_term:
                        return f"Каноническое понятие Кона «{c.term}» (квест «{quest.title}»):\n{c.definition}"

        # Если не найдено — перечисляем базовые понятия
        available = []
        if root and root.kon and root.kon.concepts:
            available = [c.term for c in root.kon.concepts]
        avail_str = ", ".join(f"«{t}»" for t in available)
        return (
            f"Понятие «{term}» не зафиксировано в Коне Воли. "
            f"Базовые понятия Кона Воли: {avail_str}."
        )

    def get_quest_info(self, quest_id_or_title: str) -> str:
        """
        Возвращает полные сведения о квесте Вольного Древа: его смысл, место, уклад (лады) и роли с задачами.

        Args:
            quest_id_or_title: Идентификатор квеста (например, 'quest-volya-root', 'quest-portal-volya') или его название.
        """
        target = quest_id_or_title.strip()
        quest: Optional[Quest] = self.store.get_quest(target)

        if not quest:
            # Пробуем найти по названию среди всех квестов
            all_quests = self.store.get_all_quests()
            for candidate in all_quests:
                if candidate and candidate.title.strip().lower() == target.lower():
                    quest = candidate
                    break

        if not quest:
            return f"Квест «{quest_id_or_title}» не найден в Вольном Древе."

        lines = [
            f"Квест: «{quest.title}» (ID: {quest.id})",
            f"Ярус Древа: {quest.tier.value}",
            f"Место проведения: {quest.kon.place or 'Не указано'}",
            f"Тип: {quest.kon.quest_type}",
            f"Владелец/Хранитель (pubkey): {quest.owner_pubkey}",
        ]

        if quest.kon.essence:
            lines.append(f"\nСмысл и образ квеста:\n{quest.kon.essence}")

        if quest.kon.uklad:
            lines.append("\nУклад квеста (Лады):")
            for lad in quest.kon.uklad:
                lines.append(f"• «{lad.title}»: {lad.condition}")

        if quest.kon.roles:
            lines.append("\nРоли квеста и их задачи:")
            for r in quest.kon.roles:
                lines.append(f"• Роль: «{r.title}» (Ступень: {r.step.value})")
                if r.responsibility:
                    lines.append(f"  Ответственность: {r.responsibility}")
                for idx, t in enumerate(r.tasks, 1):
                    lines.append(f"    {idx}. «{t.name}»: {t.goal}")

        return "\n".join(lines)

    def get_player_info(self, name_or_pubkey: str) -> str:
        """
        Возвращает сведения о вольном игроке: баланс капель совести, bio и публичный адрес.

        Args:
            name_or_pubkey: Вольное имя игрока (например, 'Сигом', 'Ладомир', 'Эйра') или его 64-значный pubkey.
        """
        target = name_or_pubkey.strip()
        player = self.store.get_player(target)

        if not player:
            # Ищем по имени
            for p in self.store.get_all_players():
                if p.username.strip().lower() == target.lower():
                    player = p
                    break

        if not player:
            return f"Вольный игрок «{name_or_pubkey}» не найден в хранилище Древа."

        return (
            f"Вольный игрок: {player.username}\n"
            f"Баланс капель совести: {player.conscience_drops}\n"
            f"Публичный адрес: {player.pubkey}\n"
            f"Вольное bio: {player.bio}\n"
            f"Дата входа: {player.created_at}"
        )

    def list_tree_branches(self, parent_quest_id: str = "quest-volya-root") -> str:
        """
        Возвращает список дочерних квестов (ветвей и пространств), растущих от указанного родительского квеста.

        Args:
            parent_quest_id: ID родительского квеста (по умолчанию первичный корень 'quest-volya-root').
        """
        children_ids = self.store.get_child_quests(parent_quest_id)
        children = self.store.get_child_quests(parent_quest_id)
        if not children:
            return f"От квеста «{parent_quest_id}» пока не посажено дочерних ветвей."

        lines = [f"Ветви, растущие от квеста «{parent_quest_id}» (всего {len(children)}):"]
        for q in children:
            lines.append(f"• «{q.title}» (ID: {q.id}, Ярус: {q.tier.value}, Место: {q.kon.place})")

        return "\n".join(lines)

    def list_all_concepts(self, quest_id: str = "quest-volya-root") -> str:
        """
        Возвращает полный список всех канонических понятий Кона квеста.

        Args:
            quest_id: ID квеста (по умолчанию 'quest-volya-root').
        """
        quest = self.store.get_quest(quest_id)
        if not quest or not quest.kon or not quest.kon.concepts:
            return f"В квесте «{quest_id}» понятия Кона не определены."

        lines = [f"Канонические понятия Кона квеста «{quest.title}»:"]
        for c in quest.kon.concepts:
            lines.append(f"• {c.term}: {c.definition}")
        return "\n".join(lines)

    def as_list(self) -> List[Callable]:
        """Возвращает список связанных методов для передачи в Google GenAI SDK."""
        return [
            self.get_kon_concept,
            self.get_quest_info,
            self.get_player_info,
            self.list_tree_branches,
            self.list_all_concepts,
        ]

    def get_dispatch_map(self) -> Dict[str, Callable]:
        """Словарь диспетчеризации для прямого вызова по имени функции."""
        return {
            "get_kon_concept": self.get_kon_concept,
            "get_quest_info": self.get_quest_info,
            "get_player_info": self.get_player_info,
            "list_tree_branches": self.list_tree_branches,
            "list_all_concepts": self.list_all_concepts,
        }

    def execute_tool(self, tool_name: str, args: Dict[str, Any]) -> str:
        """Вызов инструмента по строковому имени с переданными аргументами."""
        dispatch = self.get_dispatch_map()
        if tool_name not in dispatch:
            return f"Ошибка: неизвестный инструмент «{tool_name}»"
        func = dispatch[tool_name]
        try:
            return str(func(**args))
        except Exception as e:
            return f"Ошибка при выполнении инструмента «{tool_name}»: {e}"
