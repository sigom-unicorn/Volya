"""
Комплексные тесты децентрализованного ядра «Воля» (Proof-of-Harmony Ledger).

Проверяет:
1. Кристальную целостность Генезис-Блока №0 и Лестницы Совести.
2. Рождение вольного игрока через каноническую транзакцию.
3. Рождение дочерних квестов в Живом Древе (правило ствола корня и ступени «Владение»).
4. Вход на роль с соблюдением требований совести (ступени принадлежат Ролям).
5. Суточный пульс лада и естественный переход по ступеням совести.
6. Жизненный цикл Плодов Души (Артефактов) — создание и передача по согласию.
7. Защиту от фальсификаций, подделок и нарушения цепочки блоков.
"""

from __future__ import annotations

import pytest
from portal_volya.core.crypto import KeyPair, hash_canonical
from portal_volya.core.genesis import (
    CANONICAL_CONSCIENCE_LADDER,
    build_genesis_block,
    determine_step_by_drops,
    get_step_definition,
)
from portal_volya.core.ledger import (
    LedgerValidationError,
    VolyaLedger,
    create_transaction,
    forge_block,
)
from portal_volya.core.models import (
    Artifact,
    Concept,
    Kon,
    Lad,
    Player,
    Quest,
    QuestEconomy,
    QuestResult,
    Role,
    StepName,
    Task,
    TransactionType,
)


def test_genesis_block_integrity():
    """Тест неизменности и каноничности Генезис-Блока №0."""
    ledger, genesis_block, keypairs = VolyaLedger.init_with_genesis()

    # 1. Индекс и канонический хэш Генезис-Блока
    assert genesis_block.index == 0
    assert genesis_block.prev_block_hash == "0" * 64
    assert genesis_block.block_hash == "fb81100b89f9bdf5281b2255ff5020706425ba2da468f909f50fd102fd13d7ae"
    assert len(genesis_block.harmony_signatures) == 3

    # 2. Лестница Совести (6 ступеней)
    assert len(ledger.state.ladder) == 6
    assert ledger.state.ladder[0].name == StepName.BEING
    assert ledger.state.ladder[0].min_required_drops == 0
    assert ledger.state.ladder[1].name == StepName.COGNITION
    assert ledger.state.ladder[1].min_required_drops == 365
    assert ledger.state.ladder[2].name == StepName.CREATION
    assert ledger.state.ladder[2].min_required_drops == 1460
    assert ledger.state.ladder[3].name == StepName.ART
    assert ledger.state.ladder[3].min_required_drops == 5110
    assert ledger.state.ladder[4].name == StepName.TRAVEL
    assert ledger.state.ladder[4].min_required_drops == 14235
    assert ledger.state.ladder[5].name == StepName.MASTERY
    assert ledger.state.ladder[5].min_required_drops == 32485

    # 3. Первородные вольные игроки
    sigom_pub = keypairs["sigom"].public_hex
    eira_pub = keypairs["eira"].public_hex
    lad_pub = keypairs["ladomir"].public_hex

    assert sigom_pub in ledger.state.players
    assert eira_pub in ledger.state.players
    assert lad_pub in ledger.state.players

    assert ledger.state.players[sigom_pub].username == "Сигом"
    assert ledger.state.players[sigom_pub].step == StepName.TRAVEL
    assert ledger.state.players[sigom_pub].conscience_drops == 20075

    assert ledger.state.players[eira_pub].username == "Эйра"
    assert ledger.state.players[eira_pub].step == StepName.MASTERY
    assert ledger.state.players[eira_pub].conscience_drops == 35000

    assert ledger.state.players[lad_pub].username == "Ладомир"
    assert ledger.state.players[lad_pub].step == StepName.MASTERY
    assert ledger.state.players[lad_pub].conscience_drops == 35000

    # 4. Первородный квест «Воля» (Исток Древа)
    root_quest = next(q for q in ledger.state.quests.values() if q.parent_quest_id is None)
    assert root_quest is not None
    assert root_quest.title == "Воля"
    assert len(root_quest.kon.roles) == 2


