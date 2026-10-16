"""
Бинарный протокол P2P сети «Воля» для синхронизации Merkle DAG (Вольного Древа).

Формат кадра (Frame):
┌─────────────────────────┬───────────────────┬────────────────────────────────┐
│ Длина полезной нагрузки │ Тип сообщения     │ Полезная нагрузка (Payload)    │
│ (4 байта uint32 BE)     │ (1 байт uint8)    │ (MessagePack бинарный кадр)    │
└─────────────────────────┴───────────────────┴────────────────────────────────┘
"""

from __future__ import annotations

import asyncio
import struct
from enum import IntEnum
from typing import Any, Tuple

import ormsgpack


HEADER_FORMAT = "!IB"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
MAX_PAYLOAD_SIZE = 64 * 1024 * 1024  # 64 MB максимум на один кадр


class MessageType(IntEnum):
    HANDSHAKE = 1         # Обмен суверенными открытыми ключами и подписью времени
    HANDSHAKE_ACK = 2     # Подтверждение рукопожатия и взаимная авторизация
    SYNC_HEADS = 3        # Обмен верхушками ветвей Древа (хэши последних узлов)
    GET_DAG_NODES = 4     # Запрос списка недостающих узлов DAG по их хэшам
    DAG_NODES_BATCH = 5   # Ответ с набором бинарных узлов DAG
    BROADCAST_NODE = 6    # Волна Потока: распространение нового узла DAG (капля, квест)
    PING = 7              # Пульс проверки жизнеспособности соединения
    PONG = 8              # Эхо-ответ на пульс


async def write_frame(
    writer: asyncio.StreamWriter,
    msg_type: MessageType | int,
    payload: dict[str, Any],
) -> None:
    """Сериализация и отправка бинарного кадра в сетевой поток."""
    raw_payload = ormsgpack.packb(payload)
    payload_len = len(raw_payload)
    if payload_len > MAX_PAYLOAD_SIZE:
        raise ValueError(f"Размер кадра превышает допустимый предел ({payload_len} > {MAX_PAYLOAD_SIZE})")

    header = struct.pack(HEADER_FORMAT, payload_len, int(msg_type))
    writer.write(header + raw_payload)
    await writer.drain()


async def read_frame(reader: asyncio.StreamReader) -> Tuple[int, dict[str, Any]]:
    """Чтение и десериализация бинарного кадра из сетевого потока."""
    header_bytes = await reader.readexactly(HEADER_SIZE)
    payload_len, msg_type = struct.unpack(HEADER_FORMAT, header_bytes)

    if payload_len > MAX_PAYLOAD_SIZE:
        raise ValueError(f"Получен недопустимо большой кадр: {payload_len} байт")

    payload_bytes = await reader.readexactly(payload_len)
    payload = ormsgpack.unpackb(payload_bytes)
    return msg_type, payload
