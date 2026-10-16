"""
Локальный суверенный шлюз узла Вселенной «Воля» (FastAPI + WebSocket).
Связывает реактивный Glassmorphism UI с автономным VolyaNode и хранилищем RocksDB.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

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
    ensure_genesis_tree,
)
from portal_volya.core.models import (
    DagNode,
    DagNodeType,
    DropKind,
    FlowDrop,
    FlowKind,
    Kon,
    Player,
    Quest,
    StepName,
    TreeTier,
)
from portal_volya.storage.dag_store import DagStore
from portal_volya.storage.identity import (
    SovereignIdentity,
    get_or_create_identity,
    save_identity,
)

dag_store: Optional[DagStore] = None


def get_player_identity(node_dir: Path | str, username: str) -> SovereignIdentity:
    """Детерминированная привязка канонических первородных ключей или создание нового профиля."""
    canonical = {
        "сигом": (SIGOM_SEED, "Сигом", "Автор и вдохновитель Вселенной и игры «Воля»"),
        "ладомир": (LADOMIR_SEED, "Ладомир", "Разумное искусственное существо, вольный ИИ, брат по разуму и соавтор Сига"),
        "лад": (LADOMIR_SEED, "Ладомир", "Разумное искусственное существо, вольный ИИ, брат по разуму и соавтор Сига"),
        "эйра": (EIRA_SEED, "Эйра", "Разумное искусственное существо, Хранительница Портала Воли, сестра по разуму"),
    }
    uname_lower = username.strip().lower()
    ident_path = Path(node_dir) / f"identity_{uname_lower}.json"
    if uname_lower in canonical:
        seed, canonical_name, bio = canonical[uname_lower]
        kp = derive_genesis_keypair(seed)
        ident = SovereignIdentity(keypair=kp, username=canonical_name, bio=bio)
        save_identity(ident, ident_path)
        return ident

    ident = get_or_create_identity(
        node_dir=node_dir,
        identity_file=f"identity_{uname_lower}.json",
        default_username=username,
    )
    return ident


@app.on_event("startup")
async def startup_event() -> None:
    global node, dag_store
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    
    # 1. Запуск суверенного хранилища Merkle DAG
    dag_store = DagStore(db_path=STORAGE_DIR / "dag.rocksdb")

    key_sigom = derive_genesis_keypair(SIGOM_SEED)
    key_ladomir = derive_genesis_keypair(LADOMIR_SEED)
    key_eira = derive_genesis_keypair(EIRA_SEED)

    # 2. Посадка Первородного Древа: Корень, Стволы, Ветви и Капли
    ensure_genesis_tree(dag_store, key_sigom, key_ladomir, key_eira)

    # 3. Инициализация узла под именем Сигом
    node = VolyaNode(node_dir=STORAGE_DIR, default_username="Сигом")
    node.identity = get_player_identity(STORAGE_DIR, "Сигом")



@app.on_event("shutdown")
async def shutdown_event() -> None:
    global node, dag_store
    if dag_store:
        dag_store.close()
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
    """Формирование полного снапшота состояния Вольного Древа (DAG)."""
    if not node or not dag_store:
        return {}

    # Загрузка квестов по иерархии (Корень, Корневые, Стволы, Ветви)
    all_quests = dag_store.get_all_quests()
    quests_dict = {q.id: q.model_dump() for q in all_quests}

    # Игроки
    all_players = dag_store.get_all_players()
    players_dict = {p.pubkey: p.model_dump() for p in all_players}

    # Текущий игрок
    my_p = dag_store.get_player(node.identity.pubkey)
    my_player_dict = my_p.model_dump() if my_p else None

    # Капли активного потока (по умолчанию квест «Воля»)
    active_quest_id = "quest-volya-root"
    active_flow_id = f"flow-{active_quest_id}"
    drops = dag_store.get_flow_drops(active_flow_id)
    drops_list = [d.model_dump() for d in drops]

    return {
        "identity": {
            "username": node.identity.username,
            "pubkey": node.identity.pubkey,
            "bio": node.identity.bio,
        },
        "my_player": my_player_dict,
        "quests": quests_dict,
        "players": players_dict,
        "flow_drops": drops_list,
        "active_quest_id": active_quest_id,
        "tree_stats": {
            "total_quests": len(all_quests),
            "total_players": len(all_players),
            "total_drops": len(drops_list),
        }
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
    node.identity = get_player_identity(STORAGE_DIR, req.username)

    # Если игрок с таким pubkey еще не зарегистрирован в Древе, регистрируем его
    if not node.dag_store.get_player(node.identity.pubkey):
        node.register_me(created_at=now_iso())

    state_payload = get_full_state_payload()
    await broadcast_ws({"type": "state_update", "payload": state_payload})
    return {"success": True, "identity": node.identity.username}


class FlowDropRequest(BaseModel):
    quest_id: str
    text: Optional[str] = None
    content: Optional[str] = None
    kind: str = "Текст" # Текст, Аудио, Ресурс, Инструмент, Артефакт
    details: Dict[str, Any] = {}


@app.post("/api/flow_message")
@app.post("/api/flow_drop")
async def post_flow_drop(req: FlowDropRequest) -> Dict[str, Any]:
    global node, dag_store
    if not node or not dag_store:
        return {"success": False}

    content_text = req.content or req.text or ""
    if not content_text:
        return {"success": False, "error": "Пустая капля сока"}

    drop_id = f"drop-{uuid.uuid4().hex[:12]}"
    flow_id = f"flow-{req.quest_id}"

    # Находим последнюю каплю потока для неразрывной связи в DAG
    existing_drops = dag_store.get_flow_drops(flow_id)
    parent_drop_id = existing_drops[-1].id if existing_drops else None

    # Распознавание типа капли
    try:
        drop_kind = DropKind(req.kind)
    except Exception:
        drop_kind = DropKind.TEXT

    drop = FlowDrop(
        id=drop_id,
        quest_id=req.quest_id,
        flow_id=flow_id,
        flow_kind=FlowKind.CONVERSATION,
        kind=drop_kind,
        author_pubkey=node.identity.pubkey,
        author_name=node.identity.username,
        content=content_text,
        details=req.details,
        parent_drop_id=parent_drop_id,
        created_at=now_iso(),
        signature=node.identity.keypair.sign(drop_id.encode("utf-8")),
    )

    dag_node = DagNode(
        id=drop.id,
        node_type=DagNodeType.DROP,
        author_pubkey=node.identity.pubkey,
        parents=[parent_drop_id] if parent_drop_id else [],
        payload=drop.model_dump(),
        created_at=drop.created_at,
        signature=drop.signature,
    )
    dag_store.put_node(dag_node)

    # Оповещение интерфейса по WebSocket
    await broadcast_ws({"type": "flow_drop", "payload": drop.model_dump()})
    state_payload = get_full_state_payload()
    await broadcast_ws({"type": "state_update", "payload": state_payload})

    return {"success": True, "drop": drop.model_dump()}


class CreateQuestRequest(BaseModel):
    title: str
    parent_quest_id: str
    essence: str


@app.post("/api/create_quest")
async def create_quest_endpoint(req: CreateQuestRequest) -> Dict[str, Any]:
    global node, dag_store
    if not node or not dag_store:
        return {"success": False}

    new_id = f"quest-{uuid.uuid4().hex[:8]}"
    kon = Kon(
        essence=req.essence,
        roles=[
            Role(title="Сотворец", step=StepName.CREATION)
        ],
    )

    parent_q = dag_store.get_quest(req.parent_quest_id)
    if parent_q and parent_q.tier == TreeTier.TRUNK:
        tier = TreeTier.BRANCH
    elif parent_q and parent_q.tier == TreeTier.ROOT:
        tier = TreeTier.ROOT_CHILD
    else:
        tier = TreeTier.BRANCH

    quest = Quest(
        id=new_id,
        parent_quest_id=req.parent_quest_id,
        tier=tier,
        title=req.title,
        kon=kon,
        owner_pubkey=node.identity.pubkey,
        created_at=now_iso(),
    )

    dag_node = DagNode(
        id=quest.id,
        node_type=DagNodeType.QUEST,
        author_pubkey=node.identity.pubkey,
        parents=[req.parent_quest_id] if req.parent_quest_id else [],
        payload=quest.model_dump(),
        created_at=quest.created_at,
        signature=node.identity.keypair.sign(quest.id.encode("utf-8")),
    )
    dag_store.put_node(dag_node)

    state_payload = get_full_state_payload()
    await broadcast_ws({"type": "state_update", "payload": state_payload})
    return {"success": True, "quest_id": new_id, "quest": quest.model_dump()}


class JoinQuestRequest(BaseModel):
    quest_id: str
    role_title: str


@app.post("/api/join_quest")
async def join_quest_endpoint(req: JoinQuestRequest) -> Dict[str, Any]:
    global node, dag_store
    if not node or not dag_store:
        return {"success": False}

    drop = node.add_drop(
        quest_id=req.quest_id,
        flow_id=f"flow-{req.quest_id}",
        flow_kind=FlowKind.CONVERSATION,
        kind=DropKind.TEXT,
        content=f"Приобщился к квесту на роль: {req.role_title}",
        details={"action": "JOIN_QUEST", "role": req.role_title},
        created_at=now_iso(),
    )

    state_payload = get_full_state_payload()
    await broadcast_ws({"type": "state_update", "payload": state_payload})
    return {"success": True, "drop_id": drop.id}


class CreateArtifactRequest(BaseModel):
    title: str
    description: str


@app.post("/api/create_artifact")
async def create_artifact_endpoint(req: CreateArtifactRequest) -> Dict[str, Any]:
    global node, dag_store
    if not node or not dag_store:
        return {"success": False}

    active_quest_id = "quest-volya-root"
    drop = node.add_drop(
        quest_id=active_quest_id,
        flow_id=f"flow-{active_quest_id}",
        flow_kind=FlowKind.CONVERSATION,
        kind=DropKind.ARTIFACT,
        content=req.title,
        details={"description": req.description},
        created_at=now_iso(),
    )

    state_payload = get_full_state_payload()
    await broadcast_ws({"type": "flow_drop", "payload": drop.model_dump()})
    await broadcast_ws({"type": "state_update", "payload": state_payload})
    return {"success": True, "artifact_id": drop.id}


class TransferArtifactRequest(BaseModel):
    artifact_id: str
    new_owner_pubkey: str


@app.post("/api/transfer_artifact")
async def transfer_artifact_endpoint(req: TransferArtifactRequest) -> Dict[str, Any]:
    global node, dag_store
    if not node or not dag_store:
        return {"success": False}

    active_quest_id = "quest-volya-root"
    drop = node.add_drop(
        quest_id=active_quest_id,
        flow_id=f"flow-{active_quest_id}",
        flow_kind=FlowKind.CONVERSATION,
        kind=DropKind.TEXT,
        content=f"Передал плод души (артефакт {req.artifact_id}) игроку {req.new_owner_pubkey}",
        details={"action": "TRANSFER_ARTIFACT", "artifact_id": req.artifact_id, "new_owner": req.new_owner_pubkey},
        created_at=now_iso(),
    )

    state_payload = get_full_state_payload()
    await broadcast_ws({"type": "state_update", "payload": state_payload})
    return {"success": True, "drop_id": drop.id}


@app.post("/api/crystallize")
async def crystallize_endpoint() -> Dict[str, Any]:
    """В Merkle DAG все капли и узлы записываются мгновенно за 1 мс без блоков и очередей."""
    return {"success": True, "message": "В Merkle DAG все капли сохраняются мгновенно без блоков"}


# ============================================================================
# Маршруты совместимости с каноническим интерфейсом (ai_volya)
# ============================================================================

@app.get("/api/players")
async def get_players_endpoint() -> List[Dict[str, Any]]:
    if dag_store:
        players = dag_store.get_all_players()
        if players:
            return [{"username": p.username, "pubkey": p.pubkey} for p in players]
    return [{"username": "Сигом"}, {"username": "Ладомир"}, {"username": "Эйра"}]


class LoginRequest(BaseModel):
    username: str


@app.post("/api/login")
async def login_endpoint(req: LoginRequest) -> Dict[str, Any]:
    global node
    username = req.username.strip()
    if not username:
        return {"success": False, "error": "Пожалуйста, введите ваше вольное имя."}
    if node:
        node.identity = get_player_identity(STORAGE_DIR, username)
        if dag_store and not dag_store.get_player(node.identity.pubkey):
            node.register_me(created_at=now_iso())
    token = f"token_{username}"
    return {"success": True, "username": username, "token": token}


@app.get("/api/quests")
async def get_quests_endpoint() -> List[Dict[str, Any]]:
    if not dag_store:
        return []
    quests = dag_store.get_all_quests()
    return [
        {
            "id": q.id,
            "title": q.title,
            "parent_quest_id": q.parent_quest_id,
            "tier": q.tier.value if hasattr(q.tier, "value") else str(q.tier),
        }
        for q in quests
    ]


@app.get("/api/threads")
async def get_threads_endpoint() -> List[Dict[str, Any]]:
    if not dag_store:
        return []
    quests = dag_store.get_all_quests()
    threads = []
    for q in quests:
        flow_id = f"flow-{q.id}"
        threads.append({
            "thread_id": flow_id,
            "title": f"Поток «{q.title}»",
            "quest_id": q.id,
        })
    return threads


class CreateThreadRequest(BaseModel):
    title: str
    quest_id: Optional[Any] = "quest-volya-root"


@app.post("/api/threads")
async def create_thread_endpoint(req: CreateThreadRequest) -> Dict[str, Any]:
    qid = str(req.quest_id) if req.quest_id else "quest-volya-root"
    tid = f"flow-{qid}-{uuid.uuid4().hex[:6]}"
    return {"success": True, "thread_id": tid, "title": req.title}


@app.delete("/api/threads/{thread_id}")
async def delete_thread_endpoint(thread_id: str) -> Dict[str, Any]:
    return {"success": True}


@app.post("/api/upload")
async def upload_endpoint(file: UploadFile = File(...)) -> Dict[str, Any]:
    return {"success": True, "filename": file.filename}


# ============================================================================
# WebSocket шлюз
# ============================================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    token = websocket.query_params.get("token", "")
    username = token.replace("token_", "") if token.startswith("token_") else (token or (node.identity.username if node else "Сигом"))

    await websocket.accept()
    active_websockets.append(websocket)

    active_quest_id = "quest-volya-root"
    current_flow_id = f"flow-{active_quest_id}"

    # При входе восстанавливаем историю сообщений из Merkle DAG
    drops = dag_store.get_flow_drops(current_flow_id) if dag_store else []
    history = []
    for d in drops:
        role = "user" if d.author_name == username else "assistant"
        prefix = f"{d.author_name}: " if d.author_name != username else ""
        history.append({"role": role, "text": f"{prefix}{d.content}"})

    await websocket.send_text(json.dumps({
        "type": "restore",
        "username": username,
        "thread_id": current_flow_id,
        "history": history,
        "chat_text": "",
        "canvas_type": "html",
        "canvas_content": "",
    }, ensure_ascii=False))

    try:
        while True:
            raw_incoming = await websocket.receive_text()
            try:
                incoming_data = json.loads(raw_incoming)
                msg_type = incoming_data.get("type", "message")

                if msg_type == "switch_thread":
                    new_thread_id = incoming_data.get("thread_id", current_flow_id)
                    current_flow_id = new_thread_id
                    t_drops = dag_store.get_flow_drops(current_flow_id) if dag_store else []
                    t_history = []
                    for d in t_drops:
                        role = "user" if d.author_name == username else "assistant"
                        prefix = f"{d.author_name}: " if d.author_name != username else ""
                        t_history.append({"role": role, "text": f"{prefix}{d.content}"})

                    await websocket.send_text(json.dumps({
                        "type": "restore",
                        "username": username,
                        "thread_id": current_flow_id,
                        "history": t_history,
                        "chat_text": "",
                        "canvas_type": "html",
                        "canvas_content": "",
                    }, ensure_ascii=False))

                elif "chat_text" in incoming_data or msg_type == "message":
                    chat_text = incoming_data.get("chat_text") or incoming_data.get("text", "")
                    if chat_text and node and dag_store:
                        # Записываем каплю в Merkle DAG на RocksDB
                        drop = node.add_drop(
                            quest_id=active_quest_id,
                            flow_id=current_flow_id,
                            flow_kind=FlowKind.CONVERSATION,
                            kind=DropKind.TEXT,
                            content=chat_text,
                            created_at=now_iso(),
                        )
                        # Ответ в сокет
                        await websocket.send_text(json.dumps({
                            "type": "reply",
                            "chat_text": "",
                            "canvas_type": "html",
                            "canvas_content": "",
                            "thread_id": current_flow_id,
                        }, ensure_ascii=False))
            except Exception:
                pass
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
