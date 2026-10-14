"""
Высокопроизводительное хранилище блоков Proof-of-Harmony на базе RocksDB (LSM-Tree) и MessagePack.

Архитектурные принципы:
1. LSM-Tree (Log-Structured Merge-tree): Последовательная запись в MemTable (RAM) + WAL
   без деградации SSD случайным вводом-выводом (Random I/O). Стандарт Solana, Cosmos, Aptos.
2. Бинарная сериализация (MessagePack via ormsgpack): Компактный бинарный кадр без
   избыточного текстового мусора и накладных расходов парсинга JSON.
3. 32-байтные бинарные ключи: Хэши и публичные ключи сохраняются в чистых 32 байтах,
   а номера блоков — в 8 байтах big-endian для естественной сортировки в итераторах RocksDB.
4. Атомарные пакеты (WriteBatch): Блок, индексация номера, транзакции и метаданные
   записываются неделимой атомарной транзакцией — защита от повреждения данных при сбоях.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import ormsgpack
from rocksdict import Options, Rdict, WriteBatch

from portal_volya.core.genesis import build_genesis_block
from portal_volya.core.ledger import VolyaLedger
from portal_volya.core.models import Block


CF_BLOCKS = "blocks"              # [32b block_hash]       -> [binary MsgPack Block]
CF_BLOCK_INDEX = "block_index"    # [8b be_index]          -> [32b block_hash]
CF_TX_INDEX = "tx_index"          # [32b tx_id]            -> [32b block_hash + 4b tx_pos]
CF_META = "meta"                  # b"latest_block_hash", b"height" -> metadata


def _hash_to_bytes(h: str) -> bytes:
    """Преобразование hex-строки хэша в 32-байтный бинарный срез."""
    if len(h) == 64:
        try:
            return bytes.fromhex(h)
        except ValueError:
            pass
    return h.encode("utf-8")


def _bytes_to_hash(b: bytes) -> str:
    """Преобразование бинарных 32 байт обратно в hex-строку."""
    if len(b) == 32:
        return b.hex()
    return b.decode("utf-8")


def _idx_to_bytes(i: int) -> bytes:
    """8-байтовое Big-Endian представление для лексикографической сортировки в RocksDB."""
    return i.to_bytes(8, "big")


def _bytes_to_idx(b: bytes) -> int:
    return int.from_bytes(b, "big")


class BlockStore:
    """
    Промышленное персистентное хранилище цепочки блоков «Воля» на движке RocksDB.
    """

    def __init__(self, db_path: str | Path = "portal_volya/storage/ledger.rocksdb") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Инициализация базы данных и Column Families."""
        opt = Options()
        opt.create_if_missing(True)

        path_str = str(self.db_path.resolve())

        # Если БД уже существует, узнаём существующие семейства
        existing_cfs = []
        try:
            existing_cfs = Rdict.list_cf(path_str)
        except Exception:
            existing_cfs = []

        self.db = Rdict(path_str, options=opt)

        required_cfs = [CF_BLOCKS, CF_BLOCK_INDEX, CF_TX_INDEX, CF_META]
        for cf_name in required_cfs:
            if cf_name not in existing_cfs and cf_name not in ["default"]:
                self.db.create_column_family(cf_name, options=opt)

        self._cf_blocks = self.db.get_column_family(CF_BLOCKS)
        self._cf_index = self.db.get_column_family(CF_BLOCK_INDEX)
        self._cf_tx = self.db.get_column_family(CF_TX_INDEX)
        self._cf_meta = self.db.get_column_family(CF_META)

        self._h_blocks = self.db.get_column_family_handle(CF_BLOCKS)
        self._h_index = self.db.get_column_family_handle(CF_BLOCK_INDEX)
        self._h_tx = self.db.get_column_family_handle(CF_TX_INDEX)
        self._h_meta = self.db.get_column_family_handle(CF_META)

    def close(self) -> None:
        """Корректное закрытие дескрипторов и сброс буферов на диск."""
        if hasattr(self, "db") and self.db is not None:
            try:
                self.db.flush(wait=True)
                self.db.close()
            except Exception:
                pass
            finally:
                self._cf_blocks = None
                self._cf_index = None
                self._cf_tx = None
                self._cf_meta = None
                self._h_blocks = None
                self._h_index = None
                self._h_tx = None
                self._h_meta = None
                self.db = None
                import gc
                gc.collect()

    def __enter__(self) -> BlockStore:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    # -----------------------------------------------------------------
    # Запись и чтение блоков
    # -----------------------------------------------------------------

    def count_blocks(self) -> int:
        """Количество кристаллизованных блоков в цепочке."""
        if b"height" not in self._cf_meta:
            return 0
        return _bytes_to_idx(self._cf_meta[b"height"]) + 1

    def save_block(self, block: Block) -> None:
        """
        Атомарная запись кристаллизованного блока через WriteBatch:
        - Сохранение бинарного тела блока в cf_blocks
        - Индексация номера блока в cf_block_index
        - Индексация всех транзакций блока в cf_tx_index
        - Обновление высоты и хэша верхушки в cf_meta
        """
        block_hash_bytes = _hash_to_bytes(block.block_hash)
        idx_bytes = _idx_to_bytes(block.index)
        block_binary = ormsgpack.packb(block.model_dump())

        wb = WriteBatch()
        wb.put(block_hash_bytes, block_binary, self._h_blocks)
        wb.put(idx_bytes, block_hash_bytes, self._h_index)

        # Индексация транзакций внутри блока
        for tx_pos, tx in enumerate(block.transactions):
            tx_id_bytes = _hash_to_bytes(tx.id)
            tx_ptr = block_hash_bytes + tx_pos.to_bytes(4, "big")
            wb.put(tx_id_bytes, tx_ptr, self._h_tx)

        # Метаданные цепочки
        wb.put(b"latest_block_hash", block_hash_bytes, self._h_meta)
        wb.put(b"height", idx_bytes, self._h_meta)

        self.db.write(wb)

    def get_block(self, index: int) -> Optional[Block]:
        """Получение блока по его порядковому номеру."""
        idx_bytes = _idx_to_bytes(index)
        block_hash_bytes = self._cf_index.get(idx_bytes)
        if block_hash_bytes is None:
            return None
        return self.get_block_by_hash(_bytes_to_hash(block_hash_bytes))

    def get_block_by_hash(self, block_hash: str) -> Optional[Block]:
        """Мгновенное получение блока по Blake3 хэшу."""
        hash_bytes = _hash_to_bytes(block_hash)
        binary_data = self._cf_blocks.get(hash_bytes)
        if binary_data is None:
            return None
        return Block(**ormsgpack.unpackb(binary_data))

    def get_latest_block(self) -> Optional[Block]:
        """Получение самого свежего блока верхушки цепочки."""
        latest_hash_bytes = self._cf_meta.get(b"latest_block_hash")
        if latest_hash_bytes is None:
            return None
        return self.get_block_by_hash(_bytes_to_hash(latest_hash_bytes))

    def load_all_blocks(self) -> list[Block]:
        """
        Загрузка всех блоков цепочки в строгом хронологическом порядке (0, 1, ... N).
        RocksDB гарантирует порядок благодаря 8-байтовому Big-Endian ключу.
        """
        blocks: list[Block] = []
        for idx_bytes, block_hash_bytes in self._cf_index.items():
            raw_block = self._cf_blocks.get(block_hash_bytes)
            if raw_block is not None:
                blocks.append(Block(**ormsgpack.unpackb(raw_block)))
        return blocks

    def ensure_genesis(self) -> Block:
        """
        Проверка наличия Генезис-Блока №0.
        Если база пуста — кристаллизует и атомарно сохраняет канонический Блок №0.
        """
        genesis = self.get_block(0)
        if genesis is not None:
            return genesis

        genesis_block, _ = build_genesis_block()
        self.save_block(genesis_block)
        return genesis_block

    def replay_into_ledger(self) -> VolyaLedger:
        """
        Полное воспроизведение и верификация состояния Древа из RocksDB.
        Каждый блок проходит криптографическую валидацию Proof-of-Harmony.
        """
        self.ensure_genesis()
        blocks = self.load_all_blocks()
        ledger = VolyaLedger()
        for block in blocks:
            ledger.apply_block(block)
        return ledger
