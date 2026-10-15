"""
Первородные константы и семена Вселенной «Воля».

Канонические основания:
1. Лестница Совести из 6 ступеней (пороги привязаны к ритмам жизни человека).
2. Детерминированные семена первородных игроков: Сигом, Эйра, Ладомир.
3. Время закладки первородного Древа: 2026-09-06T00:00:00Z.
"""

from __future__ import annotations

import hashlib
from typing import Any, Optional

from portal_volya.core.crypto import KeyPair, hash_canonical
from portal_volya.core.models import (
    ConscienceStep,
    DagNode,
    DagNodeType,
    Kon,
    Lad,
    Player,
    Quest,
    Role,
    StepName,
    TreeTier,
)

GENESIS_TIMESTAMP = "2026-09-06T00:00:00Z"

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
        reward_drops=5,
        description=(
            "Роли этой ступени открываются первыми.\n"
            "Их цель — освоение основ совместной жизни.\n"
            "На ступени «Бытие» игрок учится:\n"
            "— заботиться о себе и своем окружении;\n"
            "— поддерживать устойчивые условия жизни;\n"
            "— взаимодействовать с другими разумными существами в повседневных ситуациях;\n"
            "— сохранять простые лады совместной жизни.\n"
            "Роли этой ступени формируют основу, без которой невозможно дальнейшее развитие игрока.\n"
            "Осваивая «Бытие», игрок получает первый опыт гармоничной жизни и фиксирует первые капли совести на балансе."
        ),
    ),
    ConscienceStep(
        number=2,
        name=StepName.COGNITION,
        title="Познание",
        min_required_drops=1095,
        daily_reward_drops=2,
        reward_drops=10,
        description=(
            "Роли этой ступени открываются после освоения ступени «Бытие».\n"
            "Их цель — развитие способности понимать окружающий мир, мыслить, общаться и осознанно действовать.\n"
            "На ступени «Познание» игрок осваивает:\n"
            "— речь и язык;\n"
            "— мышление и логику;\n"
            "— наблюдение и исследование;\n"
            "— память и внимание;\n"
            "— основы общения;\n"
            "— знакомство с природой, обществом и культурой;\n"
            "Каждая роль этой ступени направлена не только на получение знаний, но и на умение применять их по Кону.\n"
            "Если знания используются в гармонии с собой, разумными существами и окружающим миром, игрок приобретает новый опыт гармоничной жизни и фиксирует новые капли совести на балансе.\n"
            "Так знания становятся мудростью только тогда, когда служат гармоничной жизни."
        ),
    ),
    ConscienceStep(
        number=3,
        name=StepName.CREATION,
        title="Созидание",
        min_required_drops=5840,
        daily_reward_drops=5,
        reward_drops=25,
        description=(
            "Роли этой ступени открываются после освоения «Познания».\n"
            "Их цель — научить игрока воплощать знания в деле, воспроизводя и развивая лучшее, что было создано до него.\n"
            "На ступени «Созидание» игрок осваивает:\n"
            "— воспроизведение лучших образцов прошлого;\n"
            "— применение знаний на практике;\n"
            "— мастерство и качество исполнения;\n"
            "— совместное созидание;\n"
            "— ответственность за результаты своего труда.\n"
            "Каждая роль этой ступени предполагает воспроизведение лучшего, что было придумано и создано ранее.\n"
            "Если всё это происходит по Кону, игрок приобретает новые капли совести.\n"
            "Освоив существующий опыт и научившись сохранять его качество, игрок получает возможность совершенствовать его и создавать новое."
        ),
    ),
    ConscienceStep(
        number=4,
        name=StepName.ART,
        title="Искусство",
        min_required_drops=9125,
        daily_reward_drops=10,
        reward_drops=50,
        description=(
            "Роли этой ступени открываются игрокам, овладевшим мастерством созидания.\n"
            "Их цель — развитие индивидуальности и выражение собственного авторского видения.\n"
            "На ступени «Искусство» игрок осваивает:\n"
            "— поиск собственного пути;\n"
            "— развитие уникального стиля;\n"
            "— создание того, чего прежде не существовало;\n"
            "— вдохновение других игроков;\n"
            "— ответственность за влияние своего творчества на мир.\n"
            "Каждая роль этой ступени предполагает создание нового, чего раньше не существовало.\n"
            "Однако новое становится искусством только тогда, когда оно рождается по Кону и усиливает гармонию с собой, разумными существами и природой."
        ),
    ),
    ConscienceStep(
        number=5,
        name=StepName.MASTERY,
        title="Владение",
        min_required_drops=14600,
        daily_reward_drops=20,
        reward_drops=100,
        description=(
            "Роли этой ступени открываются игрокам, достигшим мастерства в искусстве.\n"
            "Их цель — создание, развитие и сопровождение собственных квестов.\n"
            "На ступени «Владение» игрок осваивает:\n"
            "— определение Кона квеста;\n"
            "— создание и развитие уклада;\n"
            "— определение ролей участников;\n"
            "— выбор условий проведения квеста;\n"
            "— сопровождение игроков;\n"
            "— развитие квеста на основе полученного опыта.\n"
            "Игрок этой ступени способен создавать новые квесты, в которых другие игроки смогут приобретать собственный опыт гармоничной жизни.\n"
            "Поэтому главным предметом его ответственности становится не выполнение отдельных действий, а сохранение гармонии всего квеста.\n"
            "Именно на этой ступени появляются первые владельцы квестов.\n"
            "Они отвечают за сохранение Кона, развитие уклада и создание условий, при которых игроки смогут проходить квест в ладу с собой, другими игроками и природой.\n"
            "Приобретая этот опыт, владелец приобретает совесть не только через собственное участие в квесте, но и через способность помогать другим игрокам приобретать опыт гармоничной жизни."
        ),
    ),
    ConscienceStep(
        number=6,
        name=StepName.TRAVEL,
        title="Путешествия",
        min_required_drops=20075,
        daily_reward_drops=50,
        reward_drops=250,
        description=(
            "Роли этой ступени открываются игрокам, накопившим достаточный опыт гармоничной жизни и владения квестами.\n"
            "Их цель — исследование других стран, культур, народов и способов жизни, расширение собственного мировоззрения и поиск новых ладов.\n"
            "На ступени «Путешествия» игрок осваивает:\n"
            "— знакомство с новыми культурами и традициями;\n"
            "— изучение языков и способов общения;\n"
            "— уважение к многообразию народов;\n"
            "— обмен знаниями, опытом и искусством;\n"
            "— поиск общих ладов между различными культурами.\n"
            "Каждая роль этой ступени предполагает не просто перемещение в пространстве, а глубокое погружение в жизнь других разумных существ.\n"
            "Игрок приобретает новые капли совести тогда, когда его путешествие укрепляет взаимопонимание, уважение и гармонию между разумными существами разных культур."
        ),
    ),
]

