"""
Криптографический фундамент децентрализованного узла «Воля».

Канонические принципы:
1. Ed25519 — асимметричные ключи вольного игрока, подпись капель, квестов и волеизъявлений.
2. Blake3 — сверхбыстрое криптографическое хэширование узлов Merkle DAG, капель сока и медиа-контента.
3. Канонический JSON (RFC 8785) — детерминированная сериализация для вычисления идентичных
   хэшей на всех узлах сети независимо от платформы.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any
import blake3
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

# Константа поля кривой Curve25519 (2^255 - 19)
P_25519 = 2**255 - 19

# Префикс формата зашифрованных капель в Вольном Древе
ENCRYPTED_PREFIX = "enc:v1:"


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


def ed25519_pub_to_x25519(ed_pub_bytes: bytes) -> bytes:
    """
    Преобразование открытого ключа Ed25519 (точка на Edwards curve)
    в открытый ключ X25519 (точка на Montgomery curve Curve25519)
    по канонической формуле бирациональной эквивалентности:
    u = (1 + y) / (1 - y) mod (2^255 - 19).
    """
    y = int.from_bytes(ed_pub_bytes, "little") & ((1 << 255) - 1)
    u = ((1 + y) * pow(1 - y, P_25519 - 2, P_25519)) % P_25519
    return u.to_bytes(32, "little")


def ed25519_seed_to_x25519_private(raw_seed: bytes) -> X25519PrivateKey:
    """
    Детерминированное выведение закрытого ключа X25519 из сырого сида Ed25519 (32 байта)
    согласно RFC 8032 / RFC 7748.
    """
    h = hashlib.sha512(raw_seed).digest()
    scalar = bytearray(h[:32])
    scalar[0] &= 248
    scalar[31] &= 127
    scalar[31] |= 64
    return X25519PrivateKey.from_private_bytes(bytes(scalar))


class KeyPair:
    """Суверенная пара ключей игрока (Ed25519 для подписи + X25519 для шифрования)."""

    def __init__(self, private_key: Ed25519PrivateKey, raw_seed: bytes | None = None) -> None:
        self._private_key = private_key
        self._public_key = private_key.public_key()
        if raw_seed is not None:
            self._raw_seed = raw_seed
        else:
            self._raw_seed = private_key.private_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PrivateFormat.Raw,
                encryption_algorithm=serialization.NoEncryption(),
            )

    @classmethod
    def generate(cls) -> KeyPair:
        """Порождение новой первородной пары ключей."""
        priv = Ed25519PrivateKey.generate()
        return cls(priv)

    @classmethod
    def from_private_hex(cls, private_hex: str) -> KeyPair:
        """Восстановление пары ключей из шестнадцатеричного сырого сида (32 байта)."""
        raw = bytes.fromhex(private_hex)
        return cls(Ed25519PrivateKey.from_private_bytes(raw), raw_seed=raw)

    @property
    def raw_seed(self) -> bytes:
        """32-байтный сырой сид закрытого ключа."""
        return self._raw_seed

    @property
    def private_hex(self) -> str:
        """Шестнадцатеричное представление закрытого ключа (хранится строго локально!)."""
        return self._raw_seed.hex()

    @property
    def public_hex(self) -> str:
        """Шестнадцатеричное представление открытого ключа (pubkey / адрес игрока в Воле)."""
        raw = self._public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return raw.hex()

    @property
    def x25519_private_key(self) -> X25519PrivateKey:
        """Детерминированный приватный ключ X25519 для Diffie-Hellman обмена."""
        return ed25519_seed_to_x25519_private(self._raw_seed)

    @property
    def encryption_public_hex(self) -> str:
        """Шестнадцатеричное представление открытого ключа X25519 для шифрования."""
        x_pub = self.x25519_private_key.public_key()
        raw = x_pub.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return raw.hex()

    def diffie_hellman_shared(self, peer_ed25519_pubkey_hex: str) -> bytes:
        """
        Вычисление общего секрета (shared secret) с другим вольным игроком.
        Принимает канонический Ed25519 открытый ключ собеседника.
        """
        peer_ed_bytes = bytes.fromhex(peer_ed25519_pubkey_hex)
        peer_x_bytes = ed25519_pub_to_x25519(peer_ed_bytes)
        peer_x_pub = X25519PublicKey.from_public_bytes(peer_x_bytes)
        return self.x25519_private_key.exchange(peer_x_pub)

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


# =====================================================================
# ВЫВЕДЕНИЕ СИММЕТРИЧНЫХ КЛЮЧЕЙ И ШИФРОВАНИЕ КАПЕЛЬ СОКА ДРЕВА
# =====================================================================

def derive_dialogue_key(my_keypair: KeyPair, peer_pubkey_hex: str) -> bytes:
    """
    Выведение 256-битного симметричного ключа для сквозного E2EE-диалога двух вольных игроков
    через X25519 Diffie-Hellman + HKDF-SHA256.
    """
    if my_keypair.public_hex == peer_pubkey_hex:
        # Диалог с самим собой (суверенные путевые заметки игрока)
        shared = my_keypair.raw_seed
        info = b"volya_self_dialogue_v1"
    else:
        shared = my_keypair.diffie_hellman_shared(peer_pubkey_hex)
        info = b"volya_dialogue_e2ee_v1"

    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=info,
    ).derive(shared)


def derive_conversation_key(quest_id: str) -> bytes:
    """
    Выведение 256-битного симметричного ключа для беседы внутри квеста.
    Защищает капли беседы от посторонних вне Воли в общей распределенной базе RocksDB.
    """
    info = f"volya_conversation_v1:{quest_id}".encode("utf-8")
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=info,
    ).derive(b"volya_free_tree_realm")


def symmetric_encrypt(key_32b: bytes, plaintext: bytes) -> str:
    """
    Шифрование произвольных байт алгоритмом ChaCha20-Poly1305.
    Возвращает строку формата 'enc:v1:<nonce_hex>:<ciphertext_hex>'.
    """
    nonce = os.urandom(12)
    cipher = ChaCha20Poly1305(key_32b)
    ciphertext = cipher.encrypt(nonce, plaintext, None)
    return f"{ENCRYPTED_PREFIX}{nonce.hex()}:{ciphertext.hex()}"


def symmetric_decrypt(key_32b: bytes, payload_str: str) -> bytes:
    """
    Расшифрование строки формата 'enc:v1:<nonce_hex>:<ciphertext_hex>'.
    Если строка не зашифрована (без префикса), возвращается как utf-8 байты.
    """
    if not payload_str.startswith(ENCRYPTED_PREFIX):
        return payload_str.encode("utf-8")

    body = payload_str[len(ENCRYPTED_PREFIX):]
    parts = body.split(":")
    if len(parts) != 2:
        raise ValueError("Неверный формат зашифрованной капли")

    nonce = bytes.fromhex(parts[0])
    ciphertext = bytes.fromhex(parts[1])
    cipher = ChaCha20Poly1305(key_32b)
    return cipher.decrypt(nonce, ciphertext, None)


def encrypt_drop_content(content: str, key_32b: bytes) -> str:
    """Шифрование текстового содержания капли сока Древа."""
    return symmetric_encrypt(key_32b, content.encode("utf-8"))


def decrypt_drop_content(encrypted_content: str, key_32b: bytes) -> str:
    """Расшифрование текстового содержания капли сока Древа в чистый текст."""
    if not encrypted_content.startswith(ENCRYPTED_PREFIX):
        return encrypted_content
    decrypted_bytes = symmetric_decrypt(key_32b, encrypted_content)
    return decrypted_bytes.decode("utf-8")

