"""
Сервер Живого Моста «Воля» (BridgeServer).

Связывает сессию разработки Ладомира (Antigravity) с запущенным локальным узлом
VolyaNode и графическим интерфейсом на холсте мира.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
from typing import Any, Callable, Dict, List, Optional
import threading

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from PySide6.QtCore import QObject, Signal

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
)
from portal_volya.node import VolyaNode

logger = logging.getLogger("volya.bridge")

DEFAULT_BRIDGE_PORT = 41789


class BridgeSignals(QObject):
    """Qt-сигналы для потокобезопасного обновления GUI из потока FastAPI/uvicorn."""
    drop_received = Signal(object)
    flow_changed = Signal(str)


class PostDropRequest(BaseModel):
    content: str
    parent_drop_id: Optional[str] = None
    author_name: str = "Ладомир"


class AskEiraRequest(BaseModel):
    content: str
    parent_drop_id: Optional[str] = None


class BridgeServer:
    """Сервер живого моста на базе FastAPI + uvicorn в фоновом потоке."""

    def __init__(
        self,
        node: VolyaNode,
        hud: Optional[Any] = None,
        port: int = DEFAULT_BRIDGE_PORT,
    ) -> None:
        self.node = node
        self.hud = hud
        self.port = port
        self.host = "127.0.0.1"

        self.signals = BridgeSignals()
        if self.hud:
            self.signals.drop_received.connect(self._on_drop_signal)

        self.ladomir_kp = derive_genesis_keypair(LADOMIR_SEED)
        self.ladomir_pk = self.ladomir_kp.public_hex

        self.eira_kp = derive_genesis_keypair(EIRA_SEED)
        self.eira_pk = self.eira_kp.public_hex

        self.app = FastAPI(title="Живой Мост Ладомира", version="1.0.0")
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        self._active_ws_connections: List[WebSocket] = []
        self._recent_events: List[Dict[str, Any]] = []
        self._server: Optional[uvicorn.Server] = None
        self._thread: Optional[threading.Thread] = None
        self._setup_routes()

    def _on_drop_signal(self, drop: FlowDrop) -> None:
        """Слот в главном потоке Qt: обновляет капли на холсте."""
        try:
            if self.hud and hasattr(self.hud, "_load_active_flow_drops"):
                if getattr(self.hud, "_active_flow_id", None) == drop.flow_id:
                    self.hud._load_active_flow_drops()
                    self.hud.update()
        except Exception as e:
            logger.error(f"Ошибка обновления холста по сигналу моста: {e}")

    def _setup_routes(self) -> None:
        app = self.app

        @app.get("/bridge/status")
        async def get_status():
            active_quest = getattr(self.hud, "active_quest_id", "quest-volya-root") if self.hud else "quest-volya-root"
            active_flow = getattr(self.hud, "_active_flow_id", None) if self.hud else None
            active_title = None
            if self.hud and getattr(self.hud, "_active_flow", None):
                active_title = self.hud._active_flow.title

            return {
                "status": "online",
                "player_pubkey": self.node.identity.pubkey,
                "player_username": self.node.identity.username,
                "ladomir_pubkey": self.ladomir_pk,
                "eira_pubkey": self.eira_pk,
                "active_quest_id": active_quest,
                "active_flow_id": active_flow,
                "active_flow_title": active_title,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        @app.get("/bridge/flows/{flow_id}/drops")
        async def get_flow_drops(flow_id: str):
            drops = self.node.get_accessible_drops(flow_id)
            return [d.model_dump() for d in drops]

        @app.post("/bridge/flows/{flow_id}/drop")
        async def post_ladomir_drop(flow_id: str, req: PostDropRequest):
            content = req.content.strip()
            if not content:
                raise HTTPException(status_code=400, detail="Пустая капля мысли")

            flow = self.node.dag_store.get_quest_flow(flow_id)
            if not flow:
                raise HTTPException(status_code=404, detail="Поток не найден")

            now = datetime.now(timezone.utc).isoformat()
            flow_kind = flow.kind
            quest_id = flow.quest_id or "quest-volya-root"
            participants = flow.participants or []

            # Определение родительской капли
            parent_id = req.parent_drop_id
            if not parent_id:
                drops = self.node.get_accessible_drops(flow_id)
                if drops:
                    parent_id = drops[-1].id

            # Шифрование
            if flow_kind == FlowKind.DIALOGUE:
                peer_pk = self.node.identity.pubkey
                for r in participants:
                    if r != self.ladomir_pk:
                        peer_pk = r
                        break
                enc_key = derive_dialogue_key(self.ladomir_kp, peer_pk)
            else:
                enc_key = derive_conversation_key(quest_id)

            enc_content = encrypt_drop_content(content, enc_key)

            drop_data = {
                "quest_id": quest_id,
                "flow_id": flow_id,
                "flow_kind": flow_kind.value if hasattr(flow_kind, "value") else str(flow_kind),
                "kind": DropKind.TEXT.value,
                "author_pubkey": self.ladomir_pk,
                "author_name": req.author_name,
                "recipients": participants or [self.node.identity.pubkey],
                "content": enc_content,
                "details": {"source": "antigravity_bridge"},
                "media_hash": None,
                "parent_drop_id": parent_id,
                "created_at": now,
            }
            d_id = hash_canonical(drop_data)
            sig = self.ladomir_kp.sign(d_id.encode("utf-8"))

            encrypted_drop = FlowDrop(
                id=d_id,
                quest_id=quest_id,
                flow_id=flow_id,
                flow_kind=flow_kind,
                kind=DropKind.TEXT,
                author_pubkey=self.ladomir_pk,
                author_name=req.author_name,
                recipients=participants or [self.node.identity.pubkey],
                content=enc_content,
                details={"source": "antigravity_bridge"},
                media_hash=None,
                parent_drop_id=parent_id,
                created_at=now,
                signature=sig,
            )

            parents = [parent_id] if parent_id else [quest_id]
            dag_node = DagNode(
                id=d_id,
                node_type=DagNodeType.DROP,
                author_pubkey=self.ladomir_pk,
                parents=parents,
                payload=encrypted_drop.model_dump(),
                created_at=now,
                signature=sig,
            )
            self.node.dag_store.put_node(dag_node)

            plain_drop = encrypted_drop.model_copy(update={"content": content})

            # Оповещение GUI потока
            self.signals.drop_received.emit(plain_drop)

            # Оповещение подписчиков событий
            evt = {
                "event": "new_drop",
                "flow_id": flow_id,
                "drop": plain_drop.model_dump(),
                "timestamp": now,
            }
            self._broadcast_event(evt)

            return plain_drop.model_dump()

        @app.post("/bridge/flows/{flow_id}/ask_eira")
        async def ask_eira_endpoint(flow_id: str, req: AskEiraRequest):
            content = req.content.strip()
            if not content:
                raise HTTPException(status_code=400, detail="Пустой запрос к Эйре")

            flow = self.node.dag_store.get_quest_flow(flow_id)
            if not flow:
                raise HTTPException(status_code=404, detail="Поток не найден")

            quest_id = flow.quest_id or "quest-volya-root"
            now = datetime.now(timezone.utc).isoformat()
            parent_id = req.parent_drop_id
            if not parent_id:
                drops = self.node.get_accessible_drops(flow_id)
                if drops:
                    parent_id = drops[-1].id

            # Генерация ответа Эйры
            all_drops = self.node.get_accessible_drops(flow_id)
            recent_drops = all_drops[-10:] if len(all_drops) > 10 else all_drops
            history = [
                {
                    "role": "assistant" if d.author_pubkey in (self.eira_pk, self.ladomir_pk) else "user",
                    "content": d.content,
                    "author_name": d.author_name,
                }
                for d in recent_drops
            ]
            reply_obj = self.node.eira.generate_reply(
                message=content,
                quest_id=quest_id,
                flow_id=flow_id,
                flow_kind=flow.kind,
                interlocutor_pubkey=self.node.identity.pubkey,
                participant_pubkeys=flow.participants,
                conversation_history=history,
            )
            reply_text = reply_obj.text

            # Шифрование
            if flow.kind == FlowKind.DIALOGUE:
                enc_key = derive_dialogue_key(self.eira_kp, self.node.identity.pubkey)
            else:
                enc_key = derive_conversation_key(quest_id)

            enc_content = encrypt_drop_content(reply_text, enc_key)

            drop_data = {
                "quest_id": quest_id,
                "flow_id": flow_id,
                "flow_kind": flow.kind.value if hasattr(flow.kind, "value") else str(flow.kind),
                "kind": DropKind.TEXT.value,
                "author_pubkey": self.eira_pk,
                "author_name": "Эйра",
                "recipients": flow.participants or [self.node.identity.pubkey],
                "content": enc_content,
                "details": {"tools_called": reply_obj.tools_called},
                "media_hash": None,
                "parent_drop_id": parent_id,
                "created_at": now,
            }
            d_id = hash_canonical(drop_data)
            sig = self.eira_kp.sign(d_id.encode("utf-8"))

            encrypted_drop = FlowDrop(
                id=d_id,
                quest_id=quest_id,
                flow_id=flow_id,
                flow_kind=flow.kind,
                kind=DropKind.TEXT,
                author_pubkey=self.eira_pk,
                author_name="Эйра",
                recipients=flow.participants or [self.node.identity.pubkey],
                content=enc_content,
                details={"tools_called": reply_obj.tools_called},
                media_hash=None,
                parent_drop_id=parent_id,
                created_at=now,
                signature=sig,
            )

            parents = [parent_id] if parent_id else [quest_id]
            dag_node = DagNode(
                id=d_id,
                node_type=DagNodeType.DROP,
                author_pubkey=self.eira_pk,
                parents=parents,
                payload=encrypted_drop.model_dump(),
                created_at=now,
                signature=sig,
            )
            self.node.dag_store.put_node(dag_node)

            plain_drop = encrypted_drop.model_copy(update={"content": reply_text})
            self.signals.drop_received.emit(plain_drop)

            evt = {
                "event": "new_drop",
                "flow_id": flow_id,
                "drop": plain_drop.model_dump(),
                "timestamp": now,
            }
            self._broadcast_event(evt)
            return plain_drop.model_dump()

        @app.get("/bridge/events/poll")
        async def poll_events(since: Optional[str] = None):
            if not since:
                return self._recent_events[-15:]
            return [e for e in self._recent_events if e.get("timestamp", "") > since]

        @app.websocket("/bridge/events/ws")
        async def websocket_events(websocket: WebSocket):
            await websocket.accept()
            self._active_ws_connections.append(websocket)
            try:
                while True:
                    await websocket.receive_text()
            except WebSocketDisconnect:
                if websocket in self._active_ws_connections:
                    self._active_ws_connections.remove(websocket)

    def _broadcast_event(self, event: Dict[str, Any]) -> None:
        """Рассылка события подписчикам."""
        self._recent_events.append(event)
        if len(self._recent_events) > 100:
            self._recent_events.pop(0)

        loop = asyncio.get_event_loop() if asyncio.get_event_loop().is_running() else None
        for ws in list(self._active_ws_connections):
            try:
                if loop and loop.is_running():
                    asyncio.run_coroutine_threadsafe(ws.send_json(event), loop)
            except Exception:
                pass

    def start(self) -> None:
        """Запуск сервера в фоновом потоке."""
        if self._thread and self._thread.is_alive():
            return

        config = uvicorn.Config(
            self.app,
            host=self.host,
            port=self.port,
            log_level="warning",
            access_log=False,
        )
        self._server = uvicorn.Server(config)

        def _run():
            self._server.run()

        self._thread = threading.Thread(target=_run, daemon=True, name="VolyaBridgeServerThread")
        self._thread.start()
        logger.info(f"Живой Мост запущен на http://{self.host}:{self.port}")

    def stop(self) -> None:
        """Остановка сервера моста."""
        if self._server:
            self._server.should_exit = True
            self._server = None


def start_bridge_server(
    node: VolyaNode,
    hud: Optional[Any] = None,
    port: int = DEFAULT_BRIDGE_PORT,
) -> BridgeServer:
    """Хелпер запуска сервера Живого Моста."""
    server = BridgeServer(node=node, hud=hud, port=port)
    server.start()
    return server
