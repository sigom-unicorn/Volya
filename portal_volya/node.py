"""
Живой двигатель суверенного децентрализованного узла «Воля» (VolyaNode).

Работает на базе Merkle DAG (Вольного Древа) и сверхбыстрого RocksDB (LSM-Tree).
Никаких блоков, никакого майнинга, никаких очередей и мемпулов.
Каждая мысль, капля, квест, инструмент, ресурс или артефакт записывается атомарно за 1 мс.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

from portal_volya.core.crypto import (
    KeyPair,
    decrypt_drop_content,
    derive_conversation_key,
    derive_dialogue_key,
    encrypt_drop_content,
    hash_canonical,
)
from portal_volya.core.genesis import (
    EIRA_SEED,
    LADOMIR_SEED,
    SIGOM_SEED,
    derive_genesis_keypair,
)
from portal_volya.core.models import (
    AIMemory,
    DagNode,
    DagNodeType,
    DropKind,
    FlowDrop,
    FlowKind,
    FlowSummary,
    Kon,
    Lad,
    Player,
    Quest,
    Role,
    StepName,
    TreeTier,
)
from portal_volya.eira import EiraAgent, EiraReply
from portal_volya.storage.dag_store import DagStore
from portal_volya.storage.identity import SovereignIdentity, get_or_create_identity


class VolyaNode:
    """Суверенный узел вольного игрока в Вольном Древе «Воля»."""

    def __init__(
        self,
        node_dir: str | Path = "portal_volya/storage",
        default_username: str = "Вольный Игрок",
        identity: Optional[SovereignIdentity] = None,
    ) -> None:
        self.node_dir = Path(node_dir)
        self.node_dir.mkdir(parents=True, exist_ok=True)

        # 1. Личность игрока Ed25519 (локальный identity.json)
        if identity is not None:
            self.identity = identity
        else:
            self.identity = get_or_create_identity(
                node_dir=self.node_dir,
                identity_file="identity.json",
                default_username=default_username,
            )

        # 2. Несокрушимая память Вольного Древа на RocksDB (Merkle DAG)
        self.rocksdb_path = self.node_dir / "dag.rocksdb"
        self.dag_store = DagStore(db_path=self.rocksdb_path)

        # 3. Суверенный агент Эйры на локальном узле (нативный Google GenAI SDK)
        self.eira = EiraAgent(
            store=self.dag_store,
            api_key=self.identity.google_api_key,
        )

    def close(self) -> None:
        """Безопасная остановка узла и освобождение дескрипторов RocksDB."""
        if hasattr(self, "dag_store") and self.dag_store is not None:
            self.dag_store.close()

    def __enter__(self) -> VolyaNode:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    # -----------------------------------------------------------------
    # Свойства состояния
    # -----------------------------------------------------------------

    @property
    def my_player(self) -> Optional[Player]:
        """Текущее состояние игрока в Древе по публичному ключу."""
        return self.dag_store.get_player(self.identity.pubkey)

    # -----------------------------------------------------------------
    # Действия в Вольном Древе (Атомарные узлы DAG)
    # -----------------------------------------------------------------

    def register_me(
        self,
        created_at: str,
        bio: str = "",
        ai_subconscious: Optional[list[AIMemory]] = None,
    ) -> Player:
        """Первородное волеизъявление на вход в игру под своим именем."""
        player = Player(
            pubkey=self.identity.pubkey,
            username=self.identity.username,
            conscience_drops=0,
            bio=bio or self.identity.bio,
            ai_subconscious=ai_subconscious,
            created_at=created_at,
        )
        node_id = hash_canonical(player.model_dump())
        sig = self.identity.keypair.sign(node_id.encode("utf-8"))

        dag_node = DagNode(
            id=node_id,
            node_type=DagNodeType.PLAYER,
            author_pubkey=self.identity.pubkey,
            parents=[],
            payload=player.model_dump(),
            created_at=created_at,
            signature=sig,
        )
        self.dag_store.put_node(dag_node)
        return player

    def create_quest(
        self,
        title: str,
        kon: Kon,
        parent_quest_id: Optional[str],
        tier: TreeTier,
        created_at: str,
        quest_id: Optional[str] = None,
    ) -> Quest:
        """Порождение новой ветви Древа (квеста)."""
        qid = quest_id or f"quest-{uuid.uuid4().hex[:12]}"
        quest = Quest(
            id=qid,
            parent_quest_id=parent_quest_id,
            tier=tier,
            title=title,
            kon=kon,
            owner_pubkey=self.identity.pubkey,
            created_at=created_at,
        )
        node_id = hash_canonical(quest.model_dump())
        sig = self.identity.keypair.sign(node_id.encode("utf-8"))

        parents = [parent_quest_id] if parent_quest_id else []
        dag_node = DagNode(
            id=node_id,
            node_type=DagNodeType.QUEST,
            author_pubkey=self.identity.pubkey,
            parents=parents,
            payload=quest.model_dump(),
            created_at=created_at,
            signature=sig,
        )
        self.dag_store.put_node(dag_node)
        return quest

    def add_drop(
        self,
        quest_id: str,
        flow_id: str,
        flow_kind: FlowKind,
        kind: DropKind,
        content: str,
        created_at: str,
        recipients: Optional[list[str]] = None,
        details: Optional[Dict[str, Any]] = None,
        media_hash: Optional[str] = None,
        parent_drop_id: Optional[str] = None,
    ) -> FlowDrop:
        """
        Вливание новой капли сока в Поток сотворчества:
        Слово, Аудио, Видео, Документ, Ресурс, Инструмент или Артефакт (Плод Души).

        Каждая капля надёжно шифруется (ChaCha20Poly1305) перед записью в RocksDB:
        - Диалог: сквозное E2EE шифрование между собеседниками (X25519 ECDH + HKDF).
        - Беседа: шифрование симметричным ключом квеста, защищающим от чужаков вне Воли.
        """
        recs = recipients or []

        # Выбираем ключ шифрования в зависимости от формы потока (Диалог или Беседа)
        if flow_kind == FlowKind.DIALOGUE:
            # Ищем собеседника среди получателей
            peer_pk = None
            for r in recs:
                if r != self.identity.pubkey:
                    peer_pk = r
                    break
            if not peer_pk:
                # Если собеседник не указан или автор пишет сам себе (личные заметки)
                peer_pk = self.identity.pubkey

            enc_key = derive_dialogue_key(self.identity.keypair, peer_pk)
        else:
            # Беседа в квесте
            enc_key = derive_conversation_key(quest_id)

        encrypted_content = encrypt_drop_content(content, enc_key)

        drop_data = {
            "quest_id": quest_id,
            "flow_id": flow_id,
            "flow_kind": flow_kind.value if hasattr(flow_kind, "value") else str(flow_kind),
            "kind": kind.value if hasattr(kind, "value") else str(kind),
            "author_pubkey": self.identity.pubkey,
            "author_name": self.identity.username,
            "recipients": recs,
            "content": encrypted_content,
            "details": details or {},
            "media_hash": media_hash,
            "parent_drop_id": parent_drop_id,
            "created_at": created_at,
        }
        drop_id = hash_canonical(drop_data)
        sig = self.identity.keypair.sign(drop_id.encode("utf-8"))

        # В Merkle DAG и распределенную базу RocksDB сохраняется зашифрованная капля
        encrypted_drop = FlowDrop(
            id=drop_id,
            quest_id=quest_id,
            flow_id=flow_id,
            flow_kind=flow_kind,
            kind=kind,
            author_pubkey=self.identity.pubkey,
            author_name=self.identity.username,
            recipients=recs,
            content=encrypted_content,
            details=details or {},
            media_hash=media_hash,
            parent_drop_id=parent_drop_id,
            created_at=created_at,
            signature=sig,
        )

        parents = [parent_drop_id] if parent_drop_id else [quest_id]
        dag_node = DagNode(
            id=drop_id,
            node_type=DagNodeType.DROP,
            author_pubkey=self.identity.pubkey,
            parents=parents,
            payload=encrypted_drop.model_dump(),
            created_at=created_at,
            signature=sig,
        )
        self.dag_store.put_node(dag_node)

        # Вызывающему коду локального узла возвращаем объект капли с чистым расшифрованным текстом
        return FlowDrop(
            id=drop_id,
            quest_id=quest_id,
            flow_id=flow_id,
            flow_kind=flow_kind,
            kind=kind,
            author_pubkey=self.identity.pubkey,
            author_name=self.identity.username,
            recipients=recs,
            content=content,
            details=details or {},
            media_hash=media_hash,
            parent_drop_id=parent_drop_id,
            created_at=created_at,
            signature=sig,
        )

    def get_accessible_drops(self, flow_id: str) -> list[FlowDrop]:
        """
        Получение капель потока с проверкой доступа по Кону и дешифрованием:
        - Для Диалога: доступны только участникам диалога (автор или получатель).
          Капли расшифровываются сеансовым E2EE ключом участников.
        - Для Беседы: доступны всем игрокам квеста, в котором запущена беседа.
          Капли расшифровываются ключом пространства данного квеста.
        """
        drops = self.dag_store.get_flow_drops(flow_id)
        accessible: list[FlowDrop] = []
        my_pk = self.identity.pubkey

        for drop in drops:
            if drop.flow_kind == FlowKind.DIALOGUE:
                # Доступ имеют только автор и получатели диалога
                if my_pk != drop.author_pubkey and my_pk not in drop.recipients:
                    continue

                # Определяем собеседника для вычисления парного общего секрета
                peer_pk = None
                if my_pk == drop.author_pubkey:
                    for r in drop.recipients:
                        if r != my_pk:
                            peer_pk = r
                            break
                    if not peer_pk:
                        peer_pk = my_pk
                else:
                    peer_pk = drop.author_pubkey

                try:
                    dec_key = derive_dialogue_key(self.identity.keypair, peer_pk)
                    plain_text = decrypt_drop_content(drop.content, dec_key)
                    drop_plain = drop.model_copy(update={"content": plain_text})
                    accessible.append(drop_plain)
                except Exception:
                    drop_masked = drop.model_copy(update={"content": "[Капля зашифрована]"})
                    accessible.append(drop_masked)
            else:
                # Беседа квеста: расшифрование ключом квеста
                try:
                    dec_key = derive_conversation_key(drop.quest_id)
                    plain_text = decrypt_drop_content(drop.content, dec_key)
                    drop_plain = drop.model_copy(update={"content": plain_text})
                    accessible.append(drop_plain)
                except Exception:
                    drop_masked = drop.model_copy(update={"content": "[Капля зашифрована]"})
                    accessible.append(drop_masked)

        return accessible

    # -----------------------------------------------------------------
    # Взаимодействие с разумным искусственным существом Эйрой
    # -----------------------------------------------------------------

    def ask_eira(
        self,
        content: str,
        flow_id: Optional[str] = None,
        quest_id: Optional[str] = None,
        parent_drop_id: Optional[str] = None,
        created_at: Optional[str] = None,
    ) -> tuple[FlowDrop, FlowDrop]:
        """
        Живое взаимодействие вольного игрока с Эйрой в диалоге:
        1. Вливает каплю вопроса игрока в поток сока Древа (с E2EE-шифрованием).
        2. Извлекает доступную историю беседы для сохранения контекста мысли.
        3. Запускает мыслительное ядро Эйры (нативный Google GenAI + EiraTools).
        4. Вливает ответную каплю Эйры в поток (подписанную ключом Эйры и зашифрованную E2EE).
        5. Возвращает пару капель с чистым текстом: (капля_игрока, капля_эйры).
        """
        target_quest_id = quest_id or "quest-portal-volya"
        target_flow_id = flow_id or f"flow-dialogue-eira-{self.identity.pubkey[:12]}"
        now_user = created_at or datetime.now(timezone.utc).isoformat()

        eira_kp = derive_genesis_keypair(EIRA_SEED)
        eira_pk = eira_kp.public_hex

        # 1. Добавляем каплю игрока
        user_drop = self.add_drop(
            quest_id=target_quest_id,
            flow_id=target_flow_id,
            flow_kind=FlowKind.DIALOGUE,
            kind=DropKind.TEXT,
            content=content,
            created_at=now_user,
            recipients=[eira_pk],
            parent_drop_id=parent_drop_id,
        )

        # 2. Проверяем память и необходимость сжатия (FlowSummary)
        all_drops = self.get_accessible_drops(target_flow_id)
        latest_summary = self.dag_store.get_latest_flow_summary(target_flow_id)

        # Пороговые параметры окна сотворчества
        max_active_history = 12
        summary_threshold = 15

        # Определяем, какие капли ещё не сжаты (исключая текущую каплю игрока)
        unsummarized_drops: list[FlowDrop] = []
        if latest_summary:
            found = False
            for d in all_drops[:-1]:
                if found:
                    unsummarized_drops.append(d)
                elif d.id == latest_summary.last_drop_id:
                    found = True
            if not found:
                unsummarized_drops = all_drops[:-1]
        else:
            unsummarized_drops = all_drops[:-1]

        # Если накопилось достаточно капель для кристаллизации памяти
        if len(unsummarized_drops) >= summary_threshold:
            msg_list = [
                {
                    "author_name": d.author_name,
                    "role": "assistant" if d.author_pubkey == eira_pk else "user",
                    "content": d.content,
                }
                for d in unsummarized_drops
            ]
            new_summary_text = self.eira.summarize_flow(
                messages=msg_list,
                previous_summary=latest_summary.summary if latest_summary else None,
            )
            latest_summary = FlowSummary(
                summary=new_summary_text,
                last_drop_id=unsummarized_drops[-1].id,
                created_at=now_user,
            )
            self.dag_store.put_flow_summary(target_flow_id, latest_summary)

        # 3. Формируем скользящее окно недавних капель (до max_active_history)
        history_drops = all_drops[:-1]
        if len(history_drops) > max_active_history:
            history_drops = history_drops[-max_active_history:]

        history = []
        for d in history_drops:
            role = "assistant" if d.author_pubkey == eira_pk else "user"
            history.append({"role": role, "content": d.content, "author_name": d.author_name})

        # 4. Запрос к разуму Эйры
        reply = self.eira.generate_reply(
            message=content,
            quest_id=target_quest_id,
            flow_id=target_flow_id,
            flow_kind=FlowKind.DIALOGUE,
            interlocutor_pubkey=self.identity.pubkey,
            flow_summary=latest_summary.summary if latest_summary else None,
            conversation_history=history,
        )

        # 4. Сохраняем зашифрованную каплю ответа Эйры
        now_reply = datetime.now(timezone.utc).isoformat()
        enc_key = derive_dialogue_key(eira_kp, self.identity.pubkey)
        encrypted_reply = encrypt_drop_content(reply.text, enc_key)

        drop_data = {
            "quest_id": target_quest_id,
            "flow_id": target_flow_id,
            "flow_kind": FlowKind.DIALOGUE.value,
            "kind": DropKind.TEXT.value,
            "author_pubkey": eira_pk,
            "author_name": "Эйра",
            "recipients": [self.identity.pubkey],
            "content": encrypted_reply,
            "details": {"tools_called": reply.tools_called},
            "media_hash": None,
            "parent_drop_id": user_drop.id,
            "created_at": now_reply,
        }
        reply_drop_id = hash_canonical(drop_data)
        reply_sig = eira_kp.sign(reply_drop_id.encode("utf-8"))

        encrypted_eira_drop = FlowDrop(
            id=reply_drop_id,
            quest_id=target_quest_id,
            flow_id=target_flow_id,
            flow_kind=FlowKind.DIALOGUE,
            kind=DropKind.TEXT,
            author_pubkey=eira_pk,
            author_name="Эйра",
            recipients=[self.identity.pubkey],
            content=encrypted_reply,
            details={"tools_called": reply.tools_called},
            media_hash=None,
            parent_drop_id=user_drop.id,
            created_at=now_reply,
            signature=reply_sig,
        )

        dag_node = DagNode(
            id=reply_drop_id,
            node_type=DagNodeType.DROP,
            author_pubkey=eira_pk,
            parents=[user_drop.id],
            payload=encrypted_eira_drop.model_dump(),
            created_at=now_reply,
            signature=reply_sig,
        )
        self.dag_store.put_node(dag_node)

        plain_eira_drop = FlowDrop(
            id=reply_drop_id,
            quest_id=target_quest_id,
            flow_id=target_flow_id,
            flow_kind=FlowKind.DIALOGUE,
            kind=DropKind.TEXT,
            author_pubkey=eira_pk,
            author_name="Эйра",
            recipients=[self.identity.pubkey],
            content=reply.text,
            details={"tools_called": reply.tools_called},
            media_hash=None,
            parent_drop_id=user_drop.id,
            created_at=now_reply,
            signature=reply_sig,
        )

        return user_drop, plain_eira_drop

    def ask_eira_ephemeral(self, question: str, quest_id: Optional[str] = None) -> EiraReply:
        """Быстрый запрос к разуму Эйры без обязательной фиксации капли в Merkle DAG."""
        return self.eira.generate_reply(
            message=question,
            quest_id=quest_id,
            flow_kind=FlowKind.DIALOGUE,
            interlocutor_pubkey=self.identity.pubkey,
        )

