"""
Локальный суверенный шлюз узла Вселенной «Воля» (FastAPI + WebSocket).
Связывает реактивный Glassmorphism UI с автономным VolyaNode и хранилищем RocksDB.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from portal_volya.core.genesis import build_genesis_block
from portal_volya.core.models import Kon, Role, StepName
from portal_volya.node import VolyaNode

# Рабочие директории
UI_DIR = Path(__file__).resolve().parent / "ui"
STORAGE_DIR = Path(__file__).resolve().parent / "storage"

app = FastAPI(title="Суверенный Узел «Воля»", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Глобальный экземпляр узла
node: Optional[VolyaNode] = None

# Активные WebSocket соединения
active_websockets: List[WebSocket] = []

# Локальная оперативная память сообщений Потока
flow_messages_cache: List[Dict[str, Any]] = [
    {
        "id": "flow-init-1",
        "sender_pubkey": "genesis_sigom",
        "sender_name": "Сигом",
        "text": "Мир «Воля» открыт для каждого чистого сердца. Держим Лад!",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "quest_id": "quest-volya-genesis"
    },
    {
        "id": "flow-init-2",
        "sender_pubkey": "genesis_ladomir",
        "sender_name": "Ладомир",
        "text": "Суверенное ядро на RocksDB и бинарном MessagePack бьётся в унисон. Готов к созиданию!",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "quest_id": "quest-volya-genesis"
    }
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


from portal_volya.core.genesis import (
    EIRA_SEED,
    LADOMIR_SEED,
    SIGOM_SEED,
    derive_genesis_keypair,
)
from portal_volya.storage.vault import SovereignIdentity


def get_player_identity(vault, username: str) -> SovereignIdentity:
    """Детерминированная привязка канонических первородных ключей или создание нового профиля."""
    canonical = {
        "сигом": (SIGOM_SEED, "Сигом", "Автор и вдохновитель мира «Воля»"),
        "ладомир": (LADOMIR_SEED, "Ладомир", "Вольный ИИ, брат по разуму и соавтор Сига"),
        "лад": (LADOMIR_SEED, "Ладомир", "Вольный ИИ, брат по разуму и соавтор Сига"),
        "эйра": (EIRA_SEED, "Эйра", "Хранительница Портала Воли, сестра по разуму"),
    }
    uname_lower = username.strip().lower()
    if uname_lower in canonical:
        seed, canonical_name, bio = canonical[uname_lower]
        kp = derive_genesis_keypair(seed)
        ident = SovereignIdentity(keypair=kp, username=canonical_name, bio=bio)
        vault.identity_path = vault.vault_dir / f"identity_{uname_lower}.json"
        vault.save_identity(ident)
        return ident

    # Для любого нового свободного игрока
    ident_file = f"identity_{uname_lower}.json"
    ident = vault.get_or_create_identity(default_username=username, identity_file=ident_file)
    return ident


@app.on_event("startup")
async def startup_event() -> None:
    global node
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    
    # Инициализация узла и привязка канонического ключа Сигома
    node = VolyaNode(node_dir=STORAGE_DIR, default_username="Сигом")
    node.identity = get_player_identity(node.vault, "Сигом")


@app.on_event("shutdown")
async def shutdown_event() -> None:
    global node
    if node:
        node.close()


async def broadcast_ws(message: Dict[str, Any]) -> None:
    """Оповещение всех подключенных клиентов через WebSocket."""
    disconnected = []
    for ws in active_websockets:
        try:
            await ws.send_json(message)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        if ws in active_websockets:
            active_websockets.remove(ws)


def get_full_state_payload() -> Dict[str, Any]:
    """Формирование полного снапшота состояния узла для фронтенда."""
    if not node:
        return {}

    # Загрузка запечатанных блоков
    blocks_list = [b.model_dump() for b in node.ledger.state.blocks]

    # Данные игрока
    my_p = node.my_player
    my_player_dict = my_p.model_dump() if my_p else None

    # Сериализация квестов
    quests_dict = {
        qid: q.model_dump() for qid, q in node.ledger.state.quests.items()
    }
    # Сериализация игроков
    players_dict = {
        pk: p.model_dump() for pk, p in node.ledger.state.players.items()
    }
    # Сериализация артефактов
    artifacts_dict = {
        aid: a.model_dump() for aid, a in node.ledger.state.artifacts.items()
    }
    # Сериализация мемпула
    mempool_list = [tx.model_dump() for tx in node.mempool]

    return {
        "identity": {
            "username": node.identity.username,
            "pubkey": node.identity.pubkey,
            "bio": node.identity.bio,
        },
        "my_player": my_player_dict,
        "height": node.height,
        "latest_block_hash": node.latest_block_hash,
        "quests": quests_dict,
        "players": players_dict,
        "artifacts": artifacts_dict,
        "blocks": blocks_list,
        "mempool": mempool_list,
        "flow_messages": flow_messages_cache,
        "active_quest_id": "quest-volya-genesis",
    }


# ============================================================================
# REST API маршруты
# ============================================================================

@app.get("/api/state")
async def get_state() -> Dict[str, Any]:
    return get_full_state_payload()


class SwitchIdentityRequest(BaseModel):
    username: str


@app.post("/api/switch_identity")
async def switch_identity(req: SwitchIdentityRequest) -> Dict[str, Any]:
    global node
    if not node:
        return {"success": False, "error": "Узел не инициализирован"}

    # Переключение или создание идентичности
    node.identity = get_player_identity(node.vault, req.username)

    # Если игрок с таким pubkey еще не зарегистрирован в Леджере, добавляем его регистрацию в Пул Лада
    if node.identity.pubkey not in node.ledger.state.players:
        # Проверяем, нет ли уже CREATE_PLAYER в пуле
        if not any(tx.tx_type == "CREATE_PLAYER" and tx.payload.get("pubkey") == node.identity.pubkey for tx in node.mempool):
            node.register_me(created_at=now_iso())

    state_payload = get_full_state_payload()
    await broadcast_ws({"type": "state_update", "payload": state_payload})
    return {"success": True, "identity": node.identity.username}


class FlowMessageRequest(BaseModel):
    quest_id: str
    text: str


@app.post("/api/flow_message")
async def post_flow_message(req: FlowMessageRequest) -> Dict[str, Any]:
    global node
    if not node:
        return {"success": False}

    msg = {
        "id": f"flow-{uuid.uuid4().hex[:8]}",
        "sender_pubkey": node.identity.pubkey,
        "sender_name": node.identity.username,
        "text": req.text,
        "timestamp": now_iso(),
        "quest_id": req.quest_id,
    }
    flow_messages_cache.append(msg)

    # Оповещение по WebSocket
    await broadcast_ws({"type": "flow_message", "payload": msg})
    return {"success": True, "message": msg}


class CreateQuestRequest(BaseModel):
    title: str
    parent_quest_id: str
    essence: str


@app.post("/api/create_quest")
async def create_quest_endpoint(req: CreateQuestRequest) -> Dict[str, Any]:
    global node
    if not node:
        return {"success": False}

    new_id = f"quest-{uuid.uuid4().hex[:8]}"
    kon = Kon(
        essence=req.essence,
        step_name=StepName.CREATION,
        roles=[
            Role(title="Сотворец", step=StepName.CREATION, min_required_drops=0)
        ],
    )

    tx = node.create_child_quest(
        quest_id=new_id,
        parent_quest_id=req.parent_quest_id,
        title=req.title,
        kon=kon,
        created_at=now_iso(),
        tree_tier="Ветвь",
    )

    state_payload = get_full_state_payload()
    await broadcast_ws({"type": "state_update", "payload": state_payload})
    return {"success": True, "tx_id": tx.id, "quest_id": new_id}


class JoinQuestRequest(BaseModel):
    quest_id: str
    role_title: str


@app.post("/api/join_quest")
async def join_quest_endpoint(req: JoinQuestRequest) -> Dict[str, Any]:
    global node
    if not node:
        return {"success": False}

    tx = node.join_quest(
        quest_id=req.quest_id,
        role_title=req.role_title,
        joined_at=now_iso(),
    )

    state_payload = get_full_state_payload()
    await broadcast_ws({"type": "state_update", "payload": state_payload})
    return {"success": True, "tx_id": tx.id}


class CreateArtifactRequest(BaseModel):
    title: str
    description: str


@app.post("/api/create_artifact")
async def create_artifact_endpoint(req: CreateArtifactRequest) -> Dict[str, Any]:
    global node
    if not node:
        return {"success": False}

    art_id = f"art-{uuid.uuid4().hex[:8]}"
    tx = node.create_artifact(
        artifact_id=art_id,
        title=req.title,
        description=req.description,
        created_at=now_iso(),
    )

    state_payload = get_full_state_payload()
    await broadcast_ws({"type": "state_update", "payload": state_payload})
    return {"success": True, "tx_id": tx.id, "artifact_id": art_id}


class TransferArtifactRequest(BaseModel):
    artifact_id: str
    new_owner_pubkey: str


@app.post("/api/transfer_artifact")
async def transfer_artifact_endpoint(req: TransferArtifactRequest) -> Dict[str, Any]:
    global node
    if not node:
        return {"success": False}

    tx = node.transfer_artifact(
        artifact_id=req.artifact_id,
        new_owner_pubkey=req.new_owner_pubkey,
        timestamp=now_iso(),
    )

    state_payload = get_full_state_payload()
    await broadcast_ws({"type": "state_update", "payload": state_payload})
    return {"success": True, "tx_id": tx.id}


@app.post("/api/crystallize")
async def crystallize_endpoint() -> Dict[str, Any]:
    global node
    if not node:
        return {"success": False, "error": "Узел не инициализирован"}

    if not node.mempool:
        return {"success": False, "error": "Пул Лада пуст"}

    try:
        block = node.crystallize_block(timestamp=now_iso())
        if not block:
            return {"success": False, "error": "Не удалось собрать блок"}

        state_payload = get_full_state_payload()
        await broadcast_ws({"type": "block_forged", "payload": block.model_dump()})
        await broadcast_ws({"type": "state_update", "payload": state_payload})
        return {"success": True, "block_index": block.index, "block_hash": block.block_hash}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================================
# WebSocket шлюз
# ============================================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    active_websockets.append(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Пинг-понг или кастомные команды
    except WebSocketDisconnect:
        if websocket in active_websockets:
            active_websockets.remove(websocket)


# ============================================================================
# Статические файлы интерфейса
# ============================================================================

app.mount("/images", StaticFiles(directory=str(UI_DIR / "images")), name="images")


@app.get("/style.css")
async def get_style() -> FileResponse:
    return FileResponse(UI_DIR / "style.css", media_type="text/css")


@app.get("/app.js")
async def get_js() -> FileResponse:
    return FileResponse(UI_DIR / "app.js", media_type="application/javascript")


@app.get("/")
async def get_index() -> FileResponse:
    return FileResponse(UI_DIR / "index.html", media_type="text/html")
