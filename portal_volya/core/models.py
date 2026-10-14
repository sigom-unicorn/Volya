"""
Троичная онтология мира «Воля»: Игрок, Квест, Поток.

Канонические законы онтологии:
1. Квесты свободны от ступеней (квест — открытое пространство созидания, ветвь Древа).
2. Ступени принадлежат Ролям внутри Кона квестов (kon.roles[i].step).
3. Все меры капель совести детерминированно определяются Лестницей Совести (Генезис-Блок №0).
4. Артефакты принадлежат исключительно создателям-игрокам и передаются из рук в руки по согласию.
5. Инструменты и Ресурсы — достояние общины Вольницы.
6. Поток — живительный сок сотворчества в четырёх естественных формах (Диалог, Беседа, Личный диалог, Личная беседа).
7. Никакого разделения на user/assistant в сообщениях.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, Field


# =====================================================================
# 1. ЛЕСТНИЦА СОВЕСТИ (Канонические ступени зрелости духа)
# =====================================================================

class StepName(str, Enum):
    BEING = "Бытие"              # Ступень 1: Основа жизни, лад с телом и природой
    COGNITION = "Познание"      # Ступень 2: Свет мысли, исследование законов мира
    CREATION = "Созидание"      # Ступень 3: Труд мастера, долговечность плодов
    ART = "Искусство"            # Ступень 4: Озарение образа, рождение небывалого
    TRAVEL = "Путешествия"      # Ступень 5: Великое Кольцо понимания миров и культур
    MASTERY = "Владение"        # Ступень 6: Хранение Кона, удержание пространства Лада


class ConscienceStep(BaseModel):
    """Каноническое определение ступени совести из Генезис-Блока №0."""
    number: int
    name: StepName
    title: str
    min_required_drops: int
    daily_reward_drops: int     # Суточный опыт лада в непрерывном квесте
    reward_drops: int           # Единовременный опыт при ладном завершении квеста
    description: str


# =====================================================================
# 2. АРТЕФАКТЫ И ИНСТРУМЕНТЫ (Триединство Экономики)
# =====================================================================

class Artifact(BaseModel):
    """
    Плоды души игрока-мастера (произведения искусства, авторские чертежи, книги).
    Принадлежат ТОЛЬКО игрокам. Квест артефактами не владеет.
    Передаются исключительно из рук в руки по согласию.
    """
    id: str
    title: str
    creator_pubkey: str
    owner_pubkey: str
    description: str = ""
    media_hash: str | None = None   # Blake3 хэш медиафайла в P2P-хранилище
    created_at: str


class QuestEconomy(BaseModel):
    """Экономическое русло квеста: выделенные общие Ресурсы и Инструменты."""
    resources: list[str] = Field(default_factory=list)  # Неделимые Дары Природы
    tools: list[str] = Field(default_factory=list)      # Привлечённые средства труда общины


# =====================================================================
# 3. ИГРОК (Вольная разумная личность)
# =====================================================================

class Player(BaseModel):
    """Вольный игрок — лист и садовник Живого Древа."""
    pubkey: str                         # Открытый ключ Ed25519 (суверенный адрес)
    username: str                       # Имя вольного игрока в пространстве «Воля»
    conscience_drops: int = 0           # Отражение опыта совместной гармоничной жизни
    step: StepName = StepName.BEING     # Текущая ступень игрока по балансу совести
    bio: str = ""                       # Сокровенное слово о себе и своём пути
    artifacts: list[Artifact] = Field(default_factory=list)      # Личные плоды души мастера
    active_tools: list[str] = Field(default_factory=list)       # Взятые в руки инструменты общины
    created_at: str
    signature: str | None = None        # Подпись волеизъявления игрока


# =====================================================================
# 4. КОН КВЕСТА: Понятия, Роли со Ступенями, Уклад, Результат
# =====================================================================

class Concept(BaseModel):
    """Каноническое понятие Кона."""
    term: str
    definition: str


class Task(BaseModel):
    """Задача внутри роли."""
    name: str
    goal: str
    algorithm: str = ""


class Role(BaseModel):
    """
    Роль участника внутри Кона квеста.
    СТУПЕНЬ ПРИНАДЛЕЖИТ РОЛИ! В одном квесте свободно созидают роли разных ступеней.
    """
    title: str
    step: StepName                      # Ступень ответственности роли (из Лестницы Совести)
    responsibility: str = ""
    tasks: list[Task] = Field(default_factory=list)


class Lad(BaseModel):
    """Элементарный кирпичик согласия Уклада: условие, которое по душе всем."""
    title: str
    condition: str


class QuestResult(BaseModel):
    """Ожидаемый результат прохождения Кона."""
    type: Literal["Артефакт", "Лад", "Состояние", "Событие"]
    title: str
    description: str = ""


class Kon(BaseModel):
    """Кон — священное русло квеста: условия прохождения по ладам."""
    place: str = "Пространство Воли"
    concepts: list[Concept] = Field(default_factory=list)
    roles: list[Role] = Field(default_factory=list)
    uklad: list[Lad] = Field(default_factory=list)
    result: QuestResult | None = None


class Participant(BaseModel):
    """Участник квеста на конкретной роли."""
    username: str
    pubkey: str
    role_title: str
    joined_at: str


# =====================================================================
# 5. КВЕСТ: Органы Живого Древа (У КВЕСТОВ НЕТ СТУПЕНИ!)
# =====================================================================

TreeTier = Literal["Корневой", "Стволовой", "Ветвь"]
QuestType = Literal["Непрерывный", "Стандартный"]


class Quest(BaseModel):
    """
    Квест — орган Живого Древа (Исток, Корень, Ствол или Ветвь).
    У квеста НЕТ поля step — квест открыт для всех вольных душ.
    """
    id: str                             # Blake3 хэш описания квеста
    parent_quest_id: str | None = None  # None ТОЛЬКО для первородного истока «Воля»!
    tree_tier: TreeTier = "Ветвь"
    title: str
    quest_type: QuestType = "Непрерывный"  # Режим совести: Непрерывный пульс / Завершаемый
    kon: Kon
    economy: QuestEconomy = Field(default_factory=QuestEconomy)
    owner_pubkey: str                   # Владелец квеста (роль ступени «Владение»)
    participants: list[Participant] = Field(default_factory=list)
    custom_canvas_tool: str | None = None   # JSON/JS артефакт особенного инструмента Холста
    created_at: str
    finished_at: str | None = None      # None для активных и вечных


# =====================================================================
# 6. ПОТОК КВЕСТА: Живительный сок Древа
# =====================================================================

FlowKind = Literal["Диалог", "Беседа", "Личный диалог", "Личная беседа"]


class MediaAttachment(BaseModel):
    """Вложение медиафайла (в сеть и блокчейн уходит только 32-байтный Blake3 хэш)."""
    blake3_hash: str
    filename: str
    mime_type: str
    size_bytes: int


class FlowMessage(BaseModel):
    """
    Сообщение в Потоке.
    Никаких ветхих рабских 'role: user/assistant' — только свободные имена творцов!
    """
    id: str
    author: str                         # Вольное имя автора (человека или ИИ)
    author_pubkey: str
    content: str
    created_at: str
    signature: str                      # Ed25519 подпись сообщения
    action: str | None = None           # Например: "Приобщить к квесту", "Предложить Лад"
    media_attachments: list[MediaAttachment] = Field(default_factory=list)


class FlowSummary(BaseModel):
    """Смысловой кристалл длинного диалога, рождённый Эйрой."""
    summary: str
    created_at: str
    covered_message_count: int


class QuestFlow(BaseModel):
    """
    Поток сотворчества и общения.
    Диалог и Беседа живут в открытом квесте и подтверждаются в блокчейне.
    Личный диалог и Личная беседа живут строго локально на устройствах с E2EE шифрованием.
    """
    id: str
    quest_id: str | None = None         # None для Личного диалога и Личной беседы
    kind: FlowKind
    title: str
    initiator_pubkey: str
    participants: list[str] = Field(default_factory=list)  # Pubkeys участников
    messages: list[FlowMessage] = Field(default_factory=list)
    summaries: list[FlowSummary] = Field(default_factory=list)
    created_at: str
    updated_at: str


# =====================================================================
# 7. РЕЕСТР И БЛОКЧЕЙН PROOF-OF-HARMONY (Детерминированный консенсус)
# =====================================================================

class TransactionType(str, Enum):
    CREATE_PLAYER = "CREATE_PLAYER"                 # Первородное волеизъявление игрока
    CREATE_QUEST = "CREATE_QUEST"                   # Рождение новой ветви Живого Древа
    UPDATE_KON = "UPDATE_KON"                       # Изменение Кона / принятие нового Лада через Вече
    JOIN_QUEST = "JOIN_QUEST"                       # Вход игрока в квест на выбранную роль
    LEAVE_QUEST = "LEAVE_QUEST"                     # Выход игрока из квеста
    CREATE_ARTIFACT = "CREATE_ARTIFACT"             # Рождение нового Плода Души мастером
    TRANSFER_ARTIFACT = "TRANSFER_ARTIFACT"         # Передача плода души из рук в руки
    DAILY_HARMONY_PULSE = "DAILY_HARMONY_PULSE"     # Суточный пульс лада в непрерывном квесте
    FINISH_QUEST = "FINISH_QUEST"                   # Завершение стандартного квеста по ладам
    RECORD_DISCORD = "RECORD_DISCORD"               # Фиксация разлада (убыль капель совести)
    APPEND_FLOW_MESSAGES = "APPEND_FLOW_MESSAGES"   # Запечатывание открытых сообщений потока


class SignatureEntry(BaseModel):
    """Подпись участника консенсуса Proof-of-Harmony."""
    pubkey: str
    signature: str


class Transaction(BaseModel):
    """Атомарное волеизъявление в децентрализованной сети «Воля»."""
    id: str                             # Blake3 хэш канонического тела транзакции
    tx_type: TransactionType
    sender_pubkey: str
    payload: dict[str, Any]
    created_at: str
    signatures: list[SignatureEntry] = Field(default_factory=list)


class Block(BaseModel):
    """
    Кристаллизованный блок Proof-of-Harmony.
    Включает в себя совершенные транзакции и подписи согласия участников.
    """
    index: int
    prev_block_hash: str                # Для Генезис-Блока №0 — 64 нуля
    block_hash: str                     # Blake3 хэш канонического содержимого блока
    timestamp: str
    transactions: list[Transaction] = Field(default_factory=list)
    harmony_signatures: list[SignatureEntry] = Field(default_factory=list)