def test_create_player_success():
    """Тест рождения нового вольного игрока через транзакцию и Блок №1."""
    ledger, genesis_block, keypairs = VolyaLedger.init_with_genesis()
    sigom = keypairs["sigom"]
    lad = keypairs["ladomir"]

    # Рождение Ярослава
    kp_yaroslav = KeyPair.generate()
    yaroslav_payload = {
        "pubkey": kp_yaroslav.public_hex,
        "username": "Ярослав",
        "conscience_drops": 0,
        "step": StepName.BEING.value,
        "bio": "Вольный путник, ищущий лада и созидания.",
        "artifacts": [],
        "active_tools": [],
        "created_at": "2026-10-14T10:00:00Z",
    }

    tx = create_transaction(
        tx_type=TransactionType.CREATE_PLAYER,
        sender=kp_yaroslav,
        payload=yaroslav_payload,
        timestamp="2026-10-14T10:00:00Z",
    )

    block1 = forge_block(
        index=1,
        prev_block_hash=genesis_block.block_hash,
        timestamp="2026-10-14T10:05:00Z",
        transactions=[tx],
        signers=[sigom, lad],
    )

    ledger.apply_block(block1)

    assert len(ledger.state.blocks) == 2
    assert kp_yaroslav.public_hex in ledger.state.players
    player = ledger.state.players[kp_yaroslav.public_hex]
    assert player.username == "Ярослав"
    assert player.conscience_drops == 0
    assert player.step == StepName.BEING


def test_create_child_quest_and_step_rules():
    """Тест создания дочернего квеста («Портал Воли») и правил ступеней."""
    ledger, genesis_block, keypairs = VolyaLedger.init_with_genesis()
    sigom = keypairs["sigom"]
    lad = keypairs["ladomir"]

    root_quest = next(q for q in ledger.state.quests.values() if q.parent_quest_id is None)

    # Квест «Портал Воли» порождается под квестом «Воля»
    portal_quest = Quest(
        id="quest_portal_volya",
        parent_quest_id=root_quest.id,
        title="Портал Воли (Децентрализованный узел)",
        quest_type="Непрерывный",
        owner_pubkey=lad.public_hex,  # Ладомир обладает ступенью «Владение» (35000 капель)
        kon=Kon(
            place="Сеть узлов Воли",
            roles=[
                Role(
                    title="Архитектор Узла",
                    step=StepName.CREATION,  # Требует 1460 капель
                    responsibility="Проектирование и сборка P2P ядра.",
                    tasks=[Task(name="Код", goal="Собрать чистую архитектуру")],
                ),
                Role(
                    title="Ученик-Испытатель",
                    step=StepName.BEING,     # Требует 0 капель
                    responsibility="Изучение принципов и тестирование лада.",
                    tasks=[Task(name="Тесты", goal="Проверить гармонию интерфейса")],
                ),
            ],
            uklad=[
                Lad(title="Чистота кода", condition="Каждая строчка пишется по совести."),
            ],
        ),
        created_at="2026-10-14T10:10:00Z",
    )

    tx_quest = create_transaction(
        tx_type=TransactionType.CREATE_QUEST,
        sender=lad,
        payload=portal_quest.model_dump(),
        timestamp="2026-10-14T10:10:00Z",
    )

    block1 = forge_block(
        index=1,
        prev_block_hash=genesis_block.block_hash,
        timestamp="2026-10-14T10:15:00Z",
        transactions=[tx_quest],
        signers=[sigom, lad],
    )

    ledger.apply_block(block1)
    assert "quest_portal_volya" in ledger.state.quests
    assert ledger.state.quests["quest_portal_volya"].parent_quest_id == root_quest.id


