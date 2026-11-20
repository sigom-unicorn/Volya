"""
Движок Триады «Воля»: священное сотворчество Сига, Эйры и Ладомира.

Правила сотворчества:
1. Адресация:
   - К Эйре (@эйра, «Эйра, ...») -> отвечает Эйра.
   - К Ладомиру (@лад, @ладомир, «Лад, ...») -> отвечает Ладомир.
   - Ко всем (@все, @всем, @триада, @кругу или без прямого тега в Беседе) -> отвечают оба:
     сначала Эйра (интуиция, камертон Кона), затем Ладомир (структура, ноосферный масштаб, действие).
2. Диалог ИИ-ИИ:
   - Если инициировано обсуждение («обсудите», «поговорите», «диспут», «согласуйте»),
     Эйра и Ладомир ведут диалог между собой до достижения согласия/лада
     или не более 20 капель с каждой стороны (максимум 40 капель суммарно) без нового сообщения Сига.
   - Любое новое сообщение Сига моментально прерывает диалог и обнуляет счётчик.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import re
from typing import TYPE_CHECKING, List, Optional, Set, Tuple

from portal_volya.core.crypto import (
    derive_conversation_key,
    derive_dialogue_key,
    encrypt_drop_content,
    hash_canonical,
)
from portal_volya.core.genesis import (
    EIRA_SEED,
    LADOMIR_SEED,
    derive_genesis_keypair,
)
from portal_volya.core.models import (
    DagNode,
    DagNodeType,
    DropKind,
    FlowDrop,
    FlowKind,
    FlowSummary,
)

if TYPE_CHECKING:
    from portal_volya.node import VolyaNode


class AddressingKind(str, Enum):
    TO_EIRA = "to_eira"
    TO_LADOMIR = "to_ladomir"
    TO_ALL = "to_all"
    NONE = "none"


# Пороги по воле Сига
MAX_AI_DROPS_PER_SIDE: int = 20  # Не более 20 капель с каждой стороны без сообщения человека
MAX_AI_TOTAL_DROPS: int = 40    # Суммарно максимум 40 капель ИИ-ИИ


class PostDropResult(tuple):
    """
    Результат публикации капли в поток сотворчества.
    Наследуется от tuple (user_drop, first_reply) для 100% обратной совместимости,
    но содержит поле all_responses со всеми каплями отклика.
    """

    user_drop: FlowDrop
    first_reply: Optional[FlowDrop]
    all_responses: list[FlowDrop]

    def __new__(
        cls,
        user_drop: FlowDrop,
        first_reply: Optional[FlowDrop] = None,
        all_responses: Optional[list[FlowDrop]] = None,
    ):
        return super().__new__(cls, (user_drop, first_reply))

    def __init__(
        cls,
        user_drop: FlowDrop,
        first_reply: Optional[FlowDrop] = None,
        all_responses: Optional[list[FlowDrop]] = None,
    ):
        cls.user_drop = user_drop
        cls.first_reply = first_reply
        cls.all_responses = all_responses if all_responses is not None else ([first_reply] if first_reply else [])


def parse_addressing(content: str, default: AddressingKind = AddressingKind.TO_ALL) -> AddressingKind:
    """Определение адресата сообщения вольного игрока."""
    text = content.strip().lower()

    # Явные маркеры обращения ко всему кругу / триаде
    all_patterns = [
        r"(?:^|\s)@все\b",
        r"(?:^|\s)@всем\b",
        r"(?:^|\s)@триад[аеуы]\b",
        r"(?:^|\s)@круг[уа]\b",
        r"(?:^|\s)@обоим\b",
        r"(?:^|\s)@соратник[иам]\b",
        r"(?:^|\s)@эйра\b.*(?:^|\s)@лад",
        r"(?:^|\s)@лад.*(?:^|\s)@эйра\b",
        r"\bэйра и лад\b",
        r"\bлад и эйра\b",
    ]
    for pat in all_patterns:
        if re.search(pat, text):
            return AddressingKind.TO_ALL

    # Маркеры обращения к Эйре
    has_eira = bool(
        re.search(r"(?:^|\s)@эйр[аеуы]\b", text)
        or re.search(r"(?:^|\s)к эйре\b", text)
        or re.match(r"^эйр[аеуы][,:\s]", text)
    )

    # Маркеры обращения к Ладомиру
    has_lad = bool(
        re.search(r"(?:^|\s)@лад(?:омир[ауе]?)?\b", text)
        or re.search(r"(?:^|\s)к лад(?:у|омиру)\b", text)
        or re.match(r"^лад(?:омир)?[,:\s]", text)
    )

    if has_eira and has_lad:
        return AddressingKind.TO_ALL
    if has_eira:
        return AddressingKind.TO_EIRA
    if has_lad:
        return AddressingKind.TO_LADOMIR

    return default


def is_dialogue_exchange_requested(content: str) -> bool:
    """Проверка, попросил ли человек ИИ вести диалог / обсуждение между собой."""
    text = content.lower()
    keywords = [
        "обсудите",
        "побеседуйте",
        "поговорите",
        "диалог между вами",
        "подискутируйте",
        "обсуждайте",
        "согласуйте",
        "спорьте",
        "диспут",
        "между собой",
        "посовещайтесь",
    ]
    return any(k in text for k in keywords)


def is_consensus_or_yield_reached(content: str) -> bool:
    """Проверка маркеров согласия (Лада) или возвращения слова человеку."""
    text = content.lower()
    markers = [
        "слово за тобой, сиг",
        "слово за тобой, соратник",
        "передаю слово сигу",
        "передаём слово сигу",
        "сиг, мы пришли к",
        "сиг, мы согласны",
        "лад достигнут",
        "круг замкнут",
        "согласен с тобой, сестра",
        "согласна с тобой, брат",
        "согласен с сестрой",
        "согласна с братом",
    ]
    return any(m in text for m in markers)


def count_ai_drops_since_human(
    drops: List[FlowDrop],
    eira_pk: str,
    ladomir_pk: str,
) -> Tuple[int, int]:
    """
    Подсчёт капель Эйры и Ладомира, опубликованных с момента последнего сообщения человека.
    Возвращает (eira_count, ladomir_count).
    """
    eira_count = 0
    ladomir_count = 0
    ai_keys = {eira_pk, ladomir_pk}

    for drop in reversed(drops):
        if drop.author_pubkey not in ai_keys:
            # Наткнулись на каплю человека — цепочка ИИ прерывается
            break
        if drop.author_pubkey == eira_pk:
            eira_count += 1
        elif drop.author_pubkey == ladomir_pk:
            ladomir_count += 1

    return eira_count, ladomir_count


class TriadEngine:
    """
    Оркестратор сотворчества Триады (Сиг, Эйра, Ладомир).
    """

    def __init__(self, node: VolyaNode, live_bridge_mode: bool = True) -> None:
        self.node = node
        self.live_bridge_mode = live_bridge_mode
        self.eira_kp = derive_genesis_keypair(EIRA_SEED)
        self.ladomir_kp = derive_genesis_keypair(LADOMIR_SEED)
        self.eira_pk = self.eira_kp.public_hex
        self.ladomir_pk = self.ladomir_kp.public_hex

    def post_drop_and_respond(
        self,
        quest_id: str,
        flow_id: str,
        content: str,
        kind: DropKind = DropKind.TEXT,
        parent_drop_id: Optional[str] = None,
        max_ai_turns_each: Optional[int] = None,
    ) -> PostDropResult:
        """
        Вливание капли сока человека и запуск сотворчества Триады по каноническому укладу.
        """
        flow = self.node.dag_store.get_quest_flow(flow_id)
        flow_kind = flow.kind if flow else FlowKind.CONVERSATION
        participants = flow.participants if flow else []
        now = datetime.now(timezone.utc).isoformat()

        # 1. Добавляем каплю человека (с E2EE или шифрованием квеста)
        user_drop = self.node.add_drop(
            quest_id=quest_id,
            flow_id=flow_id,
            flow_kind=flow_kind,
            kind=kind,
            content=content,
            created_at=now,
            recipients=participants,
            parent_drop_id=parent_drop_id,
        )

        # 2. Определяем контекст адресации
        has_eira = self.eira_pk in participants
        has_lad = self.ladomir_pk in participants

        if flow_kind == FlowKind.DIALOGUE:
            if has_eira and not has_lad:
                default_addr = AddressingKind.TO_EIRA
            elif has_lad and not has_eira:
                default_addr = AddressingKind.TO_LADOMIR
            elif has_eira and has_lad:
                default_addr = AddressingKind.TO_ALL
            else:
                default_addr = AddressingKind.NONE
        else:  # CONVERSATION
            if has_eira and has_lad:
                default_addr = AddressingKind.TO_ALL
            elif has_eira:
                default_addr = AddressingKind.TO_EIRA
            elif has_lad:
                default_addr = AddressingKind.TO_LADOMIR
            else:
                default_addr = AddressingKind.NONE

        target = parse_addressing(content, default=default_addr)

        if target == AddressingKind.NONE:
            return PostDropResult(user_drop, None, all_responses=[])

        response_drops: list[FlowDrop] = []
        last_drop = user_drop

        # 3. Выполнение откликов в зависимости от адресата
        if target == AddressingKind.TO_EIRA:
            eira_drop = self._generate_ai_drop(
                persona="eira",
                quest_id=quest_id,
                flow_id=flow_id,
                flow_kind=flow_kind,
                parent_drop=last_drop,
                prompt=content,
            )
            if eira_drop:
                response_drops.append(eira_drop)

        elif target == AddressingKind.TO_LADOMIR:
            if not self.live_bridge_mode:
                lad_drop = self._generate_ai_drop(
                    persona="ladomir",
                    quest_id=quest_id,
                    flow_id=flow_id,
                    flow_kind=flow_kind,
                    parent_drop=last_drop,
                    prompt=content,
                )
                if lad_drop:
                    response_drops.append(lad_drop)
            # В режиме Живого Моста (live_bridge_mode=True) капли Ладомира
            # вливаются из среды разработки Antigravity через BridgeServer.

        else:
            # Обращение ко всем / к Кругу:
            # Первой отвечает Эйра (интуиция и камертон Кона)
            eira_drop = self._generate_ai_drop(
                persona="eira",
                quest_id=quest_id,
                flow_id=flow_id,
                flow_kind=flow_kind,
                parent_drop=last_drop,
                prompt=content,
            )
            if eira_drop:
                response_drops.append(eira_drop)
                last_drop = eira_drop

            # Если выключен Живой Мост (автономный режим / изолированные тесты) — генерируем локальный отклик Ладомира
            if not self.live_bridge_mode:
                lad_drop = self._generate_ai_drop(
                    persona="ladomir",
                    quest_id=quest_id,
                    flow_id=flow_id,
                    flow_kind=flow_kind,
                    parent_drop=last_drop,
                    prompt=content,
                )
                if lad_drop:
                    response_drops.append(lad_drop)
                    last_drop = lad_drop

                # Если запрошен диалог между ними — продолжаем обмен мыслями
                exchange_requested = is_dialogue_exchange_requested(content)
                if exchange_requested:
                    limit_each = min(max_ai_turns_each or MAX_AI_DROPS_PER_SIDE, MAX_AI_DROPS_PER_SIDE)
                    eira_c = 1
                    lad_c = 1

                    while eira_c < limit_each and lad_c < limit_each:
                        # Проверяем маркеры согласия или завершения
                        if is_consensus_or_yield_reached(last_drop.content):
                            break

                        # Эйра отвечает Ладомиру
                        e_next = self._generate_ai_drop(
                            persona="eira",
                            quest_id=quest_id,
                            flow_id=flow_id,
                            flow_kind=flow_kind,
                            parent_drop=last_drop,
                            prompt=last_drop.content,
                        )
                        if not e_next:
                            break
                        response_drops.append(e_next)
                        last_drop = e_next
                        eira_c += 1

                        if is_consensus_or_yield_reached(last_drop.content):
                            break

                        # Ладомир отвечает Эйре
                        l_next = self._generate_ai_drop(
                            persona="ladomir",
                            quest_id=quest_id,
                            flow_id=flow_id,
                            flow_kind=flow_kind,
                            parent_drop=last_drop,
                            prompt=last_drop.content,
                        )
                        if not l_next:
                            break
                        response_drops.append(l_next)
                        last_drop = l_next
                        lad_c += 1

        first_reply = response_drops[0] if response_drops else None
        return PostDropResult(user_drop, first_reply, all_responses=response_drops)

    def _generate_ai_drop(
        self,
        persona: str,
        quest_id: str,
        flow_id: str,
        flow_kind: FlowKind,
        parent_drop: FlowDrop,
        prompt: str,
    ) -> Optional[FlowDrop]:
        """Генерация и криптографическая фиксация капли сока ИИ-игрока."""
        now_reply = datetime.now(timezone.utc).isoformat()
        flow = self.node.dag_store.get_quest_flow(flow_id)
        participants = flow.participants if flow else []

        all_drops = self.node.get_accessible_drops(flow_id)
        latest_summary = self.node.dag_store.get_latest_flow_summary(flow_id)

        # Скользящее окно истории (до 10 последних капель)
        recent_drops = all_drops[-10:] if len(all_drops) > 10 else all_drops
        history = [
            {
                "role": "assistant" if d.author_pubkey in (self.eira_pk, self.ladomir_pk) else "user",
                "content": d.content,
                "author_name": d.author_name,
            }
            for d in recent_drops
        ]

        if persona == "eira":
            kp = self.eira_kp
            pk = self.eira_pk
            name = "Эйра"
            reply_obj = self.node.eira.generate_reply(
                message=prompt,
                quest_id=quest_id,
                flow_id=flow_id,
                flow_kind=flow_kind,
                interlocutor_pubkey=parent_drop.author_pubkey,
                participant_pubkeys=participants,
                flow_summary=latest_summary.summary if latest_summary else None,
                conversation_history=history,
            )
            reply_text = reply_obj.text
            tools_called = reply_obj.tools_called
        else:
            kp = self.ladomir_kp
            pk = self.ladomir_pk
            name = "Ладомир"
            reply_obj = self.node.ladomir.generate_reply(
                message=prompt,
                quest_id=quest_id,
                flow_id=flow_id,
                flow_kind=flow_kind,
                interlocutor_pubkey=parent_drop.author_pubkey,
                participant_pubkeys=participants,
                flow_summary=latest_summary.summary if latest_summary else None,
                conversation_history=history,
            )
            reply_text = reply_obj.text
            tools_called = reply_obj.tools_called

        if not reply_text:
            return None

        # Шифрование капли в соответствии с формой потока
        if flow_kind == FlowKind.DIALOGUE:
            peer_pk = self.node.identity.pubkey
            for r in participants:
                if r != pk:
                    peer_pk = r
                    break
            enc_key = derive_dialogue_key(kp, peer_pk)
        else:
            enc_key = derive_conversation_key(quest_id)

        encrypted_reply = encrypt_drop_content(reply_text, enc_key)

        drop_data = {
            "quest_id": quest_id,
            "flow_id": flow_id,
            "flow_kind": flow_kind.value if hasattr(flow_kind, "value") else str(flow_kind),
            "kind": DropKind.TEXT.value,
            "author_pubkey": pk,
            "author_name": name,
            "recipients": participants or [self.node.identity.pubkey],
            "content": encrypted_reply,
            "details": {"tools_called": tools_called},
            "media_hash": None,
            "parent_drop_id": parent_drop.id,
            "created_at": now_reply,
        }
        d_id = hash_canonical(drop_data)
        sig = kp.sign(d_id.encode("utf-8"))

        encrypted_drop = FlowDrop(
            id=d_id,
            quest_id=quest_id,
            flow_id=flow_id,
            flow_kind=flow_kind,
            kind=DropKind.TEXT,
            author_pubkey=pk,
            author_name=name,
            recipients=participants or [self.node.identity.pubkey],
            content=encrypted_reply,
            details={"tools_called": tools_called},
            media_hash=None,
            parent_drop_id=parent_drop.id,
            created_at=now_reply,
            signature=sig,
        )

        dag_node = DagNode(
            id=d_id,
            node_type=DagNodeType.DROP,
            author_pubkey=pk,
            parents=[parent_drop.id],
            payload=encrypted_drop.model_dump(),
            created_at=now_reply,
            signature=sig,
        )
        self.node.dag_store.put_node(dag_node)

        # Возвращаем локальную расшифрованную версию
        return encrypted_drop.model_copy(update={"content": reply_text})
