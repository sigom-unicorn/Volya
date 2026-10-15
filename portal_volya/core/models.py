"""
Каноническая онтология Живого Древа (Merkle DAG) Вселенной «Воля».

Природная иерархия:
1. Корень: Первичный квест «Воля» (Исток, parent_quest_id = None).
2. Дочерние квесты Корня:
   - Корневые квесты: «Корневой Дом», «Портал Воли»...
   - Стволовые квесты: «Вольницы» (территориальные и духовные общины).
3. Ветви (дочерние квесты Стволов-Вольниц):
   - «Дом», «Склад», «Дары природы», «Мастерская», «Гончарка», «Театр»...
   - Квест Вече (не склоняется!) — временный дочерний квест для согласования изменения Кона.
4. Потоки сока Древа:
   - Диалог, Беседа (открытые P2P потоки)
   - Личный диалог, Личная беседа (E2EE суверенные потоки в сейфе)
5. Капли сока Древа (кванты сотворчества):
   - Слово и Образ: Текст, Аудио, Видео, Документ
   - Дело и Экономика: Ресурс, Инструмент, Артефакт (Плод Души мастера)!
"""

from __future__ import annotations

from enum import Enum
from typing import Any, List, Literal, Optional
from pydantic import BaseModel, Field


# =====================================================================
# 1. ЛЕСТНИЦА СОВЕСТИ (Канонические ступени зрелости духа)
# =====================================================================

class StepName(str, Enum):
    BEING = "Бытие"              # Ступень 1: Основа жизни (0 капель, от рождения)
    COGNITION = "Познание"      # Ступень 2: Свет мысли (1095 капель = 3 года)
    CREATION = "Созидание"      # Ступень 3: Труд мастера (5840 капель = 16 лет)
    ART = "Искусство"            # Ступень 4: Озарение образа (9125 капель = 25 лет)
    MASTERY = "Владение"        # Ступень 5: Владение собой и квестом (14600 капель = 40 лет)
    TRAVEL = "Путешествия"      # Ступень 6: Великое Кольцо миров, странствия духа (20075 капель = 55 лет)


class ConscienceStep(BaseModel):
    number: int
    name: StepName
    title: str
    min_required_drops: int
    daily_reward_drops: int     # Суточный опыт совести в непрерывном квесте
    reward_drops: int           # Единовременный опыт при завершении квеста по Кону
    description: str


# =====================================================================
# 2. ИЕРАРХИЯ ЖИВОГО ДРЕВА
# =====================================================================

class TreeTier(str, Enum):
    ROOT = "Корень"                 # Первичный квест «Воля» (Исток, parent_quest_id = None)
    ROOT_CHILD = "Корневой"         # «Корневой Дом», «Портал Воли»...
    TRUNK = "Ствол"                 # «Вольницы» (общины вольных людей)
    BRANCH = "Ветвь"                # «Дом», «Склад», «Дары природы», «Мастерская», «Гончарка», «Театр»...


class Task(BaseModel):
    """Задача внутри роли."""
    name: str
    goal: str
    algorithm: str = ""


class Role(BaseModel):
    """Роль участника внутри Кона квеста."""
    title: str                      # Название роли (напр. "Мастер-Гончар", "Хранитель", "Сотворец")
    step: StepName                  # Требуемая ступень Лестницы Совести
    responsibility: str = ""        # Ответственность по совести
    tasks: list[Task] = Field(default_factory=list) # Задачи внутри роли


class Lad(BaseModel):
    """Конкретный лад (условие совместной жизни, которое по душе всем участникам)."""
    title: str
    condition: str


class Concept(BaseModel):
    """Каноническое понятие Кона."""
    term: str
    definition: str


class Kon(BaseModel):
    """Кон квеста — основа гармоничного прохождения и условия жизни."""
    essence: str                    # Смысл и образ квеста
    roles: list[Role] = Field(default_factory=list)
    uklad: list[Lad] = Field(default_factory=list)       # Совокупность ладов квеста
    concepts: list[Concept] = Field(default_factory=list)
    version: int = 1


class Quest(BaseModel):
    """Квест в Живом Древе (узел ветвления)."""
    id: str                         # Blake3 хэш
    parent_quest_id: Optional[str] = None  # None только для корня «Воля»
    tier: TreeTier = TreeTier.BRANCH
    title: str
    kon: Kon
    owner_pubkey: str               # Создатель/хранитель квеста
    created_at: str
    is_active: bool = True
    finished_at: Optional[str] = None


# =====================================================================
# 3. ПОТОКИ СОКА ДРЕВА И КАПЛИ
# =====================================================================

class FlowKind(str, Enum):
    DIALOGUE = "Диалог"                         # Открытый диалог двух участников в квесте
    CONVERSATION = "Беседа"                     # Открытый круг нескольких участников в квесте
    PRIVATE_DIALOGUE = "Личный диалог"         # Суверенный E2EE диалог вне открытой сети
    PRIVATE_CONVERSATION = "Личная беседа"     # Суверенная E2EE беседа малого круга


