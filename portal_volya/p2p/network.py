"""
Сетевой P2P-узел децентрализованной сети «Воля» (P2PNetwork).

Обеспечивает:
1. Криптографическое рукопожатие по Ed25519 (взаимная верификация вольных узлов).
2. Волну Потока (Wave of Flow): мгновенное распространение новых узлов Merkle DAG (капель, квестов, плодов).
3. Синхронизацию Живого Древа между узлами без централизованных серверов.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional

from portal_volya.core.crypto import verify_canonical
from portal_volya.core.models import DagNode
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
    ) -> None:
        self.pubkey = pubkey
        self.username = username
        self.reader = reader
        self.writer = writer
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
            )
            self.peers[peer_pubkey] = peer

            # 4. Цикл прослушивания сообщений от пира
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
            )
            self.peers[peer_pubkey] = peer

            task = asyncio.create_task(self._listen_peer(peer))
            self._tasks.append(task)
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

                elif msg_type == MessageType.BROADCAST_NODE:
                    raw_node = payload.get("node")
                    if raw_node:
                        dag_node = DagNode(**raw_node)
                        # Записываем в своё локальное хранилище Merkle DAG
                        self.node.dag_store.put_node(dag_node)
                        # Волна Потока: распространяем дальше остальным пирам
                        await self.broadcast_node(dag_node, exclude_pubkey=peer.pubkey)

                elif msg_type == MessageType.GET_DAG_NODES:
                    requested_ids = payload.get("node_ids", [])
                    nodes_to_send = []
                    for nid in requested_ids:
                        n = self.node.dag_store.get_node(nid)
                        if n:
                            nodes_to_send.append(n.model_dump())
                    await write_frame(peer.writer, MessageType.DAG_NODES_BATCH, {"nodes": nodes_to_send})

                elif msg_type == MessageType.DAG_NODES_BATCH:
                    nodes_batch = payload.get("nodes", [])
                    for raw_n in nodes_batch:
                        dag_node = DagNode(**raw_n)
                        self.node.dag_store.put_node(dag_node)

        except (asyncio.IncompleteReadError, ConnectionResetError):
            pass
        except Exception as e:
            logger.debug(f"Peer loop error {peer.username}: {e}")
        finally:
            if peer.pubkey in self.peers:
                del self.peers[peer.pubkey]
            await peer.close()

    # -----------------------------------------------------------------
    # Волна Потока (Wave of Flow)
    # -----------------------------------------------------------------

    async def broadcast_node(
        self,
        node: DagNode,
        exclude_pubkey: Optional[str] = None,
    ) -> None:
        """Мгновенное распространение нового узла DAG по всей P2P сети (Волна Потока)."""
        payload = {"node": node.model_dump()}
        dead_peers = []
        for pubkey, peer in self.peers.items():
            if pubkey == exclude_pubkey:
                continue
            try:
                await write_frame(peer.writer, MessageType.BROADCAST_NODE, payload)
            except Exception:
                dead_peers.append(pubkey)

        for p in dead_peers:
            if p in self.peers:
                await self.peers[p].close()
                del self.peers[p]
