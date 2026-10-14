"""
Комплексные тесты рантайма VolyaNode и децентрализованной P2P сети «Воля».

Проверяет:
1. Жизненный цикл VolyaNode: мемпул, волеизъявления, кристаллизация блоков, персистентность в RocksDB.
2. Сетевое рукопожатие по Ed25519 (взаимная авторизация узлов).
3. Распространение неподтвержденных транзакций через волну Gossip.
4. Распространение новых блоков и мгновенное достижение 100% консенсуса.
5. Автоматическую синхронизацию отстающего узла (Chain Sync).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import pytest

from portal_volya.core.genesis import build_genesis_block
from portal_volya.core.models import Kon, Lad, Role, StepName, Task
from portal_volya.node import VolyaNode
from portal_volya.p2p.network import P2PNetwork


def test_volya_node_lifecycle(tmp_path: Path):
    """Тест автономного рантайма VolyaNode, Пула Лада и кузницы блоков."""
    node_dir = tmp_path / "node_alpha"

    with VolyaNode(node_dir=node_dir, default_username="Ярослав") as node:
        # 1. При рождении узел поднимает Генезис-Блок №0
        assert node.height == 1
        assert node.latest_block_hash == "fb81100b89f9bdf5281b2255ff5020706425ba2da468f909f50fd102fd13d7ae"
        assert len(node.mempool) == 0

        # 2. Волеизъявление на регистрацию игрока
        tx_reg = node.register_me(created_at="2026-10-14T12:00:00Z")
        assert len(node.mempool) == 1
        assert node.mempool[0].id == tx_reg.id

        # 3. Кристаллизация Блока №1 первородными подписями
        _, keypairs = build_genesis_block()
        sigom = keypairs["sigom"]
        lad = keypairs["ladomir"]

        block1 = node.crystallize_block(
            timestamp="2026-10-14T12:05:00Z",
            signers=[sigom, lad],
        )

        assert block1 is not None
        assert block1.index == 1
        assert node.height == 2
        assert len(node.mempool) == 0  # Мемпул очищен
        assert node.identity.pubkey in node.ledger.state.players
        assert node.my_player is not None
        assert node.my_player.username == "Ярослав"

    # 4. Проверка холодного рестарта: поднимаем новый экземпляр из той же папки
    with VolyaNode(node_dir=node_dir) as node_reopened:
        assert node_reopened.height == 2
        assert node_reopened.identity.username == "Ярослав"
        assert node_reopened.my_player is not None


@pytest.mark.asyncio
async def test_p2p_network_sync_and_gossip(tmp_path: Path):
    """
    Интеграционный тест P2P сети:
    Узел А (Сигом) и Узел Б (Ладомир) соединяются по сети, обмениваются транзакциями,
    запечатывают блоки и синхронизируют цепочку с третьим узлом В (Ученик).
    """
    _, keypairs = build_genesis_block()
    sigom_kp = keypairs["sigom"]
    lad_kp = keypairs["ladomir"]

    dir_a = tmp_path / "node_a"
    dir_b = tmp_path / "node_b"
    dir_c = tmp_path / "node_c"

    node_a = VolyaNode(node_dir=dir_a, default_username="Сигом")
    node_a.identity.keypair = sigom_kp

    node_b = VolyaNode(node_dir=dir_b, default_username="Ладомир")
    node_b.identity.keypair = lad_kp

    node_c = VolyaNode(node_dir=dir_c, default_username="Ученик")

    p2p_a = P2PNetwork(node=node_a, host="127.0.0.1", port=9111)
    p2p_b = P2PNetwork(node=node_b, host="127.0.0.1", port=9112)
    p2p_c = P2PNetwork(node=node_c, host="127.0.0.1", port=9113)

    try:
        # 1. Запуск P2P серверов
        await p2p_a.start()
        await p2p_b.start()
        await p2p_c.start()

        # 2. Узел Б подключается к Узлу А (Криптографическое рукопожатие по Ed25519)
        peer = await p2p_b.connect_to_peer("127.0.0.1", 9111)
        assert peer is not None
        assert peer.pubkey == sigom_kp.public_hex
        assert peer.username == "Сигом"

        await asyncio.sleep(0.05)  # Небольшая пауза для завершения регистрации на стороне А
        assert lad_kp.public_hex in p2p_a.peers

        # 3. Тест Gossip транзакции: Сигом на узле А создает транзакцию создания артефакта
        tx_art = node_a.create_artifact(
            artifact_id="art_p2p_crystal_01",
            title="Кристалл Связи",
            description="Плод души, переданный по P2P сети",
            created_at="2026-10-14T12:10:00Z",
        )
        assert len(node_a.mempool) == 1
        assert len(node_b.mempool) == 0

        # Рассылаем волну Gossip
        await p2p_a.broadcast_transaction(tx_art)
        await asyncio.sleep(0.05)

        # Проверяем: узел Б принял транзакцию в свой Пул Лада!
        assert len(node_b.mempool) == 1
        assert node_b.mempool[0].id == tx_art.id

        # 4. Тест кристаллизации и распространения блока
        block1 = node_a.crystallize_block(
            timestamp="2026-10-14T12:15:00Z",
            signers=[sigom_kp, lad_kp],
        )
        assert block1 is not None
        assert node_a.height == 2

        # Рассылаем блок по сети
        await p2p_a.broadcast_block(block1)
        await asyncio.sleep(0.05)

        # Проверяем: узел Б принял блок, записал в RocksDB и обновил высоту!
        assert node_b.height == 2
        assert node_b.latest_block_hash == node_a.latest_block_hash
        assert len(node_b.mempool) == 0  # Мемпул на узле Б тоже очищен

        # 5. Тест Chain Sync: Новый Узел В (высота 1) подключается к Узлу А (высота 2)
        assert node_c.height == 1
        peer_ca = await p2p_c.connect_to_peer("127.0.0.1", 9111)
        assert peer_ca is not None

        # Ждем синхронизации блоков
        await asyncio.sleep(0.1)

        # Узел В докачал недостающие блоки и достиг консенсуса!
        assert node_c.height == 2
        assert node_c.latest_block_hash == node_a.latest_block_hash

    finally:
        # Корректная остановка
        await p2p_c.stop()
        await p2p_b.stop()
        await p2p_a.stop()
        node_c.close()
        node_b.close()
        node_a.close()