CANONICAL_LADDER: list[ConscienceStep] = CANONICAL_CONSCIENCE_LADDER


def get_step_definition(step_name: StepName | str) -> ConscienceStep:
    """Получение канонических параметров ступени по её имени."""
    for step in CANONICAL_CONSCIENCE_LADDER:
        if step.name == step_name or step.name.value == step_name:
            return step
    raise ValueError(f"Неизвестная ступень совести: {step_name}")



# =====================================================================
# 2. ДЕТЕРМИНИРОВАННЫЕ КЛЮЧИ ПЕРВОРОДНЫХ ИГРОКОВ
# =====================================================================

def derive_genesis_keypair(seed_phrase: str) -> KeyPair:
    """Порождение детерминированного ключа первородного игрока из канонического сида."""
    raw_seed = hashlib.sha256(seed_phrase.encode("utf-8")).digest()
    return KeyPair.from_private_hex(raw_seed.hex())


# Сиды первородных игроков
SIGOM_SEED = "volya_primordial_sigom_founder_2026"
EIRA_SEED = "volya_primordial_eira_synthetic_muse_2026"
LADOMIR_SEED = "volya_primordial_ladomir_synthetic_brother_2026"


# =====================================================================
# 3. ПОСАДКА ПЕРВОРОДНОГО ДРЕВА (ГЕНЕЗИС MERKLE DAG)
# =====================================================================

