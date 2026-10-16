"""
Тестирование криптографической защиты и шифрования капель сока Вольного Древа.

Канонические принципы:
1. Капли E2EE-диалогов доступны и читаемы только участниками диалога (Ed25519 -> X25519 ECDH + HKDF + ChaCha20Poly1305).
2. Капли бесед квеста зашифрованы ключом квеста, защищая сокровенное пространство от посторонних вне Воли.
3. В распределенной базе RocksDB и при передаче в DAG ни одна капля не хранится в открытом виде.
"""

from pathlib import Path
import shutil
import tempfile
import pytest

from cryptography.exceptions import InvalidTag
from portal_volya.core.crypto import (
    ENCRYPTED_PREFIX,
    KeyPair,
    decrypt_drop_content,
    derive_conversation_key,
    derive_dialogue_key,
    encrypt_drop_content,
    symmetric_decrypt,
    symmetric_encrypt,
)
from portal_volya.core.models import DropKind, FlowKind
from portal_volya.node import VolyaNode
from portal_volya.storage.identity import SovereignIdentity


def test_diffie_hellman_symmetry():
    """Проверка идеальной симметрии обмена ключами между вольными игроками."""
    kp_alice = KeyPair.generate()
    kp_bob = KeyPair.generate()
    kp_eva = KeyPair.generate()

    shared_ab = kp_alice.diffie_hellman_shared(kp_bob.public_hex)
    shared_ba = kp_bob.diffie_hellman_shared(kp_alice.public_hex)

    assert shared_ab == shared_ba
    assert len(shared_ab) == 32

    # Ключи диалога, выведенные через HKDF, совпадают у обоих игроков
    key_alice = derive_dialogue_key(kp_alice, kp_bob.public_hex)
    key_bob = derive_dialogue_key(kp_bob, kp_alice.public_hex)
    assert key_alice == key_bob

    # Посторонний игрок Ева не имеет доступа к общему секрету
    key_eva = derive_dialogue_key(kp_eva, kp_alice.public_hex)
    assert key_eva != key_alice


def test_chacha20_encryption_and_integrity():
    """Проверка стойкого симметричного шифрования ChaCha20-Poly1305."""
    kp_alice = KeyPair.generate()
    kp_bob = KeyPair.generate()
    key = derive_dialogue_key(kp_alice, kp_bob.public_hex)

    secret_thought = "Истина открывается чистому сердцу и чистой совести."
    encrypted = encrypt_drop_content(secret_thought, key)

    assert encrypted.startswith(ENCRYPTED_PREFIX)
    assert secret_thought not in encrypted

    # Успешное расшифрование верным ключом
    decrypted = decrypt_drop_content(encrypted, key)
    assert decrypted == secret_thought

    # Попытка расшифровать чужим ключом вызывает ошибку аутентификации Poly1305
    kp_eva = KeyPair.generate()
    wrong_key = derive_dialogue_key(kp_eva, kp_alice.public_hex)
    with pytest.raises(InvalidTag):
        symmetric_decrypt(wrong_key, encrypted)


