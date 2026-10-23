"""
Тестирование авторизации игроков, PIN-кодов, аватаров и квеста «Посвящение».
"""

import shutil
import tempfile
from pathlib import Path
import pytest

from PySide6.QtWidgets import QApplication

from portal_volya.core.crypto import KeyPair
from portal_volya.core.genesis import SIGOM_SEED, derive_genesis_keypair
from portal_volya.core.models import TreeTier, StepName
from portal_volya.node import VolyaNode
from portal_volya.storage.device_identities import DeviceIdentitiesManager
from portal_volya.ui_desktop.avatar_generator import (
    generate_default_avatar_png,
    process_custom_avatar_png,
)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    return app


@pytest.fixture
def temp_node_dir():
    d = Path(tempfile.mkdtemp(prefix="test_volya_auth_"))
    yield d
    shutil.rmtree(d, ignore_errors=True)


def test_avatar_generator(qapp):
    """Проверка генерации аватаров по умолчанию и обработки пользовательских."""
    pk = "a" * 64
    png_bytes = generate_default_avatar_png("Алексей", pk, size=128)
    assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(png_bytes) > 500

    # Обработка пользовательского
    processed = process_custom_avatar_png(png_bytes, size=64)
    assert processed[:8] == b"\x89PNG\r\n\x1a\n"


def test_device_identities_manager(temp_node_dir):
    """Проверка менеджера суверенных игроков на устройстве и PIN-кода."""
    mgr = DeviceIdentitiesManager(node_dir=temp_node_dir)

    # 1. По умолчанию сидируется Сигом, а Эйры и Ладомира в выборе НЕТ!
    players = mgr.list_players()
    usernames = [p.username for p in players]
    assert "Сигом" in usernames
    assert "Эйра" not in usernames
    assert "Ладомир" not in usernames

    # 2. Регистрация нового игрока с PIN-кодом
    neophyte_id = mgr.register_new_player("Радомир", pin="1234", bio="Вольный странник")
    assert neophyte_id.username == "Радомир"
    assert neophyte_id.has_pin is True
    assert neophyte_id.verify_pin("1234") is True
    assert neophyte_id.verify_pin("0000") is False

    # 3. Переключение
    active = mgr.get_active_player()
    assert active.username == "Радомир"

    # 4. Проверка смены PIN
    neophyte_id.set_pin("5678")
    assert neophyte_id.verify_pin("5678") is True
    assert neophyte_id.verify_pin("1234") is False


def test_node_create_neophyte_and_initiation(temp_node_dir, qapp):
    """Проверка создания Неофита в квесте «Посвящение» с 0 капель совести."""
    with VolyaNode(node_dir=temp_node_dir) as node:
        # Проверяем, что квест Посвящение есть в Древе
        init_q = node.dag_store.get_quest("quest-posvyashchenie")
        assert init_q is not None
        assert init_q.tier == TreeTier.ROOT_CHILD
        assert init_q.title == "Посвящение"
        role_titles = [r.title for r in init_q.kon.roles]
        assert "Неофит" in role_titles

        # Создаём Неофита
        player, dev_id = node.create_neophyte_player(
            username="Добрыня",
            bio="В поисках лада",
            pin="4321",
        )
        assert player.username == "Добрыня"
        assert player.conscience_drops == 0  # Ровно 0 капель в Чаше!
        assert player.avatar_hash is not None
        assert len(player.roles) == 1
        assert player.roles[0].quest_id == "quest-posvyashchenie"
        assert player.roles[0].role_title == "Неофит"

        # Проверяем аватарку в хранилище блобов
        avatar_data = node.get_player_avatar_bytes(player.pubkey)
        assert avatar_data is not None
        assert avatar_data[:8] == b"\x89PNG\r\n\x1a\n"

        # Завершаем Посвящение: определяем капли совести и наделяем ролью «Вольный игрок»
        updated_player = node.complete_initiation(player.pubkey, determined_drops=150)
        assert updated_player.conscience_drops == 150
        roles = [r.role_title for r in updated_player.roles]
        assert "Неофит" in roles
        assert "Вольный игрок" in roles


def test_player_pin_management(temp_node_dir):
    """Проверка установки, смены и удаления PIN-кода через узел."""
    with VolyaNode(node_dir=temp_node_dir) as node:
        pk = node.identity.pubkey
        # По умолчанию у Сигома нет PIN
        dev_id = node.identities_mgr.get_player(pk)
        assert dev_id.has_pin is False

        # Установка PIN
        node.set_player_pin(pk, "9876")
        assert dev_id.has_pin is True
        assert dev_id.verify_pin("9876") is True

        # Смена PIN с проверкой текущего
        with pytest.raises(ValueError):
            node.set_player_pin(pk, "1111", current_pin="wrong")

        node.set_player_pin(pk, "1111", current_pin="9876")
        assert dev_id.verify_pin("1111") is True

        # Удаление PIN
        node.remove_player_pin(pk, current_pin="1111")
        assert dev_id.has_pin is False


def test_glass_player_pill_and_profile_modal(temp_node_dir, qapp):
    """Проверка работы виджета GlassPlayerPill и карточки профиля."""
    from portal_volya.ui_desktop.profile_pill import GlassPlayerPill, PlayerProfileModal
    from portal_volya.ui_desktop.main_window import VolyaLivingWindow

    with VolyaNode(node_dir=temp_node_dir) as node:
        # Создаем pill
        pill = GlassPlayerPill(node)
        assert pill.lbl_name.text() == "Сигом"
        assert "💧" in pill.lbl_status.text()
        assert pill.lbl_avatar.pixmap() is not None

        # Проверяем модалку профиля
        modal = PlayerProfileModal(node)
        assert modal.lbl_username.text() == "Сигом"
        assert "💧 Чаша Души" in modal.lbl_drops.text()
        modal.close()

        # Создаем Неофита и переключаемся
        node.create_neophyte_player("Яромир", bio="Искатель истины")
        pill.refresh()
        assert pill.lbl_name.text() == "Яромир"
        assert "💧 0" in pill.lbl_status.text()
        assert "Неофит" in pill.lbl_status.text()

        # Проверяем окно LivingWindow
        window = VolyaLivingWindow(node=node)
        assert window.player_pill is not None
        assert window.player_pill.lbl_name.text() == "Яромир"
        window.close()