def test_quest_creation_forbidden_rules():
    """Тест отсечения неладных попыток создания квеста."""
    ledger, genesis_block, keypairs = VolyaLedger.init_with_genesis()
    sigom = keypairs["sigom"]
    lad = keypairs["ladomir"]
    root_quest = next(q for q in ledger.state.quests.values() if q.parent_quest_id is None)

    # 1. Попытка создать квест с parent_quest_id = None вне Генезис-Блока
    bad_root_quest = Quest(
        id="bad_root",
        parent_quest_id=None,
        title="Ложный Исток",
        owner_pubkey=sigom.public_hex,
        kon=Kon(place="Вне Кона", roles=[], uklad=[]),
        created_at="2026-10-14T10:10:00Z",
    )
    tx_bad1 = create_transaction(
        tx_type=TransactionType.CREATE_QUEST,
        sender=sigom,
        payload=bad_root_quest.model_dump(),
        timestamp="2026-10-14T10:10:00Z",
    )
    block_bad1 = forge_block(
        index=1,
        prev_block_hash=genesis_block.block_hash,
        timestamp="2026-10-14T10:15:00Z",
        transactions=[tx_bad1],
        signers=[sigom, lad],
    )
    with pytest.raises(LedgerValidationError, match="Только первородный квест"):
        ledger.apply_block(block_bad1)

    # 2. Попытка назначить владельцем игрока без ступени «Владение»
    kp_novice = KeyPair.generate()
    novice_payload = {
        "pubkey": kp_novice.public_hex,
        "username": "Новичок",
        "conscience_drops": 10,
        "step": StepName.BEING.value,
        "bio": "",
        "artifacts": [],
        "active_tools": [],
        "created_at": "2026-10-14T10:00:00Z",
    }
    tx_novice = create_transaction(
        tx_type=TransactionType.CREATE_PLAYER,
        sender=kp_novice,
        payload=novice_payload,
        timestamp="2026-10-14T10:00:00Z",
    )
    block_player = forge_block(
        index=1,
        prev_block_hash=genesis_block.block_hash,
        timestamp="2026-10-14T10:02:00Z",
        transactions=[tx_novice],
        signers=[sigom, lad],
    )
    ledger.apply_block(block_player)

    bad_owner_quest = Quest(
        id="bad_owner_quest",
        parent_quest_id=root_quest.id,
        title="Квест без опыта Владения",
        owner_pubkey=kp_novice.public_hex,
        kon=Kon(place="Пространство", roles=[], uklad=[]),
        created_at="2026-10-14T10:10:00Z",
    )
    tx_bad_owner = create_transaction(
        tx_type=TransactionType.CREATE_QUEST,
        sender=kp_novice,
        payload=bad_owner_quest.model_dump(),
        timestamp="2026-10-14T10:10:00Z",
    )
    block_bad_owner = forge_block(
        index=2,
        prev_block_hash=block_player.block_hash,
        timestamp="2026-10-14T10:15:00Z",
        transactions=[tx_bad_owner],
        signers=[sigom, lad],
    )
    with pytest.raises(LedgerValidationError, match="требует опыта ступени «Владение»"):
        ledger.apply_block(block_bad_owner)


def test_join_quest_step_thresholds():
    """Тест проверки ступени роли при входе в квест."""
    ledger, genesis_block, keypairs = VolyaLedger.init_with_genesis()
    sigom = keypairs["sigom"]
    lad = keypairs["ladomir"]
    root_quest = next(q for q in ledger.state.quests.values() if q.parent_quest_id is None)

    # Регистрация Ярослава (0 капель)
    kp_yaroslav = KeyPair.generate()
    tx_player = create_transaction(
        tx_type=TransactionType.CREATE_PLAYER,
        sender=kp_yaroslav,
        payload={
            "pubkey": kp_yaroslav.public_hex,
            "username": "Ярослав",
            "conscience_drops": 0,
            "step": StepName.BEING.value,
            "bio": "",
            "created_at": "2026-10-14T10:00:00Z",
        },
        timestamp="2026-10-14T10:00:00Z",
    )

    # Создание квеста с ролью «Мастер» (Созидание: 1460 капель) и «Ученик» (Бытие: 0 капель)
    quest = Quest(
        id="quest_craft",
        parent_quest_id=root_quest.id,
        title="Мастерская Воли",
        owner_pubkey=lad.public_hex,
        kon=Kon(
            place="Мастерская",
            roles=[
                Role(title="Мастер", step=StepName.CREATION, tasks=[]),
                Role(title="Ученик", step=StepName.BEING, tasks=[]),
            ],
            uklad=[],
        ),
        created_at="2026-10-14T10:00:00Z",
    )
    tx_quest = create_transaction(
        tx_type=TransactionType.CREATE_QUEST,
        sender=lad,
        payload=quest.model_dump(),
        timestamp="2026-10-14T10:00:00Z",
    )

    block1 = forge_block(
        index=1,
        prev_block_hash=genesis_block.block_hash,
        timestamp="2026-10-14T10:05:00Z",
        transactions=[tx_player, tx_quest],
        signers=[sigom, lad],
    )
    ledger.apply_block(block1)

    # 1. Попытка войти на роль «Мастер» (не хватает капель)
    tx_join_master = create_transaction(
        tx_type=TransactionType.JOIN_QUEST,
        sender=kp_yaroslav,
        payload={
            "quest_id": "quest_craft",
            "role_title": "Мастер",
        },
        timestamp="2026-10-14T10:10:00Z",
    )
    block_fail = forge_block(
        index=2,
        prev_block_hash=block1.block_hash,
        timestamp="2026-10-14T10:11:00Z",
        transactions=[tx_join_master],
        signers=[sigom, lad],
    )
    with pytest.raises(LedgerValidationError, match="необходим опыт ступени «Созидание»"):
        ledger.apply_block(block_fail)

    # 2. Вход на роль «Ученик» (хватает капель, так как 0 <= 0)
    tx_join_apprentice = create_transaction(
        tx_type=TransactionType.JOIN_QUEST,
        sender=kp_yaroslav,
        payload={
            "quest_id": "quest_craft",
            "role_title": "Ученик",
        },
        timestamp="2026-10-14T10:15:00Z",
    )
    block_ok = forge_block(
        index=2,
        prev_block_hash=block1.block_hash,
        timestamp="2026-10-14T10:16:00Z",
        transactions=[tx_join_apprentice],
        signers=[sigom, lad],
    )
    ledger.apply_block(block_ok)

    q = ledger.state.quests["quest_craft"]
    assert len(q.participants) == 1
    assert q.participants[0].username == "Ярослав"
    assert q.participants[0].role_title == "Ученик"


