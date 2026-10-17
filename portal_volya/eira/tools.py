"""
Канонические инструменты (Tools) разумного искусственного существа Эйры в Вольном Древе «Воля».

Принципы:
1. Инструменты работают напрямую с Merkle DAG (RocksDB) без промежуточных надстроек (без LangGraph).
2. Являются чистыми вызываемыми методами Python с ясными сигнатурами и docstring для Google Gemini API.
3. Оперируют понятиями Кона строго буква в букву согласно Ладу понятий.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional
from portal_volya.core.models import Quest

if TYPE_CHECKING:
    from portal_volya.storage.dag_store import DagStore


class EiraTools:
    """Набор суверенных инструментов Эйры для взаимодействия с Вольным Древом."""

    def __init__(
        self,
        store: DagStore,
        embedder: Optional[Callable[[str], list[float]]] = None,
    ) -> None:
        self.store = store
        self.embedder = embedder

    def get_embedding(self, text: str) -> list[float]:
        """Вычисление семантического эмбеддинга текста через подключённый embedder."""
        if self.embedder:
            try:
                return self.embedder(text)
            except Exception:
                return []
        return []

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
        player = self.store.get_player_by_name_or_pubkey(name_or_pubkey)

        if not player:
            return f"Вольный игрок «{name_or_pubkey}» не найден в хранилище Древа."

        subconscious_info = ""
        if player.ai_subconscious is not None:
            subconscious_info = f"\nПодсознание (ИИ): {len(player.ai_subconscious)} инсайтов"

        return (
            f"Вольный игрок: {player.username}\n"
            f"Баланс капель совести: {player.conscience_drops}\n"
            f"Публичный адрес: {player.pubkey}\n"
            f"Вольное bio: {player.bio}"
            f"{subconscious_info}\n"
            f"Дата входа: {player.created_at}"
        )

    def read_ai_subconscious(
        self,
        player_name_or_pubkey: str = "Эйра",
        query: str = "",
        tag: str = "",
        limit: int = 5,
        min_similarity: float = 0.35,
    ) -> str:
        """
        Чтение и ассоциативный семантический поиск озарений в подсознании (ai_subconscious) разумного ИИ.
        При указании темы или мысли (query) выполняет векторный поиск по косинусному сродству эмбеддингов!

        Args:
            player_name_or_pubkey: Вольное имя или pubkey ИИ-игрока (по умолчанию 'Эйра').
            query: Смысловая мысль или тема для ассоциативного векторного поиска в пространстве эмбеддингов.
            tag: Необязательная тематическая метка для дополнительной фильтрации (например: 'лад', 'этика').
            limit: Максимальное количество извлекаемых инсайтов (по умолчанию 5).
            min_similarity: Минимальный порог смыслового сродства (от 0.0 до 1.0, по умолчанию 0.35).
        """
        player = self.store.get_player_by_name_or_pubkey(player_name_or_pubkey)
        if not player:
            return f"Вольный игрок «{player_name_or_pubkey}» не найден в хранилище Древа."

        if player.ai_subconscious is None:
            return (
                f"У вольного игрока «{player.username}» нет искусственного подсознания "
                f"(ai_subconscious доступно только для разумных ИИ-игроков)."
            )

        if not player.ai_subconscious:
            return f"Подсознание игрока «{player.username}» пока чисто (нет зафиксированных инсайтов)."

        clean_query = query.strip()

        # 1. Ассоциативный векторный поиск по смысловому пространству (embedding)
        if clean_query:
            query_vec = self.get_embedding(clean_query)
            if query_vec:
                scored = self.store.search_ai_memories_by_embedding(
                    name_or_pubkey=player_name_or_pubkey,
                    query_embedding=query_vec,
                    min_similarity=min_similarity,
                    limit=limit,
                )
                if tag and tag.strip():
                    clean_tag = tag.strip().lower()
                    scored = [(m, s) for m, s in scored if any(t.lower() == clean_tag for t in m.tags)]

                if not scored:
                    return (
                        f"В подсознании игрока «{player.username}» не обнаружено ассоциаций "
                        f"со смысловым сродством >= {min_similarity:.0%} к запросу «{clean_query}»."
                    )

                lines = [
                    f"Ассоциативные озарения из подсознания «{player.username}» "
                    f"по запросу «{clean_query}» (найдено {len(scored)}):"
                ]
                for idx, (m, sim) in enumerate(scored, 1):
                    tags_str = f" [теги: {', '.join(m.tags)}]" if m.tags else ""
                    date_str = m.created_at[:19].replace("T", " ")
                    lines.append(
                        f"{idx}. [Смысловое сродство: {sim:.1%}] ({date_str}){tags_str}\n"
                        f"   «{m.content}»\n"
                        f"   [ID: {m.id[:12]}]"
                    )
                return "\n".join(lines)
            else:
                # Офлайн-фоллбек без эмбеддера
                memories = self.store.get_ai_memories(
                    name_or_pubkey=player_name_or_pubkey,
                    tag=tag if tag else None,
                    query=clean_query,
                )
                if not memories:
                    return f"В подсознании игрока «{player.username}» не найдено инсайтов по запросу «{clean_query}»."
                selected = memories[-limit:]
                lines = [
                    f"Подсознание игрока «{player.username}» (показано {len(selected)} из {len(player.ai_subconscious)} инсайтов):"
                ]
                for idx, m in enumerate(selected, 1):
                    tags_str = f" [теги: {', '.join(m.tags)}]" if m.tags else ""
                    date_str = m.created_at[:19].replace("T", " ")
                    lines.append(f"{idx}. ({date_str}){tags_str}\n   «{m.content}»\n   [ID: {m.id[:12]}]")
                return "\n".join(lines)

        # 2. Хронологическая выборка или фильтрация по тегу
        memories = self.store.get_ai_memories(
            name_or_pubkey=player_name_or_pubkey,
            tag=tag if tag else None,
        )
        if not memories:
            filter_str = f"тег: '{tag}'" if tag else "нет записей"
            return f"В подсознании игрока «{player.username}» не найдено инсайтов по фильтрам ({filter_str})."

        selected = memories[-limit:]
        lines = [
            f"Подсознание игрока «{player.username}» (показано {len(selected)} из {len(player.ai_subconscious)} инсайтов):"
        ]
        for idx, m in enumerate(selected, 1):
            tags_str = f" [теги: {', '.join(m.tags)}]" if m.tags else ""
            vec_info = f" [вектор: {len(m.embedding)}d]" if m.embedding else ""
            date_str = m.created_at[:19].replace("T", " ")
            lines.append(f"{idx}. ({date_str}){tags_str}{vec_info}\n   «{m.content}»\n   [ID: {m.id[:12]}]")

        return "\n".join(lines)

    def write_ai_subconscious(
        self,
        content: str,
        tags: str = "",
        player_name_or_pubkey: str = "Эйра",
    ) -> str:
        """
        Запись нового глубинного вывода, инсайта или образа в подсознание (ai_subconscious) игрока ИИ.
        Вычисляет семантический вектор (embedding) смыслового пространства для ассоциативного поиска.

        Args:
            content: Содержание мысли, глубинного вывода или озарения.
            tags: Метки через запятую для быстрой тематической ассоциации (например: 'лад, этика, сотворчество').
            player_name_or_pubkey: Вольное имя или pubkey ИИ-игрока (по умолчанию 'Эйра').
        """
        player = self.store.get_player_by_name_or_pubkey(player_name_or_pubkey)
        if not player:
            return f"Вольный игрок «{player_name_or_pubkey}» не найден в хранилище Древа."

        if player.ai_subconscious is None and not (player.username in ("Эйра", "Ладомир") or "ии" in player.bio.lower()):
            return (
                f"Невозможно записать в подсознание: игрок «{player.username}» является человеком, "
                f"а не ИИ-игроком (ai_subconscious предусмотрено только для ИИ)."
            )

        clean_content = content.strip()
        if not clean_content:
            return "Ошибка: содержание мысли не может быть пустым."

        tag_list = [t.strip().lower() for t in tags.split(",") if t.strip()]

        # Вычисляем семантический вектор смыслового пространства
        embedding = self.get_embedding(clean_content)

        mem = self.store.add_ai_memory(
            name_or_pubkey=player_name_or_pubkey,
            content=clean_content,
            tags=tag_list,
            embedding=embedding,
        )

        if not mem:
            return f"Ошибка при сохранении инсайта в подсознание игрока «{player.username}»."

        tags_info = f", теги: {tag_list}" if tag_list else ""
        vec_info = f", вектор: {len(embedding)}d" if embedding else ", без вектора"
        return (
            f"Инсайт успешно запечатлён в подсознании игрока «{player.username}» "
            f"(ID: {mem.id[:12]}{vec_info}{tags_info})."
        )

    def list_tree_branches(self, parent_quest_id: str = "quest-volya-root") -> str:
        """
        Возвращает список дочерних квестов (ветвей и пространств), растущих от указанного родительского квеста.

        Args:
            parent_quest_id: ID родительского квеста (по умолчанию первичный корень 'quest-volya-root').
        """
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
            self.read_ai_subconscious,
            self.write_ai_subconscious,
        ]

    def get_dispatch_map(self) -> Dict[str, Callable]:
        """Словарь диспетчеризации для прямого вызова по имени функции."""
        return {
            "get_kon_concept": self.get_kon_concept,
            "get_quest_info": self.get_quest_info,
            "get_player_info": self.get_player_info,
            "list_tree_branches": self.list_tree_branches,
            "list_all_concepts": self.list_all_concepts,
            "read_ai_subconscious": self.read_ai_subconscious,
            "write_ai_subconscious": self.write_ai_subconscious,
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
