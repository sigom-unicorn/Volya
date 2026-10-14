"""
Сетевой P2P-узел децентрализованной сети «Воля» (P2PNode).

Обеспечивает:
1. Криптографическое рукопожатие по Ed25519 (взаимная верификация вольных узлов).
2. Автоматическую синхронизацию недостающих блоков из RocksDB соседей (Chain Sync).
3. Волну сплетен (Gossip Protocol) для мгновенного распространения новых транзакций и блоков.
4. Отсутствие центральных серверов: любой узел одновременно является и клиентом, и сервером.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional

from portal_volya.core.crypto import verify_canonical
from portal_volya.core.models import Block, Transaction
from portal_volya.node import VolyaNode
from portal_volya.p2p.protocol import MessageType, read_frame, write_frame

logger = logging.getLogger("VolyaP2P")


class P2PPeer:
    """Активное двустороннее соединение с пиром-соседом."""

    def __init__(
        self,
        pubkey: str,
        username: str,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        height: int,
        latest_block_hash: str,
    ) -> None:
        self.pubkey = pubkey
        self.username = username
        self.reader = reader
        self.writer = writer
        self.height = height
        self.latest_block_hash = latest_block_hash
        self.is_alive = True

    async def close(self) -> None:
        self.is_alive = False
        try:
            self.writer.close()
            await self.writer.wait_closed()
        except Exception:
            pass


class P2PNetwork:
    """P2P Сетевой контроллер узла «Воля»."""

    def __init__(
        self,
        node: VolyaNode,
        host: str = "127.0.0.1",
        port: int = 7777,
    ) -> None:
        self.node = node
        self.host = host
        self.port = port
        self.peers: dict[str, P2PPeer] = {}  # pubkey -> P2PPeer
        self._server: Optional[asyncio.Server] = None
        self._running = False
        self._tasks: list[asyncio.Task] = []

    @property
    def is_running(self) -> bool:
        return self._running

    def _get_timestamp(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    # -----------------------------------------------------------------
    # Запуск и остановка P2P сервера
    # -----------------------------------------------------------------

    async def start(self) -> None:
        """Запуск прослушивания входящих соединений от других вольных узлов."""
        if self._running:
            return

        self._running = True
        self._server = await asyncio.start_server(
            self._handle_incoming_connection,
            self.host,
            self.port,
        )

    async def stop(self) -> None:
        """Мягкая остановка сетевого узла и закрытие всех сессий."""
        self._running = False
        for task in self._tasks:
            task.cancel()

        for peer in list(self.peers.values()):
            await peer.close()
        self.peers.clear()

        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    # -----------------------------------------------------------------
    # Обработка входящих рукопожатий и сообщений
    # -----------------------------------------------------------------

    async def _handle_incoming_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Обработка нового входящего пира."""
        peer: Optional[P2PPeer] = None
        try:
            # 1. Ожидаем канонический HANDSHAKE
            msg_type, payload = await read_frame(reader)
            if msg_type != MessageType.HANDSHAKE:
                writer.close()
                return

            # Проверка криптографической подписи рукопожатия пира
            peer_pubkey = payload["pubkey"]
            peer_sig = payload["signature"]
            verify_payload = {k: v for k, v in payload.items() if k != "signature"}

            if not verify_canonical(peer_pubkey, verify_payload, peer_sig):
                writer.close()
                return

            # 2. Отправляем ответный HANDSHAKE_ACK
            ack_body = {
                "pubkey": self.node.identity.pubkey,
                "username": self.node.identity.username,
                "height": self.node.height,
                "latest_block_hash": self.node.latest_block_hash,
                "timestamp": self._get_timestamp(),
            }
            ack_sig = self.node.identity.keypair.sign_canonical(ack_body)
            await write_frame(
                writer,
                MessageType.HANDSHAKE_ACK,
                {**ack_body, "signature": ack_sig},
            )

            # 3. Регистрируем пира
            peer = P2PPeer(
                pubkey=peer_pubkey,
                username=payload["username"],
                reader=reader,
                writer=writer,
                height=payload["height"],
                latest_block_hash=payload["latest_block_hash"],
            )
            self.peers[peer_pubkey] = peer

            # 4. Если пир опережает нас по высоте, запрашиваем синхронизацию
            if peer.height > self.node.height:
                await self._request_sync(peer)

            # 5. Цикл прослушивания сообщений от пира
            await self._listen_peer(peer)

        except (asyncio.IncompleteReadError, ConnectionResetError):
            pass
        except Exception as e:
            logger.debug(f"P2P incoming error: {e}")
        finally:
            if peer and peer.pubkey in self.peers:
                del self.peers[peer.pubkey]
                await peer.close()

    # -----------------------------------------------------------------
    # Исходящее подключение к соседу
    # -----------------------------------------------------------------

    async def connect_to_peer(self, host: str, port: int) -> Optional[P2PPeer]:
        """Подключение к удалённому вольному узлу и инициация взаимного рукопожатия."""
        try:
            reader, writer = await asyncio.open_connection(host, port)

            # 1. Отправляем HANDSHAKE
            hs_body = {
                "pubkey": self.node.identity.pubkey,
                "username": self.node.identity.username,
                "height": self.node.height,
                "latest_block_hash": self.node.latest_block_hash,
                "timestamp": self._get_timestamp(),
            }
            hs_sig = self.node.identity.keypair.sign_canonical(hs_body)
            await write_frame(
                writer,
                MessageType.HANDSHAKE,
                {**hs_body, "signature": hs_sig},
            )

            # 2. Получаем HANDSHAKE_ACK
            msg_type, payload = await read_frame(reader)
            if msg_type != MessageType.HANDSHAKE_ACK:
                writer.close()
                return None

            peer_pubkey = payload["pubkey"]
            peer_sig = payload["signature"]
            verify_payload = {k: v for k, v in payload.items() if k != "signature"}

            if not verify_canonical(peer_pubkey, verify_payload, peer_sig):
                writer.close()
                return None

            peer = P2PPeer(
                pubkey=peer_pubkey,
                username=payload["username"],
                reader=reader,
                writer=writer,
                height=payload["height"],
                latest_block_hash=payload["latest_block_hash"],
            )
            self.peers[peer_pubkey] = peer

            # Запуск фонового слушателя
            task = asyncio.create_task(self._listen_peer(peer))
            self._tasks.append(task)

            # Синхронизация, если сосед дальше по цепочке
            if peer.height > self.node.height:
                await self._request_sync(peer)

            return peer

        except Exception as e:
            logger.debug(f"Не удалось подключиться к {host}:{port}: {e}")
            return None

    # -----------------------------------------------------------------
    # Слушатель входящих кадров от подключенного соседа
    # -----------------------------------------------------------------

    async def _listen_peer(self, peer: P2PPeer) -> None:
        """Цикл обработки кадров от конкретного соседа."""
        try:
            while self._running and peer.is_alive:
                msg_type, payload = await read_frame(peer.reader)

                if msg_type == MessageType.PING:
                    await write_frame(peer.writer, MessageType.PONG, {"timestamp": self._get_timestamp()})

                elif msg_type == MessageType.GET_BLOCKS:
                    from_index = payload.get("from_index", 0)
                    max_count = payload.get("max_count", 50)
                    blocks_to_send = []
                    for idx in range(from_index, from_index + max_count):
                        b = self.node.block_store.get_block(idx)
                        if b is None:
                            break
                        blocks_to_send.append(b.model_dump())

                    await write_frame(peer.writer, MessageType.BLOCKS_BATCH, {"blocks": blocks_to_send})

                elif msg_type == MessageType.BLOCKS_BATCH:
                    raw_blocks = payload.get("blocks", [])
                    for raw_b in raw_blocks:
                        block = Block(**raw_b)
                        if block.index == self.node.height:
                            self.node.receive_and_apply_block(block)

                elif msg_type == MessageType.BROADCAST_TX:
                    tx = Transaction(**payload["tx"])
                    added = self.node.add_to_mempool(tx)
                    if added:
                        # Волна Gossip: распространяем дальше остальным пирам
                        await self.broadcast_transaction(tx, exclude_pubkey=peer.pubkey)

                elif msg_type == MessageType.BROADCAST_BLOCK:
                    block = Block(**payload["block"])
                    if block.index == self.node.height:
                        self.node.receive_and_apply_block(block)
                        peer.height = self.node.height
                        peer.latest_block_hash = self.node.latest_block_hash
                        # Волна Gossip: передаем дальше
                        await self.broadcast_block(block, exclude_pubkey=peer.pubkey)
                    elif block.index > self.node.height:
                        # Мы отстали — запрашиваем синхронизацию
                        await self._request_sync(peer)

        except (asyncio.IncompleteReadError, ConnectionResetError):
            pass
        except Exception as e:
            logger.debug(f"Peer loop error {peer.username}: {e}")
        finally:
            if peer.pubkey in self.peers:
                del self.peers[peer.pubkey]
            await peer.close()

    # -----------------------------------------------------------------
    # Синхронизация и рассылка (Gossip)
    # -----------------------------------------------------------------

    async def _request_sync(self, peer: P2PPeer) -> None:
        """Запрос недостающих блоков у соседа."""
        await write_frame(
            peer.writer,
            MessageType.GET_BLOCKS,
            {"from_index": self.node.height, "max_count": 50},
        )

    async def broadcast_transaction(
        self,
        tx: Transaction,
        exclude_pubkey: Optional[str] = None,
    ) -> None:
        """Распространение транзакции по всей P2P сети (Gossip)."""
        payload = {"tx": tx.model_dump()}
        dead_peers = []
        for pubkey, peer in self.peers.items():
            if pubkey == exclude_pubkey:
                continue
            try:
                await write_frame(peer.writer, MessageType.BROADCAST_TX, payload)
            except Exception:
                dead_peers.append(pubkey)

        for p in dead_peers:
            if p in self.peers:
                await self.peers[p].close()
                del self.peers[p]

    async def broadcast_block(
        self,
        block: Block,
        exclude_pubkey: Optional[str] = None,
    ) -> None:
        """Распространение запечатанного блока по всей P2P сети (Gossip)."""
        payload = {"block": block.model_dump()}
        dead_peers = []
        for pubkey, peer in self.peers.items():
            if pubkey == exclude_pubkey:
                continue
            try:
                await write_frame(peer.writer, MessageType.BROADCAST_BLOCK, payload)
            except Exception:
                dead_peers.append(pubkey)

        for p in dead_peers:
            if p in self.peers:
                await self.peers[p].close()
                del self.peers[p]
