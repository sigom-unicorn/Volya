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
        qapp.processEvents()


def test_startup_pin_auth_flow(temp_node_dir, qapp):
    """Проверка блокировки окна при запуске, если у активного игрока установлен ПИН-код."""
    from portal_volya.ui_desktop.main_window import VolyaLivingWindow
    from portal_volya.ui_desktop.sacred_auth import SacredPinLockWidget

    with VolyaNode(node_dir=temp_node_dir) as node:
        pk = node.identity.pubkey
        # Настраиваем ПИН-код активному игроку
        node.set_player_pin(pk, "7788")

        # Создаем окно — оно ДОЛЖНО быть не авторизовано при старте
        window = VolyaLivingWindow(node=node)
        window.show()
        qapp.processEvents()

        assert window.is_authenticated is False
        assert window.player_pill.isVisible() is False
        assert window.sacred_lock.isVisible() is True

        # Проверяем имя сверху аватарки
        assert window.sacred_lock.lbl_name.text() == "Сигом"

        # Неверный ПИН
        window.sacred_lock.pin_input.setText("1234")
        assert "Осталось попыток: 2" in window.sacred_lock.lbl_status.text()
        assert window.is_authenticated is False

        # Верный ПИН — эфирный замок открывается
        window.sacred_lock.pin_input.setText("7788")
        assert window.is_authenticated is True
        assert window.sacred_lock.isVisible() is False
        assert window.player_pill.isVisible() is True

        window.close()
        qapp.processEvents()


def test_sacred_lock_widget_interactions(temp_node_dir, qapp):
    """Проверка интерактива подсвечивающейся дуги и светящейся нити."""
    from portal_volya.ui_desktop.sacred_auth import SacredPinLockWidget
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtCore import QPointF, QEvent, Qt

    with VolyaNode(node_dir=temp_node_dir) as node:
        pk = node.identity.pubkey
        node.set_player_pin(pk, "9999")
        dev_id = node.identities_mgr.get_player(pk)

        widget = SacredPinLockWidget(node, dev_id)
        widget.show()
        qapp.processEvents()
        assert widget.btn_switch.isVisible() is False
        assert widget.btn_new.isVisible() is False
        assert widget.btn_key.isVisible() is False
        assert widget._arc_hovered is False

        # Симулируем наведение мыши на дугу под аватаркой (когда игрок только один)
        hover_ev = QMouseEvent(
            QEvent.MouseMove,
            QPointF(widget.cx, widget.cy + widget.arc_radius - 5),
            QPointF(widget.cx, widget.cy + widget.arc_radius - 5),
            Qt.NoButton,
            Qt.NoButton,
            Qt.NoModifier,
        )
        widget.mouseMoveEvent(hover_ev)
        assert widget._arc_hovered is True
        # Кнопка «Сменить» НЕ должна появляться, так как других игроков нет!
        assert widget.btn_switch.isVisible() is False
        # Но кнопки «Новый» и «Войти по ключу» появляются
        assert widget.btn_new.isVisible() is True
        assert widget.btn_key.isVisible() is True

        # Добавляем второго игрока на этот компьютер
        node.create_neophyte_player("Второй Игрок")
        widget.switch_mode(widget.MODE_PIN)
        widget.mouseMoveEvent(hover_ev)
        # Теперь есть другие игроки — «Сменить» появляется!
        assert widget.btn_switch.isVisible() is True

        # Нажатие на кнопку «Сменить» открывает список игроков
        widget.btn_switch.click()
        assert widget._switch_list_visible is True
        assert widget.switch_list_widget.isVisible() is True

        # Симулируем уход курсора
        leave_ev = QMouseEvent(
            QEvent.MouseMove,
            QPointF(10, 10),
            QPointF(10, 10),
            Qt.NoButton,
            Qt.NoButton,
            Qt.NoModifier,
        )
        # Закрываем список и уходим
        widget.btn_switch.click()
        widget.mouseMoveEvent(leave_ev)
        assert widget._arc_hovered is False
        assert widget.btn_switch.isVisible() is False

        # Проверка перехода в режим Новый (MODE_NEW)
        widget.switch_mode(widget.MODE_NEW)
        assert widget.pin_input.isVisible() is False
        assert widget.input_new_name.isVisible() is True
        assert widget.input_new_bio.isVisible() is True
        assert widget.input_new_pin.isVisible() is True

        # Проверка перехода в режим Вход по ключу (MODE_KEY)
        widget.switch_mode(widget.MODE_KEY)
        assert widget.input_new_name.isVisible() is False
        assert widget.input_key.isVisible() is True
        assert widget.input_key_pin.isVisible() is True

        widget.close()
        qapp.processEvents()


