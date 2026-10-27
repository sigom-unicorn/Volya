"""
Сверхбыстрое локальное хранилище Вольного Древа на базе RocksDB (LSM-Tree) и Merkle DAG.
Каждый узел (квест, капля потока, ресурс, инструмент, артефакт) сохраняется атомарно за доли миллисекунды.
"""

from __future__ import annotations

from datetime import datetime, timezone
import gc
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import ormsgpack
from rocksdict import ColumnFamily, Options, Rdict, WriteBatch

from portal_volya.core.crypto import (
    KeyPair,
    hash_bytes,
    hash_canonical,
    verify_signature,
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
    PlayerRoleAssignment,
    Quest,
    Role,
    StepName,
)

# Имена колоночных семейств в RocksDB
CF_NODES = "dag_nodes"          # node_id (32b) -> binary DagNode
CF_QUESTS = "quests"            # quest_id (32b) -> binary Quest
CF_DROPS = "flow_drops"         # drop_id (32b) -> binary FlowDrop
CF_PLAYERS = "players"          # pubkey (64 hex chars) -> binary Player
CF_TREE_LINKS = "tree_links"    # parent_id -> list of child_ids
CF_FLOW_LINKS = "flow_links"    # flow_id -> list of drop_ids
CF_SUMMARIES = "flow_summaries" # flow_id -> list of FlowSummary dicts
CF_BLOBS = "blobs"              # blob_hash (Blake3) -> binary data (avatars, images)
CF_META = "dag_meta"            # служебные метаданные (root_id, stats)


def _h_bytes(hex_str: str) -> bytes:
    try:
        return bytes.fromhex(hex_str)
    except Exception:
        return hex_str.encode("utf-8")


