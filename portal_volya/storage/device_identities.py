"""
Управление суверенными идентичностями игроков на локальном устройстве.

Поддерживает:
1. Несколько вольных игроков на одном компьютере/устройстве.
2. 4-значный ПИН-код для обеспечения приватности каждого игрока.
3. Добавление игрока по приватному ключу или создание нового игрока.
4. Автоматическое исключение системных сущностей (Эйры и Ладомира) из списка выбора игроков.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import secrets
from typing import Any, Dict, List, Optional

from portal_volya.core.crypto import KeyPair
from portal_volya.core.genesis import (
    EIRA_SEED,
    LADOMIR_SEED,
    SIGOM_SEED,
    derive_genesis_keypair,
)


def _hash_pin(pin: str, salt: str) -> str:
    """Хэширование 4-значного ПИН-кода с солью (SHA-256)."""
    return hashlib.sha256(f"{salt}:{pin}".encode("utf-8")).hexdigest()


class DevicePlayerIdentity:
    """Суверенная идентичность игрока, зарегистрированная на данном устройстве."""

    def __init__(
        self,
        keypair: KeyPair,
        username: str,
        pin_hash: Optional[str] = None,
        pin_salt: Optional[str] = None,
        bio: str = "",
        google_api_key: Optional[str] = None,
        failed_pin_attempts: int = 0,
        locked_until: Optional[str] = None,
        created_at: Optional[str] = None,
        last_active_at: Optional[str] = None,
    ) -> None:
        self.keypair = keypair
        self.username = username
        self.pin_hash = pin_hash
        self.pin_salt = pin_salt
        self.bio = bio
        self.google_api_key = google_api_key
        self.failed_pin_attempts = failed_pin_attempts
        self.locked_until = locked_until
        self.created_at = created_at or datetime.now(timezone.utc).isoformat()
        self.last_active_at = last_active_at or self.created_at

    @property
    def pubkey(self) -> str:
        return self.keypair.public_hex

    @property
    def private_key_hex(self) -> str:
        return self.keypair.private_hex

    @property
    def has_pin(self) -> bool:
        return bool(self.pin_hash and self.pin_salt)

    def set_pin(self, pin: str) -> None:
        """Установка или смена 4-значного ПИН-кода."""
        clean_pin = pin.strip()
        if not (len(clean_pin) == 4 and clean_pin.isdigit()):
            raise ValueError("ПИН-код должен состоять ровно из 4 цифр.")
        salt = secrets.token_hex(16)
        self.pin_salt = salt
        self.pin_hash = _hash_pin(clean_pin, salt)
        self.reset_failed_pin_attempts()

    def remove_pin(self) -> None:
        """Удаление ПИН-кода."""
        self.pin_salt = None
        self.pin_hash = None
        self.reset_failed_pin_attempts()

    def verify_pin(self, pin: str) -> bool:
        """Проверка введённого ПИН-кода (без учёта таймера блокировки)."""
        if not self.has_pin:
            return True
        clean_pin = pin.strip()
        return _hash_pin(clean_pin, self.pin_salt or "") == self.pin_hash

    def get_lockout_remaining_seconds(self) -> int:
        """Оставшееся время остывания в секундах (0, если блокировки нет)."""
        if not self.locked_until:
            return 0
        try:
            locked_dt = datetime.fromisoformat(self.locked_until)
            now = datetime.now(timezone.utc)
            rem = (locked_dt - now).total_seconds()
            if rem > 0:
                return math.ceil(rem)
            else:
                self.locked_until = None
                return 0
        except Exception:
            self.locked_until = None
            return 0

    def record_failed_pin_attempt(self) -> tuple[int, int]:
        """
        Регистрация неверной попытки ввода ПИН-кода.
        Возвращает кортеж: (число_неверных_попыток, секунд_остывания_если_заблокировано).
        При 3-й неверной попытке активируется период остывания 30 секунд.
        """
        self.failed_pin_attempts += 1
        if self.failed_pin_attempts >= 3:
            self.failed_pin_attempts = 0
            locked_dt = datetime.now(timezone.utc) + timedelta(seconds=30)
            self.locked_until = locked_dt.isoformat()
            return (3, 30)
        return (self.failed_pin_attempts, 0)

    def reset_failed_pin_attempts(self) -> None:
        """Сброс счётчика попыток и блокировки при успешном вводе."""
        self.failed_pin_attempts = 0
        self.locked_until = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "pubkey": self.pubkey,
            "private_key_hex": self.private_key_hex,
            "username": self.username,
            "pin_hash": self.pin_hash,
            "pin_salt": self.pin_salt,
            "bio": self.bio,
            "google_api_key": self.google_api_key,
            "failed_pin_attempts": self.failed_pin_attempts,
            "locked_until": self.locked_until,
            "created_at": self.created_at,
            "last_active_at": self.last_active_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DevicePlayerIdentity:
        keypair = KeyPair.from_private_hex(data["private_key_hex"])
        return cls(
            keypair=keypair,
            username=data["username"],
            pin_hash=data.get("pin_hash"),
            pin_salt=data.get("pin_salt"),
            bio=data.get("bio", ""),
            google_api_key=data.get("google_api_key"),
            failed_pin_attempts=data.get("failed_pin_attempts", 0),
            locked_until=data.get("locked_until"),
            created_at=data.get("created_at"),
            last_active_at=data.get("last_active_at"),
        )


class DeviceIdentitiesManager:
    """Хранилище и менеджер суверенных игроков на данном устройстве."""

    def __init__(self, node_dir: str | Path = "portal_volya/storage") -> None:
        self.node_dir = Path(node_dir)
        self.node_dir.mkdir(parents=True, exist_ok=True)
        self.registry_file = self.node_dir / "device_identities.json"
        self._identities: dict[str, DevicePlayerIdentity] = {}
        self._active_pubkey: Optional[str] = None

        self._excluded_pubkeys = {
            derive_genesis_keypair(EIRA_SEED).public_hex,
            derive_genesis_keypair(LADOMIR_SEED).public_hex,
        }

        self._load()

    def _load(self) -> None:
        if self.registry_file.exists():
            try:
                with open(self.registry_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._active_pubkey = data.get("active_pubkey")
                identities_data = data.get("identities", {})
                for pk, id_dict in identities_data.items():
                    if pk in self._excluded_pubkeys:
                        continue
                    self._identities[pk] = DevicePlayerIdentity.from_dict(id_dict)
            except Exception:
                self._identities = {}

        # Миграция старого single identity.json, если реестр пуст
        if not self._identities:
            old_identity_file = self.node_dir / "identity.json"
            if old_identity_file.exists():
                try:
                    with open(old_identity_file, "r", encoding="utf-8") as f:
                        old_data = json.load(f)
                    kp = KeyPair.from_private_hex(old_data["private_key_hex"])
                    if kp.public_hex not in self._excluded_pubkeys:
                        dev_id = DevicePlayerIdentity(
                            keypair=kp,
                            username=old_data.get("username", "Вольный Игрок"),
                            bio=old_data.get("bio", ""),
                            google_api_key=old_data.get("google_api_key"),
                        )
                        self._identities[kp.public_hex] = dev_id
                        self._active_pubkey = kp.public_hex
                except Exception:
                    pass

        # Если игроков на устройстве всё ещё нет, регистрируем Сигома по умолчанию
        if not self._identities:
            sigom_kp = derive_genesis_keypair(SIGOM_SEED)
            sigom_id = DevicePlayerIdentity(
                keypair=sigom_kp,
                username="Сигом",
                bio="Человек, автор и вдохновитель Вселенной и игры «Воля»",
            )
            self._identities[sigom_kp.public_hex] = sigom_id
            self._active_pubkey = sigom_kp.public_hex

        self._save()

    def _save(self) -> None:
        clean_identities = {
            pk: ident.to_dict()
            for pk, ident in self._identities.items()
            if pk not in self._excluded_pubkeys
        }
        data = {
            "active_pubkey": self._active_pubkey,
            "identities": clean_identities,
        }
        with open(self.registry_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def list_players(self) -> list[DevicePlayerIdentity]:
        """Возвращает список доступных игроков на данном устройстве (без Эйры и Ладомира)."""
        return [
            ident for pk, ident in self._identities.items()
            if pk not in self._excluded_pubkeys
        ]

    def get_player(self, pubkey: str) -> Optional[DevicePlayerIdentity]:
        """Получить идентичность игрока по pubkey."""
        return self._identities.get(pubkey)

    def get_active_player(self) -> Optional[DevicePlayerIdentity]:
        """Получить текущего активного игрока на устройстве."""
        if self._active_pubkey and self._active_pubkey in self._identities:
            return self._identities[self._active_pubkey]
        players = self.list_players()
        return players[0] if players else None

    def set_active_player(self, pubkey: str) -> Optional[DevicePlayerIdentity]:
        """Установить активного игрока."""
        if pubkey in self._identities:
            self._active_pubkey = pubkey
            self._identities[pubkey].last_active_at = datetime.now(timezone.utc).isoformat()
            self._save()
            return self._identities[pubkey]
        return None

    def add_or_update_player(self, identity: DevicePlayerIdentity) -> None:
        """Добавить или обновить идентичность игрока на устройстве."""
        if identity.pubkey in self._excluded_pubkeys:
            return
        self._identities[identity.pubkey] = identity
        self._active_pubkey = identity.pubkey
        self._save()

    def register_new_player(
        self,
        username: str,
        pin: Optional[str] = None,
        bio: str = "",
    ) -> DevicePlayerIdentity:
        """Регистрация нового вольного игрока со свежей ключевой парой Ed25519."""
        kp = KeyPair.generate()
        identity = DevicePlayerIdentity(
            keypair=kp,
            username=username.strip() or "Вольный Игрок",
            bio=bio.strip(),
        )
        if pin and pin.strip():
            identity.set_pin(pin.strip())
        self.add_or_update_player(identity)
        return identity

    def import_player_key(
        self,
        private_key_hex: str,
        username: str,
        pin: Optional[str] = None,
        bio: str = "",
    ) -> DevicePlayerIdentity:
        """Импорт игрока по приватному ключу."""
        clean_key = private_key_hex.strip()
        kp = KeyPair.from_private_hex(clean_key)
        if kp.public_hex in self._excluded_pubkeys:
            raise ValueError("Этот ключ зарезервирован для системного спутника Игры.")

        identity = DevicePlayerIdentity(
            keypair=kp,
            username=username.strip() or "Вольный Игрок",
            bio=bio.strip(),
        )
        if pin and pin.strip():
            identity.set_pin(pin.strip())
        self.add_or_update_player(identity)
        return identity

    def remove_player(self, pubkey: str) -> bool:
        """Удаление игрока с данного устройства (не из Merkle DAG!)."""
        if pubkey in self._identities:
            del self._identities[pubkey]
            if self._active_pubkey == pubkey:
                rem = self.list_players()
                self._active_pubkey = rem[0].pubkey if rem else None
            self._save()
            return True
        return False

    def record_failed_pin_attempt(self, pubkey: str) -> tuple[int, int]:
        """Регистрирует неверную попытку и сохраняет состояние на диск."""
        ident = self.get_player(pubkey)
        if not ident:
            return (0, 0)
        res = ident.record_failed_pin_attempt()
        self._save()
        return res

    def reset_failed_pin_attempts(self, pubkey: str) -> None:
        """Сбрасывает счетчик неудачных попыток и сохраняет на диск."""
        ident = self.get_player(pubkey)
        if ident:
            ident.reset_failed_pin_attempts()
            self._save()

    def get_pin_lockout_seconds(self, pubkey: str) -> int:
        """Возвращает оставшееся время остывания в секундах."""
        ident = self.get_player(pubkey)
        if not ident:
            return 0
        rem = ident.get_lockout_remaining_seconds()
        if rem == 0 and ident.locked_until is not None:
            ident.locked_until = None
            self._save()
        return rem