def test_pin_bruteforce_protection_and_cooldown(temp_node_dir, qapp):
    """Проверка защиты от брутфорса: 3 неверных ввода вызывают 30 секунд остывания."""
    from portal_volya.ui_desktop.auth_dialogs import PinCodeModal

    with VolyaNode(node_dir=temp_node_dir) as node:
        pk = node.identity.pubkey
        node.set_player_pin(pk, "5555")
        dev_id = node.identities_mgr.get_player(pk)

        modal = PinCodeModal(dev_id, node=node)

        # 1-я неверная попытка (setText автоматически вызывает _verify при 4 цифрах)
        modal.pin_input.setText("0000")
        assert "Осталось попыток: 2" in modal.lbl_error.text()
        assert modal.pin_input.isEnabled() is True

        # 2-я неверная попытка
        modal.pin_input.setText("1111")
        assert "Осталось попыток: 1" in modal.lbl_error.text()
        assert modal.pin_input.isEnabled() is True

        # 3-я неверная попытка -> активируется период остывания 30 сек
        modal.pin_input.setText("2222")
        assert "Подождите" in modal.lbl_error.text()
        assert modal.pin_input.isEnabled() is False
        assert modal.btn_submit.isEnabled() is False
        assert modal.cooldown_remaining > 0

        # Проверяем сохранение остывания на узле
        rem = node.get_pin_lockout_seconds(pk)
        assert rem > 0 and rem <= 30

        # Симулируем тики таймера остывания
        modal.cooldown_remaining = 1
        modal._on_cooldown_tick()
        assert modal.cooldown_remaining == 0
        assert modal.pin_input.isEnabled() is True
        assert modal.btn_submit.isEnabled() is True

        # После остывания дается еще 3 попытки, вводим верный ПИН
        modal.pin_input.setText("5555")
        assert dev_id.failed_pin_attempts == 0
        assert node.get_pin_lockout_seconds(pk) == 0

        modal.close()
        qapp.processEvents()


def test_sacred_lock_new_and_key_modes(temp_node_dir, qapp):
    """Проверка режимов Новый игрок и Вход по ключу в эфирном замке."""
    from portal_volya.ui_desktop.sacred_auth import SacredPinLockWidget
    from portal_volya.core.crypto import KeyPair

    with VolyaNode(node_dir=temp_node_dir) as node:
        active_pk = node.identity.pubkey
        dev_id = node.identities_mgr.get_player(active_pk)

        widget = SacredPinLockWidget(node, dev_id)
        widget.show()
        qapp.processEvents()

        # 1. Проверяем режим MODE_NEW
        widget.switch_mode(widget.MODE_NEW)
        auth_signals = []
        widget.authenticated.connect(lambda: auth_signals.append(True))

        # Попытка создать без имени
        widget._on_submit_new_clicked()
        assert "Укажите вольное имя" in widget.lbl_new_status.text()
        assert len(auth_signals) == 0

        # Корректное создание нового игрока
        widget.input_new_name.setText("Ладомир Тест")
        widget.input_new_bio.setText("Созидатель")
        widget.input_new_pin.setText("4321")
        widget._on_submit_new_clicked()
        assert len(auth_signals) == 1
        assert node.identities_mgr.get_active_player().username == "Ладомир Тест"

        # 2. Проверяем режим MODE_KEY
        widget.switch_mode(widget.MODE_KEY)
        auth_signals.clear()

        # Пустой / неверный ключ
        widget.input_key.setText("not_a_valid_hex_key")
        assert widget._key_found_player is None
        assert widget.lbl_name.text() == ""

        # Ввод приватного ключа первого игрока (он есть в базе)
        first_ident = node.identities_mgr.get_player(active_pk)
        priv_hex = first_ident.keypair.private_hex
        widget.input_key.setText(priv_hex)

        # Игрок должен быть найден, имя отображено сверху, аватар загружен
        assert widget._key_found_player is not None
        assert widget.lbl_name.text() == first_ident.username

        # Нажимаем Войти в Портал
        widget._on_submit_key_clicked()
        assert len(auth_signals) == 1

        widget.close()
        qapp.processEvents()