class DagStore:
    """Несокрушимое локальное хранилище Merkle DAG (Вольного Древа)."""

    def __init__(self, db_path: str | Path = "portal_volya/storage/dag.rocksdb") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        opts = Options()
        opts.create_if_missing(True)
        opts.create_missing_column_families(True)

        cfs = {
            CF_NODES: Options(),
            CF_QUESTS: Options(),
            CF_DROPS: Options(),
            CF_PLAYERS: Options(),
            CF_TREE_LINKS: Options(),
            CF_FLOW_LINKS: Options(),
            CF_SUMMARIES: Options(),
            CF_BLOBS: Options(),
            CF_META: Options(),
        }

        self.db = Rdict(str(self.db_path), options=opts, column_families=cfs)

        self._cf_nodes = self.db.get_column_family(CF_NODES)
        self._cf_quests = self.db.get_column_family(CF_QUESTS)
        self._cf_drops = self.db.get_column_family(CF_DROPS)
        self._cf_players = self.db.get_column_family(CF_PLAYERS)
        self._cf_tree = self.db.get_column_family(CF_TREE_LINKS)
        self._cf_flows = self.db.get_column_family(CF_FLOW_LINKS)
        self._cf_summaries = self.db.get_column_family(CF_SUMMARIES)
        self._cf_blobs = self.db.get_column_family(CF_BLOBS)
        self._cf_meta = self.db.get_column_family(CF_META)

        self._h_nodes = self.db.get_column_family_handle(CF_NODES)
        self._h_quests = self.db.get_column_family_handle(CF_QUESTS)
        self._h_drops = self.db.get_column_family_handle(CF_DROPS)
        self._h_players = self.db.get_column_family_handle(CF_PLAYERS)
        self._h_tree = self.db.get_column_family_handle(CF_TREE_LINKS)
        self._h_flows = self.db.get_column_family_handle(CF_FLOW_LINKS)
        self._h_summaries = self.db.get_column_family_handle(CF_SUMMARIES)
        self._h_blobs = self.db.get_column_family_handle(CF_BLOBS)
        self._h_meta = self.db.get_column_family_handle(CF_META)

        # Автоматическая проверка и очистка дубликатов имён игроков в летописи
        self._deduplicate_players()

    def _deduplicate_players(self) -> None:
        """Очищает устаревшие дубликаты имён игроков, оставляя запись с наибольшим опытом совести."""
        seen: dict[str, Player] = {}
        dups_to_delete: list[str] = []
        for p in self.get_all_players():
            u_lower = p.username.strip().lower()
            if u_lower in seen:
                prev = seen[u_lower]
                if p.conscience_drops >= prev.conscience_drops:
                    dups_to_delete.append(prev.pubkey)
                    seen[u_lower] = p
                else:
                    dups_to_delete.append(p.pubkey)
            else:
                seen[u_lower] = p

        for pk in dups_to_delete:
            self.delete_player(pk)

    def close(self) -> None:
        """Безопасное освобождение дескрипторов C++ RocksDB."""
        if hasattr(self, "db") and self.db is not None:
            try:
                self.db.flush(wait=True)
                self.db.close()
            except Exception:
                pass
            finally:
                self._cf_nodes = None
                self._cf_quests = None
                self._cf_drops = None
                self._cf_players = None
                self._cf_tree = None
                self._cf_flows = None
                self._cf_summaries = None
                self._cf_blobs = None
                self._cf_meta = None
                self._h_nodes = None
                self._h_quests = None
                self._h_drops = None
                self._h_players = None
                self._h_tree = None
                self._h_flows = None
                self._h_summaries = None
                self._h_blobs = None
                self._h_meta = None
                self.db = None
                gc.collect()

    def __enter__(self) -> DagStore:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    # -----------------------------------------------------------------
    # Запись и чтение универсальных узлов DAG
    # -----------------------------------------------------------------

    def put_node(self, node: DagNode) -> None:
        """
        Атомарное сохранение узла в Merkle DAG:
        - Индексация узла в общем каталоге dag_nodes
        - Индексация в предметных колоночных семействах (quests, flow_drops, players)
        - Обновление графа связей (tree_links, flow_links)
        """
        batch = WriteBatch()
        node_key = node.id.encode("utf-8")
        node_bytes = ormsgpack.packb(node.model_dump())

        # 1. Запись узла в общий DAG
        batch.put(node_key, node_bytes, self._h_nodes)

        # 2. Предметная индексация по типу узла
        if node.node_type == DagNodeType.QUEST:
            quest = Quest(**node.payload)
            q_key = quest.id.encode("utf-8")
            batch.put(q_key, ormsgpack.packb(quest.model_dump()), self._h_quests)

            # Обновление связей Древа
            if quest.parent_quest_id:
                p_key = quest.parent_quest_id.encode("utf-8")
                raw_children = self._cf_tree.get(p_key)
                children = ormsgpack.unpackb(raw_children) if raw_children else []
                if quest.id not in children:
                    children.append(quest.id)
                    batch.put(p_key, ormsgpack.packb(children), self._h_tree)

        elif node.node_type == DagNodeType.DROP:
            drop = FlowDrop(**node.payload)
            d_key = drop.id.encode("utf-8")
            batch.put(d_key, ormsgpack.packb(drop.model_dump()), self._h_drops)

            # Обновление стрелы времени потока
            f_key = drop.flow_id.encode("utf-8")
            raw_drops = self._cf_flows.get(f_key)
            drops_list = ormsgpack.unpackb(raw_drops) if raw_drops else []
            if drop.id not in drops_list:
                drops_list.append(drop.id)
                batch.put(f_key, ormsgpack.packb(drops_list), self._h_flows)

        elif node.node_type == DagNodeType.PLAYER:
            player = Player(**node.payload)
            # Обеспечиваем строго уникальное вольное имя игрока
            existing = self.get_player_by_username(player.username)
            if existing and existing.pubkey != player.pubkey:
                raise ValueError(
                    f"К сожалению, имя «{player.username}» уже занято в Игре. Пожалуйста, подберите себе другое вольное имя."
                )
            p_key = player.pubkey.encode("utf-8")
            batch.put(p_key, ormsgpack.packb(player.model_dump()), self._h_players)

        elif node.node_type == DagNodeType.VECHE_RESULT:
            # Согласованное обновление Кона
            quest_id = node.payload.get("quest_id")
            if quest_id:
                quest = self.get_quest(quest_id)
                if quest:
                    quest.kon = Kon(**node.payload.get("new_kon"))
                    q_key = quest.id.encode("utf-8")
                    batch.put(q_key, ormsgpack.packb(quest.model_dump()), self._h_quests)

        self.db.write(batch)

    def get_node(self, node_id: str) -> Optional[DagNode]:
        """Получение узла DAG по его Blake3 хэшу."""
        raw = self._cf_nodes.get(node_id.encode("utf-8"))
        if not raw:
            return None
        return DagNode(**ormsgpack.unpackb(raw))

    # -----------------------------------------------------------------
    # Квесты Вольного Древа
    # -----------------------------------------------------------------

    def get_quest(self, quest_id: str) -> Optional[Quest]:
        raw = self._cf_quests.get(quest_id.encode("utf-8"))
        if not raw:
            return None
        return Quest(**ormsgpack.unpackb(raw))

    def get_all_quests(self) -> list[Quest]:
        quests = []
        for _, raw in self._cf_quests.items():
            quests.append(Quest(**ormsgpack.unpackb(raw)))
        return quests

    def get_child_quests(self, parent_quest_id: str) -> list[Quest]:
        raw = self._cf_tree.get(parent_quest_id.encode("utf-8"))
        if not raw:
            return []
        child_ids = ormsgpack.unpackb(raw)
        children = []
        for cid in child_ids:
            q = self.get_quest(cid)
            if q:
                children.append(q)
        return children

    def count_nodes(self) -> int:
        """Общее число узлов в Merkle DAG."""
        return len(self._cf_nodes)

    # -----------------------------------------------------------------
    # Потоки и Капли
    # -----------------------------------------------------------------

    def get_drop(self, drop_id: str) -> Optional[FlowDrop]:
        raw = self._cf_drops.get(drop_id.encode("utf-8"))
        if not raw:
            return None
        return FlowDrop(**ormsgpack.unpackb(raw))

    def get_flow_drops(self, flow_id: str) -> list[FlowDrop]:
        """Получение всех капель потока в хронологическом порядке."""
        flow_key = flow_id.encode("utf-8")
        raw = self._cf_flows.get(flow_key)
        if not raw:
            return []
        drop_ids = ormsgpack.unpackb(raw)
        drops = []
        for did in drop_ids:
            d = self.get_drop(did)
            if d:
                drops.append(d)
        return drops

    # -----------------------------------------------------------------
    # Смысловые кристаллы памяти потоков (FlowSummary)
    # -----------------------------------------------------------------

    def put_flow_summary(self, flow_id: str, summary: FlowSummary) -> None:
        """Сохранение нового кристалла сжатой памяти потока."""
        flow_key = flow_id.encode("utf-8")
        raw = self._cf_summaries.get(flow_key)
        existing = ormsgpack.unpackb(raw) if raw else []
        existing.append(summary.model_dump())
        self._cf_summaries[flow_key] = ormsgpack.packb(existing)

    def get_flow_summaries(self, flow_id: str) -> list[FlowSummary]:
        """Получение всех кристаллов памяти потока в хронологическом порядке."""
        flow_key = flow_id.encode("utf-8")
        raw = self._cf_summaries.get(flow_key)
        if not raw:
            return []
        items = ormsgpack.unpackb(raw)
        return [FlowSummary(**item) for item in items]

    def get_latest_flow_summary(self, flow_id: str) -> Optional[FlowSummary]:
        """Получение последнего актуального саммари потока."""
        summaries = self.get_flow_summaries(flow_id)
        return summaries[-1] if summaries else None

    # -----------------------------------------------------------------
    # Хранилище блобов (Content-Addressed Storage: аватарки, медиа)
    # -----------------------------------------------------------------

    def put_blob(self, data: bytes) -> str:
        """Сохранение бинарного блоба по его Blake3 хэшу."""
        h = hash_bytes(data)
        self._cf_blobs[h.encode("utf-8")] = data
        return h

    def get_blob(self, blob_hash: str) -> Optional[bytes]:
        """Получение бинарного блоба по его Blake3 хэшу."""
        return self._cf_blobs.get(blob_hash.encode("utf-8"))

    def set_player_avatar(self, pubkey: str, avatar_bytes: bytes) -> str:
        """Сохранение и привязка аватарки игрока в RocksDB."""
        avatar_hash = self.put_blob(avatar_bytes)
        player = self.get_player(pubkey)
        if player:
            player.avatar_hash = avatar_hash
            self.save_player(player)
        return avatar_hash

    def get_player_avatar(self, pubkey: str) -> Optional[bytes]:
        """Получение байтов аватарки игрока из RocksDB."""
        player = self.get_player(pubkey)
        if player and player.avatar_hash:
            return self.get_blob(player.avatar_hash)
        return None

    # -----------------------------------------------------------------
    # Игроки
    # -----------------------------------------------------------------

    def get_player(self, pubkey: str) -> Optional[Player]:
        raw = self._cf_players.get(pubkey.encode("utf-8"))
        if not raw:
            return None
        return Player(**ormsgpack.unpackb(raw))

    def get_all_players(self) -> list[Player]:
        players = []
        for _, raw in self._cf_players.items():
            players.append(Player(**ormsgpack.unpackb(raw)))
        return players

    def save_player(self, player: Player) -> None:
        existing = self.get_player_by_username(player.username)
        if existing and existing.pubkey != player.pubkey:
            raise ValueError(
                f"К сожалению, имя «{player.username}» уже занято в Игре. Пожалуйста, подберите себе другое вольное имя."
            )
        p_key = player.pubkey.encode("utf-8")
        self._cf_players[p_key] = ormsgpack.packb(player.model_dump())

    def delete_player(self, pubkey: str) -> bool:
        """Удаление игрока из индекса (например, при очистке дубликатов)."""
        p_key = pubkey.encode("utf-8")
        if p_key in self._cf_players:
            del self._cf_players[p_key]
            return True
        return False

    def get_player_by_username(self, username: str) -> Optional[Player]:
        """Поиск игрока по вольному имени (без учёта регистра)."""
        target = username.strip().lower()
        for p in self.get_all_players():
            if p.username.strip().lower() == target:
                return p
        return None

    def get_player_by_name_or_pubkey(self, name_or_pubkey: str) -> Optional[Player]:
        """Поиск игрока по публичному ключу или вольному имени (без учёта регистра)."""
        target = name_or_pubkey.strip()
        player = self.get_player(target)
        if player:
            return player
        for p in self.get_all_players():
            if p.username.strip().lower() == target.lower():
                return p
        return None

    def assign_player_role(
        self,
        pubkey: str,
        quest_id: str,
        role_title: str,
        assigned_at: Optional[str] = None,
    ) -> Optional[Player]:
        """Назначение роли игроку в квесте с сохранением в Merkle DAG."""
        player = self.get_player(pubkey)
        if not player:
            return None
        now = assigned_at or datetime.now(timezone.utc).isoformat()
        # Проверяем, назначена ли уже роль
        for r in player.roles:
            if r.quest_id == quest_id and r.role_title == role_title:
                return player
        player.roles.append(
            PlayerRoleAssignment(quest_id=quest_id, role_title=role_title, assigned_at=now)
        )
        self.save_player(player)
        return player

    def add_ai_memory(
        self,
        name_or_pubkey: str,
        content: str,
        tags: Optional[list[str]] = None,
        embedding: Optional[list[float]] = None,
        created_at: Optional[str] = None,
    ) -> Optional[AIMemory]:
        """Добавление инсайта/мысли в подсознание (ai_subconscious) игрока ИИ с сохранением эмбеддинга."""
        player = self.get_player_by_name_or_pubkey(name_or_pubkey)
        if not player:
            return None

        if player.ai_subconscious is None:
            if player.username in ("Эйра", "Ладомир") or "ии" in player.bio.lower():
                player.ai_subconscious = []
            else:
                return None

        clean_content = content.strip()
        if not clean_content:
            return None

        now = created_at or datetime.now(timezone.utc).isoformat()
        tag_list = tags or []
        thought_id = hash_canonical({"content": clean_content, "created_at": now})

        memory = AIMemory(
            id=thought_id,
            content=clean_content,
            tags=tag_list,
            embedding=embedding or [],
            created_at=now,
        )
        player.ai_subconscious.append(memory)
        self.save_player(player)
        return memory

    def search_ai_memories_by_embedding(
        self,
        name_or_pubkey: str,
        query_embedding: list[float],
        min_similarity: float = 0.3,
        limit: int = 5,
    ) -> list[tuple[AIMemory, float]]:
        """
        Семантический поиск ассоциаций в подсознании по вектору смыслового пространства (косинусное сходство).
        Возвращает список пар (AIMemory, similarity_score), отсортированный по убыванию сродства.
        """
        player = self.get_player_by_name_or_pubkey(name_or_pubkey)
        if not player or not player.ai_subconscious or not query_embedding:
            return []

        q_vec = np.array(query_embedding, dtype=np.float32)
        q_norm = float(np.linalg.norm(q_vec))
        if q_norm == 0.0:
            return []

        scored: list[tuple[AIMemory, float]] = []
        for mem in player.ai_subconscious:
            if not mem.embedding or len(mem.embedding) != len(query_embedding):
                continue
            m_vec = np.array(mem.embedding, dtype=np.float32)
            m_norm = float(np.linalg.norm(m_vec))
            if m_norm == 0.0:
                continue
            sim = float(np.dot(q_vec, m_vec) / (q_norm * m_norm))
            if sim >= min_similarity:
                scored.append((mem, sim))

        # Сортируем по убыванию смыслового сродства
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:limit]

    def get_ai_memories(
        self,
        name_or_pubkey: str,
        tag: Optional[str] = None,
        query: Optional[str] = None,
    ) -> Optional[list[AIMemory]]:
        """Получение инсайтов из подсознания игрока ИИ с опциональной фильтрацией."""
        player = self.get_player_by_name_or_pubkey(name_or_pubkey)
        if not player or player.ai_subconscious is None:
            return None

        memories = player.ai_subconscious
        if tag and tag.strip():
            clean_tag = tag.strip().lower()
            memories = [m for m in memories if any(t.lower() == clean_tag for t in m.tags)]
        if query and query.strip():
            clean_query = query.strip().lower()
            memories = [m for m in memories if clean_query in m.content.lower()]
        return memories

    # -----------------------------------------------------------------
    # Метаданные хранилища
    # -----------------------------------------------------------------

    def get_meta(self, key: str) -> Optional[str]:
        raw = self._cf_meta.get(key.encode("utf-8"))
        return raw.decode("utf-8") if raw else None

    def set_meta(self, key: str, value: str) -> None:
        self._cf_meta[key.encode("utf-8")] = value.encode("utf-8")

    # -----------------------------------------------------------------
    # Инициализация Первородного Древа (Генезис DAG)
    # -----------------------------------------------------------------

    def ensure_genesis_tree(
        self,
        key_sigom: Optional[KeyPair] = None,
        key_ladomir: Optional[KeyPair] = None,
        key_eira: Optional[KeyPair] = None,
    ) -> Quest:
        """Делегирование канонической посадки Древа истоку в core.genesis."""
        from portal_volya.core.genesis import ensure_genesis_tree
        return ensure_genesis_tree(self, key_sigom, key_ladomir, key_eira)
