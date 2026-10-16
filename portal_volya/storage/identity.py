"""
Суверенная идентичность вольного игрока на локальном узле «Воля».

Идентичность состоит из криптографической пары ключей Ed25519, вольного имени и био.
Хранится в локальном файле identity.json на устройстве игрока.
Никаких внешних серверов или баз данных — только суверенная воля игрока.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from portal_volya.core.crypto import (
    KeyPair,
    derive_conversation_key,
    derive_dialogue_key,
    encrypt_drop_content,
    hash_canonical,
)
from portal_volya.core.models import DropKind, FlowDrop, FlowKind


class SovereignIdentity:
    """Суверенная идентичность вольного игрока на локальном устройстве."""

    def __init__(
        self,
        keypair: KeyPair,
        username: str,
        bio: str = "",
        google_api_key: Optional[str] = None,
    ) -> None:
        self.keypair = keypair
        self.username = username
        self.bio = bio
        self.google_api_key = google_api_key

    @property
    def pubkey(self) -> str:
        return self.keypair.public_hex

    def to_dict(self) -> dict:
        data = {
            "private_key_hex": self.keypair.private_hex,
            "public_key_hex": self.keypair.public_hex,
            "username": self.username,
            "bio": self.bio,
        }
        if self.google_api_key:
            data["google_api_key"] = self.google_api_key
        return data

    @classmethod
    def from_dict(cls, data: dict) -> SovereignIdentity:
        keypair = KeyPair.from_private_hex(data["private_key_hex"])
        return cls(
            keypair=keypair,
            username=data["username"],
            bio=data.get("bio", ""),
            google_api_key=data.get("google_api_key"),
        )


def load_identity(identity_path: Path | str) -> Optional[SovereignIdentity]:
    """Загрузка суверенной идентичности из файла."""
    path = Path(identity_path)
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return SovereignIdentity.from_dict(data)


def save_identity(identity: SovereignIdentity, identity_path: Path | str) -> None:
    """Сохранение суверенной идентичности в файл."""
    path = Path(identity_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(identity.to_dict(), f, ensure_ascii=False, indent=2)


def get_or_create_identity(
    node_dir: Path | str = "portal_volya/storage",
    identity_file: str = "identity.json",
    default_username: str = "Вольный Игрок",
    default_bio: str = "Рождён на узле «Воля»",
) -> SovereignIdentity:
    """Получить существующую идентичность или сгенерировать новую пару ключей."""
    path = Path(node_dir) / identity_file
    existing = load_identity(path)
    if existing:
        return existing

    kp = KeyPair.generate()
    identity = SovereignIdentity(keypair=kp, username=default_username, bio=default_bio)
    save_identity(identity, path)
    return identity


def create_flow_drop(
    sender: KeyPair,
    author_name: str,
    content: str,
    created_at: str,
    flow_id: str = "",
    quest_id: str = "",
    flow_kind: FlowKind = FlowKind.DIALOGUE,
    kind: DropKind = DropKind.TEXT,
    recipients: Optional[list[str]] = None,
    details: Optional[Dict[str, Any]] = None,
    media_hash: Optional[str] = None,
    parent_drop_id: Optional[str] = None,
    encrypt: bool = True,
) -> FlowDrop:
    """Создание и подписание канонической капли сотворчества с шифрованием по Ладу."""
    recs = recipients or []
    stored_content = content

    if encrypt:
        if flow_kind == FlowKind.DIALOGUE:
            peer_pk = None
            for r in recs:
                if r != sender.public_hex:
                    peer_pk = r
                    break
            if not peer_pk:
                peer_pk = sender.public_hex
            key = derive_dialogue_key(sender, peer_pk)
            stored_content = encrypt_drop_content(content, key)
        else:
            key = derive_conversation_key(quest_id)
            stored_content = encrypt_drop_content(content, key)

    drop_body = {
        "quest_id": quest_id,
        "flow_id": flow_id,
        "flow_kind": flow_kind.value if hasattr(flow_kind, "value") else str(flow_kind),
        "kind": kind.value if hasattr(kind, "value") else str(kind),
        "author_pubkey": sender.public_hex,
        "author_name": author_name,
        "recipients": recs,
        "content": stored_content,
        "details": details or {},
        "media_hash": media_hash,
        "parent_drop_id": parent_drop_id,
        "created_at": created_at,
    }
    drop_id = hash_canonical(drop_body)
    signature = sender.sign(drop_id.encode("utf-8"))
    return FlowDrop(
        id=drop_id,
        quest_id=quest_id,
        flow_id=flow_id,
        flow_kind=flow_kind,
        kind=kind,
        author_pubkey=sender.public_hex,
        author_name=author_name,
        recipients=recs,
        content=stored_content,
        details=details or {},
        media_hash=media_hash,
        parent_drop_id=parent_drop_id,
        created_at=created_at,
        signature=signature,
    )