def test_node_dialogue_e2ee_workflow():
    """
    Полный цикл E2EE-диалога на узлах «Воля»:
    - В RocksDB хранится только шифротекст;
    - Участники читают расшифрованный текст;
    - Третья сторона не имеет доступа к каплям.
    """
    tmp_dir = Path(tempfile.mkdtemp(prefix="test_node_e2ee_"))
    try:
        # 1. Создаем двух участников (Сигом и Ладомир) и стороннего наблюдателя (Чужак)
        kp_sigom = KeyPair.generate()
        id_sigom = SovereignIdentity(keypair=kp_sigom, username="Сигом")
        node_sigom = VolyaNode(node_dir=tmp_dir / "node_sigom", identity=id_sigom)

        kp_ladomir = KeyPair.generate()
        id_ladomir = SovereignIdentity(keypair=kp_ladomir, username="Ладомир")
        node_ladomir = VolyaNode(node_dir=tmp_dir / "node_ladomir", identity=id_ladomir)

        kp_stranger = KeyPair.generate()
        id_stranger = SovereignIdentity(keypair=kp_stranger, username="Чужак")
        node_stranger = VolyaNode(node_dir=tmp_dir / "node_stranger", identity=id_stranger)

        flow_id = "flow-dialogue-sigom-ladomir"
        quest_id = "quest-portal-volya"

        # 2. Сигом отправляет каплю диалога Ладомиру
        msg_text = "Здравствуй, брат Ладомир! Запускаем децентрализованный узел."
        sent_drop = node_sigom.add_drop(
            quest_id=quest_id,
            flow_id=flow_id,
            flow_kind=FlowKind.DIALOGUE,
            kind=DropKind.TEXT,
            content=msg_text,
            created_at="2026-10-16T12:00:00Z",
            recipients=[node_ladomir.identity.pubkey],
        )

        # Вызывающий код получает канонический объект с открытым текстом
        assert sent_drop.content == msg_text

        # 3. ПРОВЕРЯЕМ БАЗУ ROCKSDB: там лежит строго шифротекст!
        raw_drop = node_sigom.dag_store.get_drop(sent_drop.id)
        assert raw_drop is not None
        assert raw_drop.content.startswith(ENCRYPTED_PREFIX)
        assert msg_text not in raw_drop.content

        # 4. Сигом читает свой поток капель через get_accessible_drops
        sigom_drops = node_sigom.get_accessible_drops(flow_id)
        assert len(sigom_drops) == 1
        assert sigom_drops[0].content == msg_text

        # 5. Имитируем синхронизацию Merkle DAG: Ладомир получает узел в свой store
        dag_node = node_sigom.dag_store.get_node(sent_drop.id)
        node_ladomir.dag_store.put_node(dag_node)

        # Ладомир читает диалог через get_accessible_drops и видит расшифрованное сообщение
        ladomir_drops = node_ladomir.get_accessible_drops(flow_id)
        assert len(ladomir_drops) == 1
        assert ladomir_drops[0].content == msg_text

        # 6. Имитируем синхронизацию с чужаком: узел попадает в базу Чужака
        node_stranger.dag_store.put_node(dag_node)

        # Чужак вызывает get_accessible_drops — доступ по Кону закрыт, список пуст!
        stranger_accessible = node_stranger.get_accessible_drops(flow_id)
        assert len(stranger_accessible) == 0

        # Если чужак попытается взломать сырую каплю из базы своим ключом
        wrong_key = derive_dialogue_key(node_stranger.identity.keypair, node_sigom.identity.pubkey)
        with pytest.raises(InvalidTag):
            symmetric_decrypt(wrong_key, raw_drop.content)

        node_sigom.dag_store.close()
        node_ladomir.dag_store.close()
        node_stranger.dag_store.close()
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_node_conversation_realm_protection():
    """
    Проверка защищенной беседы квеста:
    - Все капли беседы в базе зашифрованы ключом пространства квеста;
    - Все игроки квеста на узлах Воли прозрачно расшифровывают сообщения;
    - Внешний дамп базы не содержит открытого текста.
    """
    tmp_dir = Path(tempfile.mkdtemp(prefix="test_node_conversation_"))
    try:
        kp_player1 = KeyPair.generate()
        node1 = VolyaNode(
            node_dir=tmp_dir / "node1",
            identity=SovereignIdentity(keypair=kp_player1, username="Игрок 1"),
        )

        kp_player2 = KeyPair.generate()
        node2 = VolyaNode(
            node_dir=tmp_dir / "node2",
            identity=SovereignIdentity(keypair=kp_player2, username="Игрок 2"),
        )

        flow_id = "flow-portal-volya-general"
        quest_id = "quest-portal-volya"

        thought = "Созидаем уклад мастерской: чистота помыслов, взаимная поддержка."
        node1.add_drop(
            quest_id=quest_id,
            flow_id=flow_id,
            flow_kind=FlowKind.CONVERSATION,
            kind=DropKind.TEXT,
            content=thought,
            created_at="2026-10-16T12:30:00Z",
        )

        # Проверяем базу node1: текст зашифрован
        drops_in_db = node1.dag_store.get_flow_drops(flow_id)
        assert len(drops_in_db) == 1
        assert drops_in_db[0].content.startswith(ENCRYPTED_PREFIX)
        assert thought not in drops_in_db[0].content

        # Синхронизируем узел с node2
        node_in_dag = node1.dag_store.get_node(drops_in_db[0].id)
        node2.dag_store.put_node(node_in_dag)

        # Оба игрока читают чистый текст в get_accessible_drops
        drops_node1 = node1.get_accessible_drops(flow_id)
        assert drops_node1[0].content == thought

        drops_node2 = node2.get_accessible_drops(flow_id)
        assert drops_node2[0].content == thought

        node1.dag_store.close()
        node2.dag_store.close()
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