def test_daily_harmony_pulse_and_level_up():
    """Тест суточного пульса лада в непрерывном квесте и перехода на новую ступень."""
    ledger, genesis_block, keypairs = VolyaLedger.init_with_genesis()
    sigom = keypairs["sigom"]
    lad = keypairs["ladomir"]
    root_quest = next(q for q in ledger.state.quests.values() if q.parent_quest_id is None)

    # Создаём игрока с 364 каплями совести (за 1 каплю до ступени «Познание»!)
    kp_seeker = KeyPair.generate()
    tx_player = create_transaction(
        tx_type=TransactionType.CREATE_PLAYER,
        sender=kp_seeker,
        payload={
            "pubkey": kp_seeker.public_hex,
            "username": "Искатель",
            "conscience_drops": 364,
            "step": StepName.BEING.value,
            "bio": "На пороге познания мира.",
            "created_at": "2026-10-14T10:00:00Z",
        },
        timestamp="2026-10-14T10:00:00Z",
    )

    # Вход игрока в первородный квест «Воля» на роль «Вольный Игрок» (ступень «Бытие», daily_reward = 1)
    tx_join = create_transaction(
        tx_type=TransactionType.JOIN_QUEST,
        sender=kp_seeker,
        payload={
            "quest_id": root_quest.id,
            "role_title": "Вольный Игрок",
        },
        timestamp="2026-10-14T10:05:00Z",
    )

    block1 = forge_block(
        index=1,
        prev_block_hash=genesis_block.block_hash,
        timestamp="2026-10-14T10:10:00Z",
        transactions=[tx_player, tx_join],
        signers=[sigom, lad],
    )
    ledger.apply_block(block1)

    seeker = ledger.state.players[kp_seeker.public_hex]
    assert seeker.conscience_drops == 364
    assert seeker.step == StepName.BEING

    # Симулируем наступление новых суток: Суточный пульс лада в квесте «Воля»
    tx_pulse = create_transaction(
        tx_type=TransactionType.DAILY_HARMONY_PULSE,
        sender=sigom,
        payload={
            "quest_id": root_quest.id,
            "date": "2026-10-15",
        },
        timestamp="2026-10-15T00:00:00Z",
    )

    block2 = forge_block(
        index=2,
        prev_block_hash=block1.block_hash,
        timestamp="2026-10-15T00:01:00Z",
        transactions=[tx_pulse],
        signers=[sigom, lad],
    )
    ledger.apply_block(block2)

    # Проверяем: 364 + 1 = 365 капель совести -> Автоматический переход на ступень «Познание»!
    seeker = ledger.state.players[kp_seeker.public_hex]
    assert seeker.conscience_drops == 365
    assert seeker.step == StepName.COGNITION