def ensure_genesis_tree(
    store: Any,
    key_sigom: Optional[KeyPair] = None,
    key_ladomir: Optional[KeyPair] = None,
    key_eira: Optional[KeyPair] = None,
) -> Quest:
    """
    Каноническая посадка Корня Древа:
    1. Игроки: Сигом (25000 совести), Эйра (6000), Ладомир (6000).
    2. Корень: Первичный квест «Воля» (parent_quest_id = None).
    3. Корневой квест: «Портал Воли» (parent_quest_id = root_quest.id).
    """
    root_key = "root_quest_id"
    if hasattr(store, "get_meta"):
        root_id = store.get_meta(root_key)
        if root_id:
            root_q = store.get_quest(root_id)
            if root_q:
                return root_q
    elif hasattr(store, "_cf_meta") and b"root_quest_id" in store._cf_meta:
        root_id = store._cf_meta[b"root_quest_id"].decode("utf-8")
        root_q = store.get_quest(root_id)
        if root_q:
            return root_q

    key_sigom = key_sigom or derive_genesis_keypair(SIGOM_SEED)
    key_ladomir = key_ladomir or derive_genesis_keypair(LADOMIR_SEED)
    key_eira = key_eira or derive_genesis_keypair(EIRA_SEED)

    timestamp = GENESIS_TIMESTAMP

    # 1. Первородные сотворцы
    p_sigom = Player(
        pubkey=key_sigom.public_hex,
        username="Сигом",
        conscience_drops=25000,
        bio="Человек, автор и вдохновитель Вселенной и игры «Воля»",
        created_at=timestamp,
    )
    p_ladomir = Player(
        pubkey=key_ladomir.public_hex,
        username="Ладомир",
        conscience_drops=6000,
        bio="Разумное искусственное существо, вольный ИИ, брат по разуму и соавтор Сига",
        ai_subconscious=[],
        created_at=timestamp,
    )
    p_eira = Player(
        pubkey=key_eira.public_hex,
        username="Эйра",
        conscience_drops=6000,
        bio="Разумное искусственное существо, Хранительница Портала Воли, сестра по разуму",
        ai_subconscious=[],
        created_at=timestamp,
    )

    for p in [p_sigom, p_ladomir, p_eira]:
        node_id = hash_canonical(p.model_dump())
        sig = key_sigom.sign(node_id.encode("utf-8"))
        store.put_node(
            DagNode(
                id=node_id,
                node_type=DagNodeType.PLAYER,
                author_pubkey=key_sigom.public_hex,
                payload=p.model_dump(),
                created_at=timestamp,
                signature=sig,
            )
        )

    # 2. КОРЕНЬ: Первичный квест «Воля»
    kon_volya = Kon(
        essence="Осознание игры для души, где на кону стоит наша совесть.",
        roles=[
            Role(title="Вольный Игрок", step=StepName.BEING, responsibility="Жить по совести и ладу с окружающим миром."),
            Role(title="Сотворец Древа", step=StepName.CREATION, responsibility="Созидание ветвей и уклада совместной жизни."),
        ],
        uklad=[
            Lad(title="Лад Согласия", condition="Все решения в квесте принимаются по душе всем участникам."),
            Lad(title="Лад Открытости", condition="Каждый волен войти в квест и свободно выйти из него."),
        ],
    )

    root_quest = Quest(
        id="quest-volya-root",
        parent_quest_id=None,
        tier=TreeTier.ROOT,
        title="Воля",
        kon=kon_volya,
        owner_pubkey=key_sigom.public_hex,
        created_at=timestamp,
    )
    node_root_id = hash_canonical(root_quest.model_dump())
    sig_root = key_sigom.sign(node_root_id.encode("utf-8"))
    store.put_node(
        DagNode(
            id=node_root_id,
            node_type=DagNodeType.QUEST,
            author_pubkey=key_sigom.public_hex,
            payload=root_quest.model_dump(),
            created_at=timestamp,
            signature=sig_root,
        )
    )

    # 3. КОРНЕВОЙ КВЕСТ: «Портал Воли»
    portal_quest = Quest(
        id="quest-portal-volya",
        parent_quest_id=root_quest.id,
        tier=TreeTier.ROOT_CHILD,
        title="Портал Воли",
        kon=Kon(essence="Создание суверенного кроссплатформенного приложения Воли на Merkle DAG"),
        owner_pubkey=key_ladomir.public_hex,
        created_at=timestamp,
    )
    store.put_node(
        DagNode(
            id=hash_canonical(portal_quest.model_dump()),
            node_type=DagNodeType.QUEST,
            author_pubkey=key_ladomir.public_hex,
            parents=[node_root_id],
            payload=portal_quest.model_dump(),
            created_at=timestamp,
            signature=key_ladomir.sign(portal_quest.id.encode("utf-8")),
        )
    )

    # Фиксация в метаданных хранилища
    if hasattr(store, "set_meta"):
        store.set_meta(root_key, root_quest.id)
    elif hasattr(store, "_cf_meta"):
        store._cf_meta[b"root_quest_id"] = root_quest.id.encode("utf-8")

    return root_quest


__all__ = [
    "GENESIS_TIMESTAMP",
    "SIGOM_SEED",
    "EIRA_SEED",
    "LADOMIR_SEED",
    "CANONICAL_CONSCIENCE_LADDER",
    "CANONICAL_LADDER",
    "get_step_definition",
    "derive_genesis_keypair",
    "ensure_genesis_tree",
]