def test_unique_player_username_invariant(temp_node_dir):
    """Проверка строгого инварианта: имя игрока в БД и на устройстве должно быть уникальным."""
    import pytest

    with VolyaNode(node_dir=temp_node_dir) as node:
        # Игрок "Сигом" уже создан в Genesis
        genesis_sigom = node.dag_store.get_player_by_username("Сигом")
        assert genesis_sigom is not None

        # Попытка создать второго игрока с именем "Сигом" должна вызвать исключение
        with pytest.raises(ValueError, match="уже занято"):
            node.create_neophyte_player("Сигом")

        # Попытка создать игрока с именем "сигом" (в нижнем регистре) также должна отклоняться
        with pytest.raises(ValueError, match="уже занято"):
            node.create_neophyte_player("сигом")

        # Создаем игрока с уникальным именем
        p2, dev2 = node.create_neophyte_player("Радомир")
        assert p2.username == "Радомир"

        # Повторная попытка создать "Радомир" отклоняется
        with pytest.raises(ValueError, match="уже занято"):
            node.create_neophyte_player("Радомир")


def test_sacred_lock_switch_player_with_pin(temp_node_dir, qapp):
    """Проверка смены игрока на замке: выбор другого игрока, ввод его ПИНа -> активный игрок переключается на узле."""
    from portal_volya.ui_desktop.sacred_auth import SacredPinLockWidget

    with VolyaNode(node_dir=temp_node_dir) as node:
        # Genesis игрок "Сигом" с ПИН-кодом
        sigom_pk = node.identities_mgr.get_active_player().pubkey
        node.set_player_pin(sigom_pk, "1234")
        sigom_ident = node.identities_mgr.get_player(sigom_pk)

        # Создаем второго игрока "Test" с ПИН-кодом "5678"
        p_test, dev_test = node.create_neophyte_player("Test", pin="5678")
        assert node.identities_mgr.get_active_player().username == "Test"

        # Открываем замок для активного "Test"
        lock = SacredPinLockWidget(node, dev_test)
        lock.show()
        qapp.processEvents()

        # Выбираем игрока "Сигом" через переключатель
        lock._on_switch_player_selected(sigom_ident)
        assert lock.identity.username == "Сигом"

        # Вводим ПИН-код Сигома
        auth_fired = []
        lock.authenticated.connect(lambda: auth_fired.append(True))
        lock.pin_input.setText("1234")
        qapp.processEvents()

        # Должен сработать сигнал authenticated, а активным игроком на узле должен стать Сигом!
        assert len(auth_fired) == 1
        assert node.identities_mgr.get_active_player().username == "Сигом"
        assert node.identity.username == "Сигом"
        assert node.my_player.username == "Сигом"


def test_pin_inputs_strictly_digits_only(qapp, temp_node_dir):
    """Проверка, что все поля ввода ПИН-кода принимают исключительно цифры (0-9) до 4 символов."""
    from PySide6.QtTest import QTest
    from PySide6.QtGui import QValidator
    from portal_volya.ui_desktop.sacred_auth import CleanPinInput, SacredPinLockWidget
    from portal_volya.ui_desktop.auth_dialogs import PinCodeModal

    # 1. CleanPinInput
    clean_pin = CleanPinInput()
    clean_pin.show()
    QTest.keyClicks(clean_pin, "1a2#b3 4x9")
    assert clean_pin.text() == "1234"

    val = clean_pin.validator()
    assert val is not None
    assert val.validate("1234", 0)[0] == QValidator.State.Acceptable
    assert val.validate("abcd", 0)[0] == QValidator.State.Invalid
    assert val.validate("12!4", 0)[0] == QValidator.State.Invalid
    assert val.validate("12345", 0)[0] == QValidator.State.Invalid

    # 2. SacredPinLockWidget поля ввода: input_new_pin и input_key_pin
    with VolyaNode(node_dir=temp_node_dir / "node_pin") as node:
        widget = SacredPinLockWidget(node)
        widget.show()

        # Проверка input_new_pin
        widget.input_new_pin.clear()
        QTest.keyClicks(widget.input_new_pin, "8abc$ 765")
        assert widget.input_new_pin.text() == "8765"

        # Проверка input_key_pin
        widget.input_key_pin.clear()
        QTest.keyClicks(widget.input_key_pin, "43!@210")
        assert widget.input_key_pin.text() == "4321"