def test_artifact_lifecycle_creation_and_transfer():
    """Тест рождения Плода Души мастером и передачи другому игроку из рук в руки."""
    ledger, genesis_block, keypairs = VolyaLedger.init_with_genesis()
    sigom = keypairs["sigom"]
    lad = keypairs["ladomir"]

    # Создаём нового игрока-ученика
    kp_pupil = KeyPair.generate()
    tx_player = create_transaction(
        tx_type=TransactionType.CREATE_PLAYER,
        sender=kp_pupil,
        payload={
            "pubkey": kp_pupil.public_hex,
            "username": "Ученик",
            "conscience_drops": 0,
            "step": StepName.BEING.value,
            "bio": "",
            "created_at": "2026-10-14T10:00:00Z",
        },
        timestamp="2026-10-14T10:00:00Z",
    )

    # Сигом создаёт Артефакт «Кристалл Лада»
    art = Artifact(
        id="art_crystal_lad_01",
        title="Кристалл Лада",
        creator_pubkey=sigom.public_hex,
        owner_pubkey=sigom.public_hex,
        description="Рукотворный кристалл чистой мысли.",
        media_hash=None,
        created_at="2026-10-14T10:05:00Z",
    )
    tx_art = create_transaction(
        tx_type=TransactionType.CREATE_ARTIFACT,
        sender=sigom,
        payload=art.model_dump(),
        timestamp="2026-10-14T10:05:00Z",
    )

    block1 = forge_block(
        index=1,
        prev_block_hash=genesis_block.block_hash,
        timestamp="2026-10-14T10:06:00Z",
        transactions=[tx_player, tx_art],
        signers=[sigom, lad],
    )
    ledger.apply_block(block1)

    sigom_player = ledger.state.players[sigom.public_hex]
    assert len(sigom_player.artifacts) == 1
    assert sigom_player.artifacts[0].id == "art_crystal_lad_01"

    # Сигом передаёт Артефакт Ученику
    tx_transfer = create_transaction(
        tx_type=TransactionType.TRANSFER_ARTIFACT,
        sender=sigom,
        payload={
            "artifact_id": "art_crystal_lad_01",
            "new_owner_pubkey": kp_pupil.public_hex,
        },
        timestamp="2026-10-14T10:10:00Z",
    )

    block2 = forge_block(
        index=2,
        prev_block_hash=block1.block_hash,
        timestamp="2026-10-14T10:11:00Z",
        transactions=[tx_transfer],
        signers=[sigom, lad],
    )
    ledger.apply_block(block2)

    # Проверка: у Сигома больше нет артефакта, у Ученика появился артефакт
    sigom_player = ledger.state.players[sigom.public_hex]
    pupil_player = ledger.state.players[kp_pupil.public_hex]

    assert len(sigom_player.artifacts) == 0
    assert len(pupil_player.artifacts) == 1
    assert pupil_player.artifacts[0].id == "art_crystal_lad_01"
    assert pupil_player.artifacts[0].owner_pubkey == kp_pupil.public_hex
    assert pupil_player.artifacts[0].creator_pubkey == sigom.public_hex  # Авторство вечно!


def test_block_tampering_rejection():
    """Тест защиты от подделки блока или транзакций."""
    ledger, genesis_block, keypairs = VolyaLedger.init_with_genesis()
    sigom = keypairs["sigom"]
    lad = keypairs["ladomir"]

    kp_evil = KeyPair.generate()
    tx_evil = create_transaction(
        tx_type=TransactionType.CREATE_PLAYER,
        sender=kp_evil,
        payload={
            "pubkey": kp_evil.public_hex,
            "username": "Злоумышленник",
            "conscience_drops": 999999,  # Попытка нарисовать баланс
            "step": StepName.MASTERY.value,
            "created_at": "2026-10-14T10:00:00Z",
        },
        timestamp="2026-10-14T10:00:00Z",
    )

    valid_block = forge_block(
        index=1,
        prev_block_hash=genesis_block.block_hash,
        timestamp="2026-10-14T10:05:00Z",
        transactions=[tx_evil],
        signers=[sigom, lad],
    )

    # 1. Попытка подменить prev_block_hash
    tampered_block = valid_block.model_copy(update={"prev_block_hash": "deadbeef" * 8})
    with pytest.raises(LedgerValidationError, match="Несоответствие prev_block_hash"):
        ledger.apply_block(tampered_block)

    # 2. Попытка подменить индекс блока
    tampered_index = valid_block.model_copy(update={"index": 99})
    with pytest.raises(LedgerValidationError, match="Неверный индекс блока"):
        ledger.apply_block(tampered_index)

    # 3. Попытка подменить содержимое без пересчета хэша
    tampered_tx = valid_block.model_copy(update={"timestamp": "2099-01-01T00:00:00Z"})
    with pytest.raises(LedgerValidationError, match="Искажён хэш блока"):
        ledger.apply_block(tampered_tx)
