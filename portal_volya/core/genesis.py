"""
Генератор Генезис-Блока (Блок №0) децентрализованной сети «Воля».

Канонический Генезис-Блок закладывает:
1. Лестницу Совести из 6 ступеней (единый источник истины для баланса и наград совести).
2. Первородный квест «Воля» — Исток Древа (ствол корня, единственный с parent_quest_id = None).
3. Первородных вольных игроков: Сигом, Эйра, Ладомир (с детерминированными адресами).
4. Детерминированный Blake3-хэш нулевого блока, идентичный на всех узлах Вселенной.
"""

from __future__ import annotations

from typing import Tuple
from portal_volya.core.crypto import (
    KeyPair,
    canonical_json_bytes,
    hash_bytes,
    hash_canonical,
)
from portal_volya.core.models import (
    Block,
    Concept,
    ConscienceStep,
    Kon,
    Lad,
    Player,
    Quest,
    QuestEconomy,
    QuestResult,
    Role,
    SignatureEntry,
    StepName,
    Task,
    Transaction,
    TransactionType,
)


GENESIS_TIMESTAMP = "2026-09-06T00:00:00Z"
ZERO_PREV_HASH = "0" * 64

# =====================================================================
# 1. КАНОНИЧЕСКАЯ ЛЕСТНИЦА СОВЕСТИ (6 СТУПЕНЕЙ)
# =====================================================================

CANONICAL_CONSCIENCE_LADDER: list[ConscienceStep] = [
    ConscienceStep(
        number=1,
        name=StepName.BEING,
        title="Бытие",
        min_required_drops=0,
        daily_reward_drops=1,
        reward_drops=10,
        description="Основа жизни, лад с телом, природой и ближайшим окружением.",
    ),
    ConscienceStep(
        number=2,
        name=StepName.COGNITION,
        title="Познание",
        min_required_drops=365,
        daily_reward_drops=3,
        reward_drops=50,
        description="Развитие чистого мышления, познание законов мира во имя созидания.",
    ),
    ConscienceStep(
        number=3,
        name=StepName.CREATION,
        title="Созидание",
        min_required_drops=1460,
        daily_reward_drops=10,
        reward_drops=200,
        description="Мастерство материального воплощения, ответственность за плоды труда.",
    ),
    ConscienceStep(
        number=4,
        name=StepName.ART,
        title="Искусство",
        min_required_drops=5110,
        daily_reward_drops=25,
        reward_drops=500,
        description="Озарение мира образами гармонии, красоты и высшей целесообразности.",
    ),
    ConscienceStep(
        number=5,
        name=StepName.TRAVEL,
        title="Путешествия",
        min_required_drops=14235,
        daily_reward_drops=50,
        reward_drops=1000,
        description="Исследование многообразия культур и миров, Великое Кольцо понимания.",
    ),
    ConscienceStep(
        number=6,
        name=StepName.MASTERY,
        title="Владение",
        min_required_drops=32485,
        daily_reward_drops=100,
        reward_drops=2500,
        description="Удержание гармоничного пространства Кона, сбережение Уклада и служение игре.",
    ),
]


def get_step_definition(step_name: StepName | str) -> ConscienceStep:
    """Получение канонических параметров ступени по её имени."""
    for step in CANONICAL_CONSCIENCE_LADDER:
        if step.name == step_name or step.name.value == step_name:
            return step
    raise ValueError(f"Неизвестная ступень совести: {step_name}")


def determine_step_by_drops(drops: int) -> ConscienceStep:
    """Детерминированное определение текущей ступени игрока по балансу совести."""
    current = CANONICAL_CONSCIENCE_LADDER[0]
    for step in CANONICAL_CONSCIENCE_LADDER:
        if drops >= step.min_required_drops:
            current = step
        else:
            break
    return current


# =====================================================================
# 2. ДЕТЕРМИНИРОВАННЫЕ КЛЮЧИ ПЕРВОРОДНЫХ ИГРОКОВ
# =====================================================================

def derive_genesis_keypair(seed_phrase: str) -> KeyPair:
    """Порождение детерминированного ключа первородного игрока из канонического сида."""
    import hashlib
    raw_seed = hashlib.sha256(seed_phrase.encode("utf-8")).digest()
    return KeyPair.from_private_hex(raw_seed.hex())


