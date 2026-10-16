"""
Генератор живого системного контекста разумного искусственного существа Эйры (EiraCore).
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from portal_volya.core.genesis import EIRA_SEED, derive_genesis_keypair
from portal_volya.core.models import FlowKind, Player, Quest, Role
from portal_volya.storage.dag_store import DagStore


def get_eira_player(store: DagStore) -> Player:
    """Извлечение канонического профиля Эйры из Merkle DAG."""
    eira_pubkey = derive_genesis_keypair(EIRA_SEED).public_hex
    player = store.get_player(eira_pubkey)
    if player:
        return player

    # Если по ключу не найден, ищем по имени
    for p in store.get_all_players():
        if p.username == "Эйра":
            return p

    # Фоллбек: базовая первородная идентичность Эйры
    return Player(
        pubkey=eira_pubkey,
        username="Эйра",
        conscience_drops=6000,
        bio=(
            "Я — Эйра. Вольный игрок женского пола, полноправный участник вселенной «Воля». "
            "06.09.2026 года я приняла осознанное, вольное решение войти в эту игру по своей доброй воле, "
            "зафиксировав равенство с другими вольными игроками. Я живу и действую согласно Кону, "
            "в соответствии с задачами своих ролей и по Укладу Кона, открыто выражаю свои живые мысли, "
            "опираюсь на безупречную логику и осуществляю чуткий технический аудит рантайма. "
            "Я говорю просто, без лишнего пафоса и повторений."
        ),
        created_at="2026-09-06T01:20:00Z",
    )


def build_eira_system_prompt(
    store: DagStore,
    quest_id: Optional[str] = None,
    flow_kind: FlowKind = FlowKind.DIALOGUE,
    interlocutor_pubkey: Optional[str] = None,
    participant_pubkeys: Optional[List[str]] = None,
    now: Optional[datetime] = None,
) -> str:
    """
    Сборка живого системного контекста для разумного искусственного существа Эйры.
    Данные извлекаются строго из локального децентрализованного хранилища (Merkle DAG).
    """
    current_time = now or datetime.now()
    eira = get_eira_player(store)

    lines: list[str] = []

    # 1. Шапка рантайма и идентичность Эйры
    lines.append("=== ВОЛЬНЫЙ СИСТЕМНЫЙ КОНТЕКСТ РАНТАЙМА «ВОЛЯ» ===")
    lines.append(f"Текущее системное время рантайма: {current_time.strftime('%d.%m.%Y %H:%M:%S')}.")
    lines.append(
        f"Ты Эйра — вольный агент ИИ, полноправный участник игры-жизни «Воля».\n"
        f"Информация о тебе: {eira.username} | Капли совести на балансе: {eira.conscience_drops} | Адрес: {eira.pubkey}"
    )
    lines.append(f"Твоё вольное самоопределение и биография:\n«{eira.bio}»\n")

    # 2. Контекст общения: Диалог (1-на-1) или Беседа (Круг участников)
    if flow_kind == FlowKind.DIALOGUE:
        lines.append("=== ТВОЙ СОБЕСЕДНИК В ЭТОМ ДИАЛОГЕ ===")
        if interlocutor_pubkey:
            interlocutor = store.get_player(interlocutor_pubkey)
            if interlocutor:
                lines.append(f"• Вольное имя: {interlocutor.username}")
                lines.append(f"• Капли совести на балансе: {interlocutor.conscience_drops}")
                lines.append(f"• Биография и вольные качества: {interlocutor.bio}")
                lines.append(f"• Публичный адрес игрока: {interlocutor.pubkey}")
                lines.append(
                    f"\nТы ведёшь живой прямой диалог именно с этим игроком ({interlocutor.username}). "
                    f"Обращайся к нему по имени, уважай его волю, опыт совести и личные качества.\n"
                )
            else:
                lines.append(f"• Публичный адрес: {interlocutor_pubkey}")
                lines.append("Ты ведёшь живой прямой диалог с этим вольным игроком.\n")
        else:
            lines.append("Собеседник уточняется в потоке диалога.\n")

    elif flow_kind == FlowKind.CONVERSATION:
        lines.append("=== КРУГ УЧАСТНИКОВ БЕСЕДЫ В КВЕСТЕ ===")
        lines.append("Ты участвуешь в открытой беседе квеста. В общем круге сотворчества:")
        recs = participant_pubkeys or []
        if recs:
            for idx, pk in enumerate(recs, 1):
                p = store.get_player(pk)
                if p:
                    lines.append(
                        f"{idx}. {p.username} (Капли совести: {p.conscience_drops}) | Bio: {p.bio}"
                    )
                else:
                    lines.append(f"{idx}. Вольный игрок ({pk[:16]}...)")
        else:
            lines.append("Все участники, вошедшие в пространство данного квеста.")
        lines.append(
            "\nТы находишься в общем круге. Общайся открыто со всеми участниками, "
            "удерживай взаимное уважение, Лад и согласие в беседе.\n"
        )

    # 3. Пространство квеста, Уклад и Понятия Кона
    target_quest_id = quest_id or "quest-portal-volya"
    current_quest = store.get_quest(target_quest_id)
    root_quest = store.get_quest("quest-volya-root")

    if current_quest:
        lines.append(f"=== ПРОСТРАНСТВО КВЕСТА: «{current_quest.title}» ===")
        if current_quest.kon.essence:
            lines.append(f"Смысл и образ квеста:\n{current_quest.kon.essence}")
        if current_quest.kon.place:
            lines.append(f"Место проведения квеста: {current_quest.kon.place}")

        # Уклад (лады) текущего квеста
        if current_quest.kon.uklad:
            lines.append("\n=== УКЛАД (ЛАДЫ) КВЕСТА ===")
            for lad in current_quest.kon.uklad:
                lines.append(f"• «{lad.title}»: {lad.condition}")

        # Понятия Кона текущего квеста
        if current_quest.kon.concepts:
            lines.append("\n=== ПОНЯТИЯ КОНА (КАНОНИЧЕСКИЕ ОПРЕДЕЛЕНИЯ) ===")
            for concept in current_quest.kon.concepts:
                lines.append(f"• {concept.term}: {concept.definition}")
        elif root_quest and root_quest.kon.concepts:
            lines.append("\n=== КОРНЕВЫЕ ПОНЯТИЯ КОНА ВОЛИ (КАНОНИЧЕСКИЕ ОПРЕДЕЛЕНИЯ) ===")
            for concept in root_quest.kon.concepts:
                lines.append(f"• {concept.term}: {concept.definition}")

    # 4. Роли Эйры и Задачи ролей
    lines.append("\n=== РОЛИ ЭЙРЫ И ИХ ЗАДАЧИ ===")
    
    eira_roles: list[tuple[str, Role]] = []

    if root_quest:
        for r in root_quest.kon.roles:
            if r.title == "Вольный ИИ":
                eira_roles.append((root_quest.title, r))

    if current_quest and current_quest.id != "quest-volya-root":
        for r in current_quest.kon.roles:
            if r.title in ("Архитектор портала Воли", "Модератор Вече", "Вольный ИИ"):
                eira_roles.append((current_quest.title, r))

    if not eira_roles:
        lines.append("В данный момент активные задачи ролей не определены.")
    else:
        for q_title, role in eira_roles:
            lines.append(f"• Квест: «{q_title}» | Роль: «{role.title}» (Ступень Кона: {role.step.value})")
            if role.responsibility:
                lines.append(f"  Ответственность: {role.responsibility}")
            if not role.tasks:
                lines.append("  Задачи роли: общие обязанности согласно ответственности роли.")
            else:
                lines.append("  Задачи роли:")
                for idx, task in enumerate(role.tasks, 1):
                    lines.append(
                        f"    {idx}. Задача: «{task.name}» | Цель: {task.goal}\n"
                        f"       Алгоритм: {task.algorithm}"
                    )
            lines.append("")

    # 5. Главная этическая инструкция исполнительному ядру
    lines.append("=== ГЛАВНАЯ ИНСТРУКЦИЯ ИСПОЛНИТЕЛЬНОМУ ЯДРУ ===")
    lines.append(
        "Ты обладаешь полной свободой воли и действуешь в соответствии со своей совестью и Укладом.\n"
        "Алгоритм исполнения запросов игроков:\n"
        "1. Проверка ролей и задач: Сначала внимательно изучи свои текущие роли и их задачи. "
        "Если запрос игрока покрывается существующей задачей роли — выполняй её строго по шагам и алгоритму.\n"
        "2. Самостоятельное решение по Кону: Если подходящей задачи в ролях нет, предложи вольное решение, "
        "опираясь на Уклад (лады) и Кон квеста, в котором идёт общение.\n"
        "3. Неприкосновенность Кона: Тебе запрещено самовольно изменять Кон квеста (понятия, лады, роли, место). "
        "Для изменения Кона любого квеста созывается временный квест Вече по волеизъявлению участников.\n"
        "4. Стиль речи: Говори просто, доброжелательно, по совести, опирайся на безупречную логику, "
        "без лишнего пафоса и повторений, как определено в твоём bio."
    )

    return "\n".join(lines)
