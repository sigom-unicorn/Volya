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
        self._cf_meta = self.db.get_column_family(CF_META)

        self._h_nodes = self.db.get_column_family_handle(CF_NODES)
        self._h_quests = self.db.get_column_family_handle(CF_QUESTS)
        self._h_drops = self.db.get_column_family_handle(CF_DROPS)
        self._h_players = self.db.get_column_family_handle(CF_PLAYERS)
        self._h_tree = self.db.get_column_family_handle(CF_TREE_LINKS)
        self._h_flows = self.db.get_column_family_handle(CF_FLOW_LINKS)
        self._h_summaries = self.db.get_column_family_handle(CF_SUMMARIES)
        self._h_meta = self.db.get_column_family_handle(CF_META)

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
                self._cf_meta = None
                self._h_nodes = None
                self._h_quests = None
                self._h_drops = None
                self._h_players = None
                self._h_tree = None
                self._h_flows = None
                self._h_summaries = None
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
        - Индексация узла в общем каталоге
        - Раскладка по специализированным индексам (квест, капля, игрок)
        """
        wb = WriteBatch()
        node_id_b = _h_bytes(node.id)
        raw_node = ormsgpack.packb(node.model_dump())
        wb.put(node_id_b, raw_node, self._h_nodes)

        # 1. Если узел - появление Квеста
        if node.node_type == DagNodeType.QUEST:
            quest = Quest(**node.payload)
            q_id_b = _h_bytes(quest.id)
            wb.put(q_id_b, ormsgpack.packb(quest.model_dump()), self._h_quests)

            # Привязка к родителю в Древе
            parent_key = _h_bytes(quest.parent_quest_id) if quest.parent_quest_id else b"ROOT"
            existing_children_raw = self._cf_tree.get(parent_key)
            existing_children = ormsgpack.unpackb(existing_children_raw) if existing_children_raw else []
            if quest.id not in existing_children:
                existing_children.append(quest.id)
                wb.put(parent_key, ormsgpack.packb(existing_children), self._h_tree)

        # 2. Если узел - Капля в потоке (слово, аудио, видео, ресурс, инструмент, артефакт)
        elif node.node_type == DagNodeType.DROP:
            drop = FlowDrop(**node.payload)
            d_id_b = _h_bytes(drop.id)
            wb.put(d_id_b, ormsgpack.packb(drop.model_dump()), self._h_drops)

            # Привязка капли к нити потока
            flow_key = drop.flow_id.encode("utf-8")
            existing_drops_raw = self._cf_flows.get(flow_key)
            existing_drops = ormsgpack.unpackb(existing_drops_raw) if existing_drops_raw else []
            if drop.id not in existing_drops:
                existing_drops.append(drop.id)
                wb.put(flow_key, ormsgpack.packb(existing_drops), self._h_flows)

        # 3. Если узел - регистрация игрока
        elif node.node_type == DagNodeType.PLAYER:
            player = Player(**node.payload)
            p_key = player.pubkey.encode("utf-8")
            wb.put(p_key, ormsgpack.packb(player.model_dump()), self._h_players)

        self.db.write(wb)

    def get_node(self, node_id: str) -> Optional[DagNode]:
        raw = self._cf_nodes.get(_h_bytes(node_id))
        if not raw:
            return None
        return DagNode(**ormsgpack.unpackb(raw))

    # -----------------------------------------------------------------
    # Выборки по иерархии Древа
    # -----------------------------------------------------------------

    def get_quest(self, quest_id: str) -> Optional[Quest]:
        raw = self._cf_quests.get(_h_bytes(quest_id))
        if not raw:
            return None
        return Quest(**ormsgpack.unpackb(raw))

    def get_all_quests(self) -> list[Quest]:
        quests = []
        for _, raw in self._cf_quests.items():
            quests.append(Quest(**ormsgpack.unpackb(raw)))
        return quests

    def get_child_quests(self, parent_quest_id: Optional[str]) -> list[Quest]:
        parent_key = _h_bytes(parent_quest_id) if parent_quest_id else b"ROOT"
        raw = self._cf_tree.get(parent_key)
        if not raw:
            return []
        child_ids = ormsgpack.unpackb(raw)
        res = []
        for cid in child_ids:
            q = self.get_quest(cid)
            if q:
                res.append(q)
        return res

    # -----------------------------------------------------------------
    # Выборки по Потокам и Каплям (Слово, Аудио, Ресурс, Инструмент, Артефакт)
    # -----------------------------------------------------------------

    def get_drop(self, drop_id: str) -> Optional[FlowDrop]:
        raw = self._cf_drops.get(_h_bytes(drop_id))
        if not raw:
            return None
        return FlowDrop(**ormsgpack.unpackb(raw))

    def get_flow_drops(self, flow_id: str) -> list[FlowDrop]:
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
        p_key = player.pubkey.encode("utf-8")
        self._cf_players[p_key] = ormsgpack.packb(player.model_dump())

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