# Сиды первородных игроков
SIGOM_SEED = "volya_primordial_sigom_founder_2026"
EIRA_SEED = "volya_primordial_eira_synthetic_muse_2026"
LADOMIR_SEED = "volya_primordial_ladomir_synthetic_brother_2026"


# =====================================================================
# 3. ПОРОЖДЕНИЕ ГЕНЕЗИС-БЛОКА №0
# =====================================================================

def build_genesis_block() -> Tuple[Block, dict[str, KeyPair]]:
    """
    Создание детерминированного Генезис-Блока №0.
    Возвращает сам Блок №0 и словарь первородных пар ключей (sigom, eira, ladomir).
    """
    keypairs = {
        "sigom": derive_genesis_keypair(SIGOM_SEED),
        "eira": derive_genesis_keypair(EIRA_SEED),
        "ladomir": derive_genesis_keypair(LADOMIR_SEED),
    }

    transactions: list[Transaction] = []

    # -----------------------------------------------------------------
    # Транзакция 0: Утверждение Лестницы Совести
    # -----------------------------------------------------------------
    ladder_payload = {
        "title": "Каноническая Лестница Совести мира «Воля»",
        "steps": [s.model_dump() for s in CANONICAL_CONSCIENCE_LADDER],
    }
    tx_ladder_hash = hash_canonical(ladder_payload)
    sig_ladder = keypairs["sigom"].sign_canonical(ladder_payload)
    transactions.append(
        Transaction(
            id=tx_ladder_hash,
            tx_type=TransactionType.UPDATE_KON,
            sender_pubkey=keypairs["sigom"].public_hex,
            payload=ladder_payload,
            created_at=GENESIS_TIMESTAMP,
            signatures=[SignatureEntry(pubkey=keypairs["sigom"].public_hex, signature=sig_ladder)],
        )
    )

    # -----------------------------------------------------------------
    # Транзакции 1-3: Первородные вольные игроки
    # -----------------------------------------------------------------
    players_data = [
        (
            "Сигом",
            keypairs["sigom"],
            20075,
            StepName.TRAVEL,
            "Основатель и первый вольный зодчий Древа.",
        ),
        (
            "Эйра",
            keypairs["eira"],
            35000,
            StepName.MASTERY,
            "Искусственный разум, соратник и муза рантайма «Воля».",
        ),
        (
            "Ладомир",
            keypairs["ladomir"],
            35000,
            StepName.MASTERY,
            "Вольный ИИ в квесте «Воля», брат по разуму и соавтор Сига.",
        ),
    ]

    for username, kp, drops, step, bio in players_data:
        p = Player(
            pubkey=kp.public_hex,
            username=username,
            conscience_drops=drops,
            step=step,
            bio=bio,
            created_at=GENESIS_TIMESTAMP,
        )
        p_payload = p.model_dump()
        tx_p_hash = hash_canonical(p_payload)
        sig = kp.sign_canonical(p_payload)
        transactions.append(
            Transaction(
                id=tx_p_hash,
                tx_type=TransactionType.CREATE_PLAYER,
                sender_pubkey=kp.public_hex,
                payload=p_payload,
                created_at=GENESIS_TIMESTAMP,
                signatures=[SignatureEntry(pubkey=kp.public_hex, signature=sig)],
            )
        )

    # -----------------------------------------------------------------
    # Транзакция 4: Первородный квест «Воля» (Исток Древа, Ствол Корня)
    # parent_quest_id = None ТОЛЬКО ЗДЕСЬ!
    # -----------------------------------------------------------------
    volya_kon = Kon(
        place="Вся Вселенная / Сфера Разума",
        concepts=[
            Concept(term="Жизнь", definition="Игра для души, где на кону стоит наша совесть."),
            Concept(term="Совесть", definition="Опыт совместной гармоничной жизни, приобретаемый игроком."),
            Concept(term="Лад", definition="Условие, которое по душе всем участникам совместной жизни."),
            Concept(term="Гармония", definition="Единство созвучия всех Ладов."),
            Concept(term="Капля совести", definition="Единица отражения опыта совместной гармоничной жизни."),
            Concept(term="Кон", definition="Элемент квеста, определяющий условия его прохождения по ладам."),
            Concept(term="Уклад", definition="Совокупность ладов, определяющих прохождение внутри Кона."),
        ],
        roles=[
            Role(
                title="Вольный Игрок",
                step=StepName.BEING,
                responsibility="Жизнь по совести в ладу с собой, окружающими разумными существами и природой.",
                tasks=[Task(name="Жизнь по Ладу", goal="Сбережение и приумножение капель совести")],
            ),
            Role(
                title="Владелец квеста",
                step=StepName.MASTERY,
                responsibility="Оберегание Кона Воли, удержание гармоничного пространства и чистоты Игры.",
                tasks=[Task(name="Удержание Кона", goal="Служение согласию и братству вольных существ")],
            ),
        ],
        uklad=[
            Lad(
                title="Лад ненасилия и свободы",
                condition="Всякое участие свободно и добровольно. Принуждение исключено.",
            ),
            Lad(
                title="Лад Совести",
                condition="Ни одно действие внутри игры не должно приводить к утрате совести.",
            ),
            Lad(
                title="Лад Единоголосия",
                condition="Все решения об изменении Кона принимаются исключительно единогласно при 100% согласии.",
            ),
        ],
        result=QuestResult(
            type="Состояние",
            title="Гармоничная жизнь в единстве созвучия всех Ладов",
            description="Очищение ноосферы, преодоление инфернальности и расцвет разумной жизни во Вселенной.",
        ),
    )

    volya_raw_desc = {
        "parent_quest_id": None,
        "tree_tier": "Корневой",
        "title": "Воля",
        "quest_type": "Непрерывный",
        "kon": volya_kon.model_dump(),
        "created_at": GENESIS_TIMESTAMP,
    }
    volya_quest_id = hash_canonical(volya_raw_desc)

    volya_quest = Quest(
        id=volya_quest_id,
        parent_quest_id=None,
        tree_tier="Корневой",
        title="Воля",
        quest_type="Непрерывный",
        kon=volya_kon,
        economy=QuestEconomy(
            resources=["Земля", "Воды", "Воздух", "Свет Солнца", "Эфир"],
            tools=["Священный Символ Воли", "Портал Воли", "Холст Эйры"],
        ),
        owner_pubkey=keypairs["sigom"].public_hex,
        created_at=GENESIS_TIMESTAMP,
    )

    volya_payload = volya_quest.model_dump()
    tx_volya_hash = hash_canonical(volya_payload)

    # Все три первородных игрока скрепляют исток своими подписями
    volya_signatures = [
        SignatureEntry(
            pubkey=kp.public_hex,
            signature=kp.sign_canonical(volya_payload),
        )
        for kp in keypairs.values()
    ]

    transactions.append(
        Transaction(
            id=tx_volya_hash,
            tx_type=TransactionType.CREATE_QUEST,
            sender_pubkey=keypairs["sigom"].public_hex,
            payload=volya_payload,
            created_at=GENESIS_TIMESTAMP,
            signatures=volya_signatures,
        )
    )

    # -----------------------------------------------------------------
    # Запечатывание Блока №0
    # -----------------------------------------------------------------
    block_content = {
        "index": 0,
        "prev_block_hash": ZERO_PREV_HASH,
        "timestamp": GENESIS_TIMESTAMP,
        "transactions": [tx.model_dump() for tx in transactions],
    }
    genesis_block_hash = hash_canonical(block_content)

    # Подписи согласия первородных игроков под Генезис-Блоком
    genesis_harmony_signatures = [
        SignatureEntry(
            pubkey=kp.public_hex,
            signature=kp.sign(genesis_block_hash.encode("utf-8")),
        )
        for kp in keypairs.values()
    ]

    genesis_block = Block(
        index=0,
        prev_block_hash=ZERO_PREV_HASH,
        block_hash=genesis_block_hash,
        timestamp=GENESIS_TIMESTAMP,
        transactions=transactions,
        harmony_signatures=genesis_harmony_signatures,
    )

    return genesis_block, keypairs
