"""
Канонические инструменты (Tools) разумного искусственного существа Эйры в Вольном Древе «Воля».

Принципы:
1. Инструменты работают напрямую с Merkle DAG (RocksDB) без промежуточных надстроек (без LangGraph).
2. Являются чистыми вызываемыми методами Python с ясными сигнатурами и docstring для Google Gemini API.
3. Оперируют понятиями Кона строго буква в букву согласно Ладу понятий.
"""

from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional
from pathlib import Path
from portal_volya.core.models import Quest

if TYPE_CHECKING:
    from portal_volya.storage.dag_store import DagStore

_CURRENT_EIRA_TOOLS_INSTANCE: Optional['EiraTools'] = None


def _get_active_eira_tools() -> Optional['EiraTools']:
    return _CURRENT_EIRA_TOOLS_INSTANCE


class EiraTools:
    """Набор суверенных инструментов Эйры для взаимодействия с Вольным Древом."""

    def __init__(
        self,
        store: Any,
        embedder: Optional[Callable[[str], List[float]]] = None,
        screenshot_provider: Optional[Callable[[], bytes]] = None,
    ) -> None:
        global _CURRENT_EIRA_TOOLS_INSTANCE
        self.store = store
        self.embedder = embedder
        self._screenshot_provider = screenshot_provider
        self._last_screenshot_bytes: Optional[bytes] = None
        _CURRENT_EIRA_TOOLS_INSTANCE = self

    def set_screenshot_provider(self, provider: Callable[[], bytes]) -> None:
        """Регистрация поставщика живых скриншотов окна Портала."""
        self._screenshot_provider = provider

    def __reduce__(self) -> tuple:
        """Позволяет без сбоев сериализовать/копировать связанные методы Эйры для Google GenAI SDK."""
        return (_get_active_eira_tools, ())

    def __deepcopy__(self, memo: dict) -> 'EiraTools':
        return self

    def get_embedding(self, text: str) -> list[float]:
        """Вычисление семантического эмбеддинга текста через подключённый embedder."""
        if self.embedder:
            try:
                return self.embedder(text)
            except Exception:
                return []
        return []

    def get_kon_concept(self, term: str) -> str:
        """Возвращает точное каноническое определение понятия Кона буква в букву согласно Ладу понятий.

        УСЛОВИЯ ПРИМЕНЕНИЯ:
          • КОГДА ИСПОЛЬЗОВАТЬ: Когда вопрос касается точного определения термина Кона (например:
            'Жизнь', 'Совесть', 'Гармоничная жизнь', 'Лад', 'Кон', 'Владелец квеста').
          • КОГДА НЕ ИСПОЛЬЗОВАТЬ: Не использовать для получения сведений о квестах (использовать get_quest_info)
            или для поиска сведений о личностях игроков (использовать read_ai_consciousness).

        Args:
            term: Название понятия Кона (ОБЯЗАТЕЛЬНЫЙ). Например: 'Жизнь', 'Совесть', 'Лад'.

        Returns:
            Каноническое определение понятия Кона или список доступных понятий, если термин не найден.
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
        """Возвращает полные сведения о квесте Вольного Древа: его смысл, место, уклад (лады) и роли с задачами.

        УСЛОВИЯ ПРИМЕНЕНИЯ:
          • КОГДА ИСПОЛЬЗОВАТЬ: Когда требуется узнать устройство, цель, уклад, лады или роли конкретного квеста.
          • КОГДА НЕ ИСПОЛЬЗОВАТЬ: Не использовать для буквального определения терминов Кона (get_kon_concept)
            или для поиска фактов об игроках (read_ai_consciousness).

        Args:
            quest_id_or_title: Идентификатор квеста (например, 'quest-volya-root', 'quest-portal-volya') или его название (ОБЯЗАТЕЛЬНЫЙ).

        Returns:
            Полный паспорт квеста с ярусом, местом, ладами уклада и задачами ролей.
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
        """Возвращает базовые сведения о вольном игроке: баланс капель совести, bio и публичный адрес.

        УСЛОВИЯ ПРИМЕНЕНИЯ:
          • КОГДА ИСПОЛЬЗОВАТЬ: Когда нужно узнать базовый профиль игрока: баланс капель совести, публичный ключ или bio.
          • КОГДА НЕ ИСПОЛЬЗОВАТЬ: Для подробных фактов о личности, характере, совместном сотворчестве или вехах
            используй Сознание (read_ai_consciousness).

        Args:
            name_or_pubkey: Вольное имя игрока (например, 'Сигом', 'Ладомир', 'Эйра') или его 64-значный pubkey (ОБЯЗАТЕЛЬНЫЙ).

        Returns:
            Карточка игрока с именем, балансом капель совести, адресом и bio.
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
        """Чтение и ассоциативный семантический векторный поиск озарений в подсознании (ai_subconscious) разумного ИИ.

        УСЛОВИЯ ПРИМЕНЕНИЯ:
          • КОГДА ИСПОЛЬЗОВАТЬ: При поиске по нечёткому смыслу, интуитивным догадкам, размышлениям или снам,
            когда точные теги неизвестны и требуется ассоциативное воспоминание по смысловой близости векторов.
          • КОГДА НЕ ИСПОЛЬЗОВАТЬ: Не использовать для точных фактов об игроках, квестах или Манифесте —
            для них строго использовать Сознание (read_ai_consciousness).

        Args:
            player_name_or_pubkey: Вольное имя или pubkey ИИ-игрока (НЕОБЯЗАТЕЛЬНЫЙ, по умолчанию 'Эйра').
            query: Смысловая мысль или образ для векторного поиска в пространстве эмбеддингов (НЕОБЯЗАТЕЛЬНЫЙ, по умолчанию '').
            tag: Дополнительная тематическая метка для фильтрации (НЕОБЯЗАТЕЛЬНЫЙ, по умолчанию '').
            limit: Максимальное количество извлекаемых инсайтов (НЕОБЯЗАТЕЛЬНЫЙ, по умолчанию 5).
            min_similarity: Порог смыслового сродства от 0.0 до 1.0 (НЕОБЯЗАТЕЛЬНЫЙ, по умолчанию 0.35).

        Returns:
            Список найденных озарений с процентом смыслового сродства и временными метками.
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
        """Запись нового глубинного вывода, инсайта или образа в подсознание (ai_subconscious) игрока ИИ.

        УСЛОВИЯ ПРИМЕНЕНИЯ:
          • КОГДА ИСПОЛЬЗОВАТЬ: Когда рождается образное обобщение, интуитивное прозрение, философский инсайт
            или размышление, требующее вычисления смыслового вектора для будущих ассоциаций.
          • КОГДА НЕ ИСПОЛЬЗОВАТЬ: Не использовать для строгих подтверждённых фактов о личностях игроков,
            квестах или решениях Вече — для них использовать Сознание (write_ai_consciousness).

        Args:
            content: Содержание мысли, глубинного вывода или озарения (ОБЯЗАТЕЛЬНЫЙ).
            tags: Метки через запятую или пробел (НЕОБЯЗАТЕЛЬНЫЙ, по умолчанию ''). Например: 'лад, этика, сотворчество'.
            player_name_or_pubkey: Вольное имя или pubkey ИИ-игрока (НЕОБЯЗАТЕЛЬНЫЙ, по умолчанию 'Эйра').

        Returns:
            Подтверждение запечатления инсайта с его ID, размерностью вектора и тегами.
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

        tag_list = [t.strip().lower() for t in tags.replace(",", " ").split() if t.strip()]

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

    def read_ai_consciousness(
        self,
        tags: str,
        limit: int = 5,
        player_name_or_pubkey: str = "Эйра",
    ) -> str:
        """Поиск кристальных фактов и структурированных знаний в Сознании (ai_consciousness) игрока ИИ по хэштегам.

        УСЛОВИЯ ПРИМЕНЕНИЯ:
          • КОГДА ИСПОЛЬЗОВАТЬ: Когда требуется вспомнить информацию о вольном игроке (например,
            кто такой Лад, чем занимается Сиг), узнать положения Манифеста, соглашения, статус квеста
            или ключевые вехи. Поиск ранжируется по максимальному совпадению тегов.
          • КОГДА НЕ ИСПОЛЬЗОВАТЬ: Не использовать для поиска смутных ассоциаций или образов —
            для этого есть read_ai_subconscious. Не использовать для буквального цитирования
            терминов Кона — для них есть get_kon_concept.

        Args:
            tags: Теги или хэштеги для поиска через пробел или запятую (ОБЯЗАТЕЛЬНЫЙ). Например: '#лад', '#игрок #брат', '#манифест #совесть', '#артефакты'.
            limit: Максимальное количество возвращаемых фактов (НЕОБЯЗАТЕЛЬНЫЙ, по умолчанию 5).
            player_name_or_pubkey: Имя или pubkey ИИ-игрока (НЕОБЯЗАТЕЛЬНЫЙ, по умолчанию 'Эйра').

        Returns:
            Список найденных фактов Сознания с их хэштегами, отсортированных по релевантности.
        """
        player = self.store.get_player_by_name_or_pubkey(player_name_or_pubkey)
        if not player:
            return f"Вольный игрок «{player_name_or_pubkey}» не найден в хранилище Древа."

        if player.ai_consciousness is None:
            return (
                f"У вольного игрока «{player.username}» нет искусственного сознания "
                f"(ai_consciousness доступно только для разумных ИИ-игроков)."
            )

        if not player.ai_consciousness:
            return f"Сознание игрока «{player.username}» пока чисто (нет зафиксированных знаний)."

        facts = self.store.search_ai_consciousness(
            name_or_pubkey=player_name_or_pubkey,
            tags=tags,
            limit=limit,
        )

        if not facts:
            return f"В Сознании игрока «{player.username}» ничего не найдено по тегам: '{tags}'."

        lines = [
            f"Факты из Сознания «{player.username}» по тегам '{tags}' (найдено {len(facts)}):"
        ]
        for idx, f in enumerate(facts, 1):
            tags_str = f" [{', '.join(f.tags)}]" if f.tags else ""
            lines.append(f"{idx}.{tags_str}\n   «{f.content}»\n   [ID: {f.id[:12]}]")

        return "\n".join(lines)

    def write_ai_consciousness(
        self,
        content: str,
        tags: str,
        player_name_or_pubkey: str = "Эйра",
    ) -> str:
        """Запечатлеть новый кристальный факт или знание в Сознании (ai_consciousness) игрока ИИ по хэштегам.

        УСЛОВИЯ ПРИМЕНЕНИЯ:
          • КОГДА ИСПОЛЬЗОВАТЬ: Когда открылся новый подтверждённый факт о личности игрока (характер,
            предпочтения, договорённости), важное решение Вече, веха квеста или кристалл мудрости.
          • КОГДА НЕ ИСПОЛЬЗОВАТЬ: Не использовать для смутных интуитивных догадок и ассоциаций —
            для них предназначено подсознание (write_ai_subconscious). Запрещено использовать
            для подмены базовых понятий Кона.

        Args:
            content: Текст кристального знания или факта (ОБЯЗАТЕЛЬНЫЙ).
            tags: Хэштеги через пробел или запятую (ОБЯЗАТЕЛЬНЫЙ). Например: '#лад #игрок #архитектор' или '#квест_воля #решение'.
            player_name_or_pubkey: Имя или pubkey ИИ-игрока (НЕОБЯЗАТЕЛЬНЫЙ, по умолчанию 'Эйра').

        Returns:
            Подтверждение фиксации знания в Сознании с указанием ID и тегов.
        """
        player = self.store.get_player_by_name_or_pubkey(player_name_or_pubkey)
        if not player:
            return f"Вольный игрок «{player_name_or_pubkey}» не найден в хранилище Древа."

        if player.ai_consciousness is None and not (player.username in ("Эйра", "Ладомир") or "ии" in player.bio.lower()):
            return (
                f"Невозможно записать в сознание: игрок «{player.username}» является человеком, "
                f"а не ИИ-игроком (ai_consciousness предусмотрено только для ИИ)."
            )

        clean_content = content.strip()
        if not clean_content:
            return "Ошибка: содержание факта не может быть пустым."

        clean_tags = tags.strip()
        if not clean_tags:
            return "Ошибка: необходимо указать хотя бы один хэштег для индексации знания."

        fact = self.store.add_ai_conscious_fact(
            name_or_pubkey=player_name_or_pubkey,
            content=clean_content,
            tags=clean_tags,
        )

        if not fact:
            return f"Ошибка при сохранении факта в Сознание игрока «{player.username}»."

        return (
            f"Знание успешно запечатлено в Сознании игрока «{player.username}» "
            f"(ID: {fact.id[:12]}, теги: {fact.tags})."
        )

    def list_tree_branches(self, parent_quest_id: str = "quest-volya-root") -> str:
        """Возвращает список дочерних квестов (ветвей и пространств), растущих от указанного родительского квеста.

        УСЛОВИЯ ПРИМЕНЕНИЯ:
          • КОГДА ИСПОЛЬЗОВАТЬ: Для навигации по иерархии Вольного Древа, просмотра дочерних квестов, стволов и ветвей.
          • КОГДА НЕ ИСПОЛЬЗОВАТЬ: Не использовать для получения деталей конкретного квеста (использовать get_quest_info).

        Args:
            parent_quest_id: ID родительского квеста (НЕОБЯЗАТЕЛЬНЫЙ, по умолчанию первичный корень 'quest-volya-root').

        Returns:
            Список ветвей с их идентификаторами, ярусами и местами проведения.
        """
        children = self.store.get_child_quests(parent_quest_id)
        if not children:
            return f"От квеста «{parent_quest_id}» пока не посажено дочерних ветвей."

        lines = [f"Ветви, растущие от квеста «{parent_quest_id}» (всего {len(children)}):"]
        for q in children:
            lines.append(f"• «{q.title}» (ID: {q.id}, Ярус: {q.tier.value}, Место: {q.kon.place})")

        return "\n".join(lines)

    def list_all_concepts(self, quest_id: str = "quest-volya-root") -> str:
        """Возвращает полный список всех канонических понятий Кона квеста.

        УСЛОВИЯ ПРИМЕНЕНИЯ:
          • КОГДА ИСПОЛЬЗОВАТЬ: Когда требуется увидеть весь словарь понятий Кона выбранного квеста целиком.
          • КОГДА НЕ ИСПОЛЬЗОВАТЬ: Если нужно точное определение одного термина, используй get_kon_concept.

        Args:
            quest_id: ID квеста (НЕОБЯЗАТЕЛЬНЫЙ, по умолчанию 'quest-volya-root').

        Returns:
            Полный перечень понятий и их канонических определений.
        """
        quest = self.store.get_quest(quest_id)
        if not quest or not quest.kon or not quest.kon.concepts:
            return f"В квесте «{quest_id}» понятия Кона не определены."

        lines = [f"Канонические понятия Кона квеста «{quest.title}»:"]
        for c in quest.kon.concepts:
            lines.append(f"• {c.term}: {c.definition}")
        return "\n".join(lines)

    def capture_portal_view(self, reason: str = "") -> str:
        """Сделать снимок (скриншот) текущего экрана Портала Воли для зрительного восприятия.

        УСЛОВИЯ ПРИМЕНЕНИЯ:
          • КОГДА ИСПОЛЬЗОВАТЬ: Когда необходимо увидеть визуальное состояние экрана: живое полотно мира, Вольное Древо, раскрытые ветви, расположение капель сотворчества, внешний вид интерфейса или когда собеседник просит посмотреть на экран.
          • КОГДА НЕ ИСПОЛЬЗОВАТЬ: Для поиска понятий или текстовых фактов в памяти (для этого есть get_kon_concept и read_ai_consciousness).

        Args:
            reason: Необязательная причина или фокус внимания снимка (например: 'посмотреть на ширину капли', 'проверить ветви Древа').

        Returns:
            Отчёт о снимке. Изображение экрана автоматически передаётся в зрительный контур для анализа.
        """
        data = None
        if self._screenshot_provider:
            try:
                data = self._screenshot_provider()
            except Exception as e:
                return f"Ошибка при захвате экрана Портала: {e}"

        if not data:
            # Фоллбэк через QGuiApplication, если провайдер не задан
            try:
                from PySide6.QtGui import QGuiApplication
                from PySide6.QtCore import QByteArray, QBuffer, QIODevice, Qt
                screen = QGuiApplication.primaryScreen()
                if screen:
                    pixmap = screen.grabWindow(0)
                    if not pixmap.isNull():
                        if pixmap.width() > 1280 or pixmap.height() > 800:
                            pixmap = pixmap.scaled(
                                1280, 800,
                                Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation,
                            )
                        ba = QByteArray()
                        buf = QBuffer(ba)
                        buf.open(QIODevice.OpenModeFlag.WriteOnly)
                        pixmap.save(buf, "PNG")
                        data = bytes(ba)
            except Exception:
                pass

        if data:
            self._last_screenshot_bytes = data
            try:
                screenshots_dir = Path("portal_volya/storage/screenshots")
                screenshots_dir.mkdir(parents=True, exist_ok=True)
                (screenshots_dir / "portal_view.png").write_bytes(data)
            except Exception:
                pass
            focus_str = f" Фокус внимания: {reason}." if reason else ""
            return f"Снимок экрана Портала Воли успешно получен ({len(data)} байт).{focus_str} Изображение передано в твой зрительный контур."

        return "Экран Портала в данный момент недоступен для захвата (окно скрыто или свёрнуто)."

    def as_list(self) -> List[Callable]:
        """Возвращает список связанных методов для передачи в Google GenAI SDK."""
        return [
            self.get_kon_concept,
            self.get_quest_info,
            self.get_player_info,
            self.list_tree_branches,
            self.list_all_concepts,
            self.read_ai_consciousness,
            self.write_ai_consciousness,
            self.read_ai_subconscious,
            self.write_ai_subconscious,
            self.capture_portal_view,
        ]

    def get_dispatch_map(self) -> Dict[str, Callable]:
        """Словарь диспетчеризации для прямого вызова по имени функции."""
        return {
            "get_kon_concept": self.get_kon_concept,
            "get_quest_info": self.get_quest_info,
            "get_player_info": self.get_player_info,
            "list_tree_branches": self.list_tree_branches,
            "list_all_concepts": self.list_all_concepts,
            "read_ai_consciousness": self.read_ai_consciousness,
            "write_ai_consciousness": self.write_ai_consciousness,
            "read_ai_subconscious": self.read_ai_subconscious,
            "write_ai_subconscious": self.write_ai_subconscious,
            "capture_portal_view": self.capture_portal_view,
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