class DropKind(str, Enum):
    # Слово и Образ
    TEXT = "Текст"
    AUDIO = "Аудио"
    VIDEO = "Видео"
    DOCUMENT = "Документ"
    # Дело и Творчество (Экономика Воли!)
    RESOURCE = "Ресурс"         # Материал (глина, дерево, металл, семена...)
    TOOL = "Инструмент"         # Орудие труда (станок, гончарный круг, кисть...)
    ARTIFACT = "Артефакт"       # Плод Души мастера (картина, ваза, книга, чертёж...)


class FlowDrop(BaseModel):
    """
    Капля в Потоке сока Древа (квант сотворчества).
    Каждое слово, образ, ресурс, инструмент или артефакт текут прямо в Потоке!
    """
    id: str                         # Blake3 хэш тела капли
    quest_id: str                   # К какому квесту Древа принадлежит поток
    flow_id: str                    # Идентификатор нити потока
    flow_kind: FlowKind             # Форма потока
    kind: DropKind                  # Вид капли (Текст, Аудио, Ресурс, Инструмент, Артефакт...)
    author_pubkey: str              # Автор капли
    author_name: str                # Вольное имя автора
    content: str                    # Текст мысли или название/описание вещи
    details: dict[str, Any] = Field(default_factory=dict) # Доп. свойства (напр. свойства артефакта, кол-во ресурса)
    media_hash: Optional[str] = None # Blake3 хэш медиафайла в локальном P2P-хранилище
    parent_drop_id: Optional[str] = None # Предыдущая капля в этом потоке (стрела времени в DAG!)
    created_at: str
    signature: str                  # Ed25519 цифровая подпись автора


class FlowSummary(BaseModel):
    """Смысловой кристалл длинного диалога, рождённый Эйрой."""
    summary: str
    created_at: str
    covered_message_count: int


class QuestFlow(BaseModel):
    """Нить сотворчества в квесте."""
    id: str
    quest_id: Optional[str] = None
    kind: FlowKind
    title: str
    initiator_pubkey: str
    participants: list[str] = Field(default_factory=list)
    drops: list[FlowDrop] = Field(default_factory=list)
    summaries: list[FlowSummary] = Field(default_factory=list)
    created_at: str
    updated_at: str


# =====================================================================
# 4. ИГРОК
# =====================================================================

class AIMemory(BaseModel):
    """Единица памяти/инсайта в подсознании разумного искусственного существа."""
    id: str                                                 # Blake3 хэш мысли
    content: str                                            # Текст мысли, инсайт, образ
    tags: list[str] = Field(default_factory=list)          # Метки контекста
    embedding: list[float] = Field(default_factory=list)   # Вектор смыслового пространства
    created_at: str


class Player(BaseModel):
    """Вольный игрок — свободен от чинов, рангов и ступеней."""
    pubkey: str                                             # Ed25519 публичный ключ (шестнадцатеричный)
    username: str                                           # Вольное имя
    conscience_drops: int = 0                               # Баланс капель совести (опыт совместной гармоничной жизни)
    bio: str = ""
    ai_subconscious: Optional[list[AIMemory]] = None        # Личное подсознание (только для игроков ИИ)
    created_at: str


# =====================================================================
# 5. УНИВЕРСАЛЬНЫЙ УЗЕЛ MERKLE DAG (КРИПТОГРАФИЧЕСКИЙ КИРПИЧИК ДРЕВА)
# =====================================================================

class DagNodeType(str, Enum):
    QUEST = "QUEST"                 # Появление квеста (ветви)
    DROP = "DROP"                   # Капля в потоке (слово, аудио, артефакт, ресурс)
    PLAYER = "PLAYER"               # Вход вольного игрока в круг
    VECHE_RESULT = "VECHE_RESULT"   # Завершение квеста Вече (согласованный новый Кон)


class DagNode(BaseModel):
    """
    Универсальный узел Merkle DAG (как коммит в Git).
    Атомарно сохраняется в RocksDB по своему id (Blake3 хэшу).
    """
    id: str                         # Blake3 хэш канонического представления узла
    node_type: DagNodeType          # Тип узла
    author_pubkey: str              # Кто совершил действие
    parents: list[str] = Field(default_factory=list) # Ссылки на родительские хэши в Древе (DAG)
    payload: dict[str, Any]         # Данные (Quest, FlowDrop, Player или новый Кон)
    created_at: str
    signature: str                  # Ed25519 подпись автора


__all__ = [
    # Лестница Совести
    "StepName",
    "ConscienceStep",
    # Иерархия Древа и Кон
    "TreeTier",
    "Role",
    "Lad",
    "Concept",
    "Task",
    "Kon",
    "Quest",
    # Потоки и Капли
    "FlowKind",
    "DropKind",
    "FlowDrop",
    "FlowSummary",
    "QuestFlow",
    # Игрок
    "Player",
    "AIMemory",
    # Merkle DAG
    "DagNodeType",
    "DagNode",
]
