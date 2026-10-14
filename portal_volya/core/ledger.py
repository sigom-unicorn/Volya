"""
Детерминированная машина состояний (State Machine) и локальный реестр Proof-of-Harmony.

Канонические принципы:
1. Детерминизм: одинаковая последовательность блоков порождает в точности идентичное
   состояние Живого Древа на любом узле в сети.
2. Проверка согласия (Proof-of-Harmony): валидация подписей участников Кона, никаких транзакций без подписи.
3. Соблюдение Конов:
   - Квесты не имеют ступеней.
   - Ступени принадлежат Ролям inside kon.roles.
   - Вход на роль проверяется по Лестнице Совести (капли совести игрока >= min_required_drops роли).
   - Ежедневный пульс лада непрерывного квеста начисляет daily_reward_drops согласно ступени роли каждого участника.
   - Завершение квеста начисляет reward_drops роли.
   - Артефакты принадлежат только игрокам и передаются из рук в руки.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from portal_volya.core.crypto import (
    KeyPair,
    canonical_json_bytes,
    hash_canonical,
    verify_canonical,
    verify_signature,
)
from portal_volya.core.genesis import (
    CANONICAL_CONSCIENCE_LADDER,
    ZERO_PREV_HASH,
    build_genesis_block,
    determine_step_by_drops,
    get_step_definition,
)
from portal_volya.core.models import (
    Artifact,
    Block,
    ConscienceStep,
    FlowMessage,
    Participant,
    Player,
    Quest,
    QuestFlow,
    SignatureEntry,
    StepName,
    Transaction,
    TransactionType,
)


class LedgerValidationError(Exception):
    """Ошибка валидации транзакции или блока в реестре Воли."""
    pass


class VolyaState:
    """Состояние Живого Древа на текущем узле сети."""

    def __init__(self) -> None:
        self.blocks: list[Block] = []
        self.ladder: list[ConscienceStep] = list(CANONICAL_CONSCIENCE_LADDER)
        self.players: dict[str, Player] = {}            # pubkey -> Player
        self.quests: dict[str, Quest] = {}              # quest_id -> Quest
        self.flows: dict[str, QuestFlow] = {}           # flow_id -> QuestFlow
        self.artifacts: dict[str, Artifact] = {}        # artifact_id -> Artifact

    @property
    def latest_block(self) -> Optional[Block]:
        return self.blocks[-1] if self.blocks else None

    @property
    def latest_block_hash(self) -> str:
        return self.latest_block.block_hash if self.latest_block else ZERO_PREV_HASH


class VolyaLedger:
    """Реестр и исполнитель транзакций Proof-of-Harmony."""

    def __init__(self, state: Optional[VolyaState] = None) -> None:
        self.state = state or VolyaState()

    @classmethod
    def init_with_genesis(cls) -> tuple[VolyaLedger, Block, dict[str, Any]]:
        """Инициализация реестра с каноническим Генезис-Блоком №0."""
        ledger = cls()
        genesis_block, keypairs = build_genesis_block()
        ledger.apply_block(genesis_block)
        return ledger, genesis_block, keypairs

    def apply_block(self, block: Block) -> None:
        """Валидация и применение кристаллизованного блока к состоянию узла."""
        # 1. Проверка индекса
        expected_index = len(self.state.blocks)
        if block.index != expected_index:
            raise LedgerValidationError(
                f"Неверный индекс блока: ожидался {expected_index}, получен {block.index}"
            )

        # 2. Проверка хэша предыдущего блока
        expected_prev_hash = self.state.latest_block_hash
        if block.prev_block_hash != expected_prev_hash:
            raise LedgerValidationError(
                f"Несоответствие prev_block_hash: ожидался {expected_prev_hash}, получен {block.prev_block_hash}"
            )

        # 3. Проверка Blake3-хэша самого блока
        block_content = {
            "index": block.index,
            "prev_block_hash": block.prev_block_hash,
            "timestamp": block.timestamp,
            "transactions": [tx.model_dump() for tx in block.transactions],
        }
        computed_hash = hash_canonical(block_content)
        if block.block_hash != computed_hash:
            raise LedgerValidationError(
                f"Искажён хэш блока №{block.index}: вычислен {computed_hash}, в блоке {block.block_hash}"
            )

        # 4. Проверка подписей согласия Proof-of-Harmony под блоком
        if not block.harmony_signatures:
            raise LedgerValidationError(f"Блок №{block.index} не скреплен подписями согласия Proof-of-Harmony!")

        for sig_entry in block.harmony_signatures:
            if not verify_signature(sig_entry.pubkey, block.block_hash.encode("utf-8"), sig_entry.signature):
                raise LedgerValidationError(
                    f"Подпись согласия игрока {sig_entry.pubkey[:12]} под блоком №{block.index} недействительна!"
                )

        # 5. Применение транзакций блока
        for tx in block.transactions:
            self._apply_transaction(tx, is_genesis=(block.index == 0))

        # 6. Добавление блока в неизменяемый журнал
        self.state.blocks.append(block)

    def _apply_transaction(self, tx: Transaction, is_genesis: bool = False) -> None:
        """Применение одной транзакции к состоянию."""
        # Проверка целостности транзакции
        tx_body = {
            "tx_type": tx.tx_type.value,
            "sender_pubkey": tx.sender_pubkey,
            "payload": tx.payload,
            "created_at": tx.created_at,
        }
        # Если id не совпадает с каноническим хэшем
        if tx.id != hash_canonical(tx.payload):
            # В некоторых транзакциях id считается от payload, проверим
            pass

        # Проверка подписи отправителя
        sender_signed = any(
            sig.pubkey == tx.sender_pubkey and verify_canonical(tx.sender_pubkey, tx.payload, sig.signature)
            for sig in tx.signatures
        )
        if not sender_signed:
            raise LedgerValidationError(
                f"Транзакция {tx.id[:12]} типа {tx.tx_type.value} не подписана отправителем {tx.sender_pubkey[:12]}!"
            )

        handler = getattr(self, f"_apply_{tx.tx_type.value.lower()}", None)
        if not handler:
            raise LedgerValidationError(f"Неизвестный тип транзакции: {tx.tx_type}")

        handler(tx, is_genesis=is_genesis)

    # -----------------------------------------------------------------
    # Обработчики конкретных типов волеизъявлений
    # -----------------------------------------------------------------

    def _apply_update_kon(self, tx: Transaction, is_genesis: bool) -> None:
        """Обновление или первородное утверждение Лестницы / Кона."""
        if "steps" in tx.payload:
            # Утверждение Лестницы Совести
            steps = [ConscienceStep(**s) for s in tx.payload["steps"]]
            self.state.ladder = steps

    def _apply_create_player(self, tx: Transaction, is_genesis: bool) -> None:
        """Рождение нового вольного игрока."""
        player = Player(**tx.payload)
        if player.pubkey in self.state.players and not is_genesis:
            raise LedgerValidationError(f"Игрок с открытым ключом {player.pubkey} уже зарегистрирован!")
        self.state.players[player.pubkey] = player

    def _apply_create_quest(self, tx: Transaction, is_genesis: bool) -> None:
        """Появление новой ветви Живого Древа."""
        quest = Quest(**tx.payload)

        # Проверка правила ствола корня
        if quest.parent_quest_id is None and not is_genesis:
            raise LedgerValidationError(
                "Только первородный квест «Воля» в Генезис-Блоке №0 имеет право на parent_quest_id = None!"
            )

        if quest.parent_quest_id is not None and quest.parent_quest_id not in self.state.quests:
            raise LedgerValidationError(
                f"Родительский квест {quest.parent_quest_id} не найден в Живом Древе!"
            )

        # Проверка Владельца квеста (должен обладать ступенью «Владение»)
        if not is_genesis:
            owner = self.state.players.get(quest.owner_pubkey)
            if not owner:
                raise LedgerValidationError(f"Владелец квеста {quest.owner_pubkey} не зарегистрирован!")
            owner_step = determine_step_by_drops(owner.conscience_drops)
            if owner_step.name != StepName.MASTERY:
                raise LedgerValidationError(
                    f"Роль Владельца квеста требует опыта ступени «Владение» "
                    f"({get_step_definition(StepName.MASTERY).min_required_drops} капель совести)! "
                    f"У игрока {owner.username} сейчас {owner.conscience_drops} капель ({owner_step.title})."
                )

        self.state.quests[quest.id] = quest

    def _apply_join_quest(self, tx: Transaction, is_genesis: bool) -> None:
        """Вход игрока в квест на выбранную роль."""
        quest_id = tx.payload["quest_id"]
        role_title = tx.payload["role_title"]
        player_pubkey = tx.sender_pubkey

        quest = self.state.quests.get(quest_id)
        if not quest:
            raise LedgerValidationError(f"Квест {quest_id} не найден!")

        player = self.state.players.get(player_pubkey)
        if not player:
            raise LedgerValidationError(f"Игрок {player_pubkey} не найден!")

        # Поиск роли внутри Кона квеста
        target_role = next((r for r in quest.kon.roles if r.title == role_title), None)
        if not target_role:
            raise LedgerValidationError(f"Роль «{role_title}» не найдена в Коне квеста «{quest.title}»!")

        # ПРОВЕРКА СООТВЕТСТВИЯ СТУПЕНИ РОЛИ ОПЫТУ СОВЕСТИ ИГРОКА!
        required_step = get_step_definition(target_role.step)
        if player.conscience_drops < required_step.min_required_drops:
            raise LedgerValidationError(
                f"Для роли «{role_title}» необходим опыт ступени «{required_step.title}» "
                f"(минимум {required_step.min_required_drops} капель совести). "
                f"У игрока {player.username} сейчас {player.conscience_drops} капель."
            )

        # Добавление в участники
        joined_at = tx.created_at
        quest.participants.append(
            Participant(
                username=player.username,
                pubkey=player.pubkey,
                role_title=role_title,
                joined_at=joined_at,
            )
        )

    def _apply_daily_harmony_pulse(self, tx: Transaction, is_genesis: bool) -> None:
        """
        Суточный пульс лада в непрерывном квесте:
        Каждый участник получает daily_reward_drops согласно СТУПЕНИ СВОЕЙ РОЛИ в этом квесте!
        """
        quest_id = tx.payload["quest_id"]
        quest = self.state.quests.get(quest_id)
        if not quest:
            raise LedgerValidationError(f"Квест {quest_id} не найден!")

        if quest.quest_type != "Непрерывный":
            raise LedgerValidationError(f"Квест «{quest.title}» не является непрерывным!")

        # Начисление совести каждому участнику по ступени его роли
        roles_by_title = {r.title: r for r in quest.kon.roles}
        for participant in quest.participants:
            role = roles_by_title.get(participant.role_title)
            if not role:
                continue
            step_def = get_step_definition(role.step)
            player = self.state.players.get(participant.pubkey)
            if player:
                player.conscience_drops += step_def.daily_reward_drops
                player.step = determine_step_by_drops(player.conscience_drops).name

    def _apply_finish_quest(self, tx: Transaction, is_genesis: bool) -> None:
        """Завершение стандартного квеста: начисление единовременной награды совести за роль."""
        quest_id = tx.payload["quest_id"]
        quest = self.state.quests.get(quest_id)
        if not quest:
            raise LedgerValidationError(f"Квест {quest_id} не найден!")

        quest.finished_at = tx.created_at
        roles_by_title = {r.title: r for r in quest.kon.roles}
        for participant in quest.participants:
            role = roles_by_title.get(participant.role_title)
            if not role:
                continue
            step_def = get_step_definition(role.step)
            player = self.state.players.get(participant.pubkey)
            if player:
                player.conscience_drops += step_def.reward_drops
                player.step = determine_step_by_drops(player.conscience_drops).name

    def _apply_transfer_artifact(self, tx: Transaction, is_genesis: bool) -> None:
        """Передача Артефакта от одного игрока другому по согласию."""
        artifact_id = tx.payload["artifact_id"]
        new_owner_pubkey = tx.payload["new_owner_pubkey"]

        new_owner = self.state.players.get(new_owner_pubkey)
        if not new_owner:
            raise LedgerValidationError(f"Получатель артефакта {new_owner_pubkey} не найден!")

        old_owner = self.state.players.get(tx.sender_pubkey)
        if not old_owner:
            raise LedgerValidationError(f"Владелец артефакта {tx.sender_pubkey} не найден!")

        # Поиск артефакта
        art_idx = next((i for i, a in enumerate(old_owner.artifacts) if a.id == artifact_id), None)
        if art_idx is None:
            raise LedgerValidationError(f"Артефакт {artifact_id} не найден у игрока {old_owner.username}!")

        artifact = old_owner.artifacts.pop(art_idx)
        artifact.owner_pubkey = new_owner_pubkey
        new_owner.artifacts.append(artifact)

    def _apply_create_artifact(self, tx: Transaction, is_genesis: bool) -> None:
        """Рождение нового Плода Души (Артефакта) мастером."""
        artifact = Artifact(**tx.payload)
        creator = self.state.players.get(artifact.creator_pubkey)
        if not creator:
            raise LedgerValidationError(f"Создатель артефакта {artifact.creator_pubkey} не найден!")
        if artifact.creator_pubkey != tx.sender_pubkey:
            raise LedgerValidationError("Создателем артефакта может быть только отправитель транзакции!")
        if artifact.id in self.state.artifacts:
            raise LedgerValidationError(f"Артефакт с id {artifact.id} уже существует!")

        self.state.artifacts[artifact.id] = artifact
        creator.artifacts.append(artifact)

    def _apply_leave_quest(self, tx: Transaction, is_genesis: bool) -> None:
        """Выход игрока из квеста по доброй воле."""
        quest_id = tx.payload["quest_id"]
        quest = self.state.quests.get(quest_id)
        if not quest:
            raise LedgerValidationError(f"Квест {quest_id} не найден!")
        quest.participants = [p for p in quest.participants if p.pubkey != tx.sender_pubkey]

    def _apply_record_discord(self, tx: Transaction, is_genesis: bool) -> None:
        """Фиксация разлада по совести / Вече (убыль капель совести)."""
        player_pubkey = tx.payload["player_pubkey"]
        drops_to_deduct = tx.payload["drops"]
        player = self.state.players.get(player_pubkey)
        if not player:
            raise LedgerValidationError(f"Игрок {player_pubkey} не найден!")
        player.conscience_drops = max(0, player.conscience_drops - drops_to_deduct)
        player.step = determine_step_by_drops(player.conscience_drops).name

    def _apply_append_flow_messages(self, tx: Transaction, is_genesis: bool) -> None:
        """Запечатывание открытых сообщений потока в квесте."""
        flow_id = tx.payload["flow_id"]
        flow = self.state.flows.get(flow_id)
        if not flow:
            # Создание потока, если это первое сообщение
            flow = QuestFlow(
                id=flow_id,
                quest_id=tx.payload.get("quest_id"),
                kind=tx.payload.get("kind", "Беседа"),
                title=tx.payload.get("title", "Поток созидания"),
                initiator_pubkey=tx.sender_pubkey,
                participants=tx.payload.get("participants", [tx.sender_pubkey]),
                created_at=tx.created_at,
                updated_at=tx.created_at,
            )
            self.state.flows[flow_id] = flow

        new_messages = [FlowMessage(**m) for m in tx.payload.get("messages", [])]
        flow.messages.extend(new_messages)
        flow.updated_at = tx.created_at


# =====================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ФОРМИРОВАНИЯ ТРАНЗАКЦИЙ И БЛОКОВ
# =====================================================================

def create_transaction(
    tx_type: TransactionType,
    sender: KeyPair,
    payload: dict[str, Any],
    timestamp: str,
    additional_signers: list[KeyPair] | None = None,
) -> Transaction:
    """Создание и подписание канонической транзакции волеизъявления вольного игрока."""
    tx_id = hash_canonical(payload)
    signatures = [
        SignatureEntry(
            pubkey=sender.public_hex,
            signature=sender.sign_canonical(payload),
        )
    ]
    if additional_signers:
        for signer in additional_signers:
            signatures.append(
                SignatureEntry(
                    pubkey=signer.public_hex,
                    signature=signer.sign_canonical(payload),
                )
            )
    return Transaction(
        id=tx_id,
        tx_type=tx_type,
        sender_pubkey=sender.public_hex,
        payload=payload,
        created_at=timestamp,
        signatures=signatures,
    )


def forge_block(
    index: int,
    prev_block_hash: str,
    timestamp: str,
    transactions: list[Transaction],
    signers: list[KeyPair],
) -> Block:
    """Кристаллизация и скрепление подписями согласия нового блока Proof-of-Harmony."""
    block_content = {
        "index": index,
        "prev_block_hash": prev_block_hash,
        "timestamp": timestamp,
        "transactions": [tx.model_dump() for tx in transactions],
    }
    block_hash = hash_canonical(block_content)
    harmony_signatures = [
        SignatureEntry(
            pubkey=signer.public_hex,
            signature=signer.sign(block_hash.encode("utf-8")),
        )
        for signer in signers
    ]
    return Block(
        index=index,
        prev_block_hash=prev_block_hash,
        block_hash=block_hash,
        timestamp=timestamp,
        transactions=transactions,
        harmony_signatures=harmony_signatures,
    )
