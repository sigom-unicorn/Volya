"""
Криптографический фундамент децентрализованного узла «Воля».

Канонические принципы:
1. Ed25519 — асимметричные ключи вольного игрока, подпись транзакций и сообщений.
2. Blake3 — сверхбыстрое криптографическое хэширование блоков, транзакций и медиа-контента.
3. Канонический JSON (RFC 8785) — детерминированная сериализация для вычисления идентичных
   хэшей на всех узлах сети независимо от платформы.
"""

from __future__ import annotations

import json
from typing import Any
import blake3
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


def canonical_json_bytes(data: Any) -> bytes:
    """
    Детерминированная каноническая сериализация данных в JSON (RFC 8785 совместимая).
    Сортировка ключей, удаление лишних пробелов, строгий UTF-8 без экранирования кириллицы.
    """
    return json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def hash_bytes(data: bytes) -> str:
    """Вычисление 256-битного (32 байта) хэша Blake3 в шестнадцатеричном виде."""
    hasher = blake3.blake3(data)
    return hasher.hexdigest()


def hash_canonical(data: Any) -> str:
    """Каноническое хэширование произвольной структуры данных через Blake3."""
    return hash_bytes(canonical_json_bytes(data))


def hash_file(file_path: str, chunk_size: int = 65536) -> str:
    """Потоковое вычисление Blake3 хэша файла любого объёма."""
    hasher = blake3.blake3()
    with open(file_path, "rb") as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest()


class KeyPair:
    """Суверенная пара ключей игрока (Ed25519)."""

    def __init__(self, private_key: Ed25519PrivateKey) -> None:
        self._private_key = private_key
        self._public_key = private_key.public_key()

    @classmethod
    def generate(cls) -> KeyPair:
        """Порождение новой первородной пары ключей."""
        return cls(Ed25519PrivateKey.generate())

    @classmethod
    def from_private_hex(cls, private_hex: str) -> KeyPair:
        """Восстановление пары ключей из шестнадцатеричного сырого сида (32 байта)."""
        raw = bytes.fromhex(private_hex)
        return cls(Ed25519PrivateKey.from_private_bytes(raw))

    @property
    def private_hex(self) -> str:
        """Шестнадцатеричное представление закрытого ключа (хранится строго локально!)."""
        from cryptography.hazmat.primitives import serialization

        raw = self._private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
        return raw.hex()

    @property
    def public_hex(self) -> str:
        """Шестнадцатеричное представление открытого ключа (pubkey / адрес игрока)."""
        from cryptography.hazmat.primitives import serialization

        raw = self._public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return raw.hex()

    def sign(self, message: bytes) -> str:
        """Подпись произвольных байт закрытым ключом Ed25519 (возвращает hex подписи)."""
        signature = self._private_key.sign(message)
        return signature.hex()

    def sign_canonical(self, data: Any) -> str:
        """Подпись канонической структуры данных."""
        return self.sign(canonical_json_bytes(data))


def verify_signature(public_hex: str, message: bytes, signature_hex: str) -> bool:
    """
    Проверка подписи сообщения открытым ключом Ed25519.
    Возвращает True при подлинности, иначе False.
    """
    try:
        pub_raw = bytes.fromhex(public_hex)
        sig_raw = bytes.fromhex(signature_hex)
        public_key = Ed25519PublicKey.from_public_bytes(pub_raw)
        public_key.verify(sig_raw, message)
        return True
    except (ValueError, InvalidSignature):
        return False


def verify_canonical(public_hex: str, data: Any, signature_hex: str) -> bool:
    """Проверка подписи канонической структуры данных."""
    return verify_signature(public_hex, canonical_json_bytes(data), signature_hex)
