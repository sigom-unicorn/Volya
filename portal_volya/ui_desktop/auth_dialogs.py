"""
Модальные окна авторизации, выбора игрока, ввода ПИН-кода и создания Неофита (Glassmorphism).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import (
    QByteArray,
    QRectF,
    QRegularExpression,
    QSize,
    QTimer,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QIcon,
    QImage,
    QPainter,
    QPainterPath,
    QPixmap,
    QRegularExpressionValidator,
)
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from portal_volya.node import VolyaNode
from portal_volya.storage.device_identities import DevicePlayerIdentity
from portal_volya.ui_desktop.avatar_generator import (
    generate_default_avatar_png,
    process_custom_avatar_png,
)


def make_circular_pixmap(data: bytes, size: int = 48) -> QPixmap:
    """Создаёт идеально круглый QPixmap из байтов PNG/JPG."""
    img = QImage()
    img.loadFromData(data)
    if img.isNull():
        # Fallback на пустой серый круг
        img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
        img.fill(QColor("#1b2a47"))

    scaled = img.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)

    target = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    target.fill(Qt.transparent)

    painter = QPainter(target)
    painter.setRenderHint(QPainter.Antialiasing, True)
    path = QPainterPath()
    path.addEllipse(0, 0, size, size)
    painter.setClipPath(path)
    x_offset = int((size - scaled.width()) / 2)
    y_offset = int((size - scaled.height()) / 2)
    painter.drawImage(x_offset, y_offset, scaled)
    painter.end()

    return QPixmap.fromImage(target)


# Базовый стиль для стеклянных окон
GLASS_DIALOG_STYLE = """
QDialog {
    background: transparent;
}
#glassModalCard {
    background: rgba(14, 20, 36, 0.90);
    border: 1.5px solid rgba(212, 175, 55, 0.40);
    border-radius: 18px;
}
QLabel {
    color: #e2e8f0;
    font-family: 'Segoe UI', 'Roboto', sans-serif;
}
QLineEdit {
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.20);
    border-radius: 8px;
    padding: 8px 12px;
    color: #f8fafc;
    font-size: 13px;
}
QLineEdit:focus {
    border: 1px solid #d4af37;
    background: rgba(255, 255, 255, 0.12);
}
QPushButton {
    background: rgba(255, 255, 255, 0.09);
    border: 1px solid rgba(255, 255, 255, 0.20);
    border-radius: 10px;
    color: #f8fafc;
    padding: 8px 16px;
    font-size: 13px;
    font-weight: 500;
}
QPushButton:hover {
    background: rgba(255, 255, 255, 0.22);
    border-color: rgba(212, 175, 55, 0.60);
}
QPushButton:pressed {
    background: rgba(255, 255, 255, 0.32);
}
QPushButton#primaryBtn {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1b4332, stop:1 #2d6a4f);
    border: 1.2px solid #d4af37;
    color: #fefae0;
    font-weight: 600;
}
QPushButton#primaryBtn:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2d6a4f, stop:1 #40916c);
    border-color: #fefae0;
}
"""


class PinCodeModal(QDialog):
    """Модальное окно ввода 4-значного ПИН-кода игрока."""

    authenticated = Signal()

    def __init__(
        self,
        identity: DevicePlayerIdentity,
        node: Optional[VolyaNode] = None,
        allow_switch_player: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.identity = identity
        self.node = node
        self.allow_switch_player = allow_switch_player

        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setStyleSheet(GLASS_DIALOG_STYLE)
        self.resize(380, 360)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        card = QFrame(self)
        card.setObjectName("glassModalCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 24, 24, 24)
        card_layout.setSpacing(12)

        # Заголовок
        lbl_lock = QLabel("🔒 Вход защищён ПИН-кодом")
        lbl_lock.setFont(QFont("Segoe UI", 13, QFont.Bold))
        lbl_lock.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(lbl_lock)

        # Аватар игрока (если доступен узел)
        if self.node:
            avatar_bytes = self.node.get_player_avatar_bytes(self.identity.pubkey)
            if not avatar_bytes:
                avatar_bytes = generate_default_avatar_png(self.identity.username, self.identity.pubkey)
            lbl_avatar = QLabel()
            lbl_avatar.setPixmap(make_circular_pixmap(avatar_bytes, size=52))
            lbl_avatar.setAlignment(Qt.AlignCenter)
            card_layout.addWidget(lbl_avatar)

        lbl_sub = QLabel(f"Игрок: <strong>{self.identity.username}</strong>")
        lbl_sub.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(lbl_sub)

        # Поле ввода ПИН-кода
        self.pin_input = QLineEdit()
        self.pin_input.setEchoMode(QLineEdit.Password)
        self.pin_input.setMaxLength(4)
        self.pin_input.setValidator(
            QRegularExpressionValidator(QRegularExpression(r"^[0-9]{0,4}$"), self)
        )
        self.pin_input.setAlignment(Qt.AlignCenter)
        self.pin_input.setFont(QFont("Segoe UI", 20, QFont.Bold))
        self.pin_input.setPlaceholderText("••••")
        self.pin_input.textChanged.connect(self._on_pin_changed)
        card_layout.addWidget(self.pin_input)

        self.lbl_error = QLabel("")
        self.lbl_error.setStyleSheet("color: #ef4444; font-size: 12px;")
        self.lbl_error.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(self.lbl_error)

        # Кнопки
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        if self.allow_switch_player:
            btn_switch = QPushButton("👤 Сменить")
            btn_switch.setToolTip("Войти под другим игроком")
            btn_switch.clicked.connect(lambda: self.done(2))
            btn_layout.addWidget(btn_switch)

        btn_cancel = QPushButton("Отмена")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        self.btn_submit = QPushButton("Войти")
        self.btn_submit.setObjectName("primaryBtn")
        self.btn_submit.clicked.connect(self._verify)
        btn_layout.addWidget(self.btn_submit)

        card_layout.addLayout(btn_layout)
        main_layout.addWidget(card)

        # Настройка таймера периода остывания (anti-bruteforce)
        self.cooldown_timer = QTimer(self)
        self.cooldown_timer.timeout.connect(self._on_cooldown_tick)
        self.cooldown_remaining = 0

        # Проверка текущего остывания при открытии окна
        if self.node:
            init_lockout = self.node.get_pin_lockout_seconds(self.identity.pubkey)
        else:
            init_lockout = self.identity.get_lockout_remaining_seconds()

        if init_lockout > 0:
            self._start_cooldown(init_lockout)
        else:
            self.pin_input.setFocus()

    def _start_cooldown(self, seconds: int) -> None:
        """Блокировка ввода на период остывания."""
        self.cooldown_remaining = seconds
        self.pin_input.setEnabled(False)
        self.btn_submit.setEnabled(False)
        self.lbl_error.setText(f"⏳ Слишком много неверных попыток.\nПодождите {self.cooldown_remaining} сек.")
        self.cooldown_timer.start(1000)

    def _on_cooldown_tick(self) -> None:
        """Ежесекундное обновление таймера остывания."""
        self.cooldown_remaining -= 1
        if self.cooldown_remaining <= 0:
            self.cooldown_timer.stop()
            self.pin_input.setEnabled(True)
            self.btn_submit.setEnabled(True)
            self.pin_input.clear()
            self.pin_input.setFocus()
            self.lbl_error.setText("Вы можете попробовать снова (3 попытки)")
            self.lbl_error.setStyleSheet("color: #10b981; font-size: 12px;")
        else:
            self.lbl_error.setStyleSheet("color: #ef4444; font-size: 12px;")
            self.lbl_error.setText(f"⏳ Слишком много неверных попыток.\nПодождите {self.cooldown_remaining} сек.")

    def _on_pin_changed(self, text: str) -> None:
        if self.cooldown_remaining > 0:
            return
        self.lbl_error.setText("")
        self.lbl_error.setStyleSheet("color: #ef4444; font-size: 12px;")
        if len(text.strip()) == 4:
            self._verify()

    def _verify(self) -> None:
        if self.cooldown_remaining > 0:
            return

        pin = self.pin_input.text().strip()
        if self.identity.verify_pin(pin):
            if self.node:
                self.node.reset_failed_pin_attempts(self.identity.pubkey)
            else:
                self.identity.reset_failed_pin_attempts()
            self.authenticated.emit()
            self.accept()
        else:
            if self.node:
                failed_count, cooldown = self.node.record_failed_pin_attempt(self.identity.pubkey)
            else:
                failed_count, cooldown = self.identity.record_failed_pin_attempt()

            if cooldown > 0:
                self._start_cooldown(cooldown)
            else:
                attempts_left = 3 - failed_count
                self.lbl_error.setStyleSheet("color: #ef4444; font-size: 12px;")
                self.lbl_error.setText(f"Неверный ПИН-код. Осталось попыток: {attempts_left}")
                self.pin_input.selectAll()
                self.pin_input.setFocus()

    def closeEvent(self, event) -> None:
        if hasattr(self, "cooldown_timer") and self.cooldown_timer.isActive():
            self.cooldown_timer.stop()
        super().closeEvent(event)


class CreatePlayerModal(QDialog):
    """Модальное окно рождения нового игрока (вход Неофитом в квест Посвящение)."""

    def __init__(self, node: VolyaNode, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.node = node
        self.custom_avatar_data: Optional[bytes] = None

        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setStyleSheet(GLASS_DIALOG_STYLE)
        self.resize(480, 520)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        card = QFrame(self)
        card.setObjectName("glassModalCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 24, 28, 24)
        card_layout.setSpacing(14)

        lbl_title = QLabel("РОЖДЕНИЕ В ИГРЕ «ВОЛЯ»")
        lbl_title.setFont(QFont("Georgia", 14, QFont.Bold))
        lbl_title.setStyleSheet("color: #fefae0;")
        lbl_title.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(lbl_title)

        lbl_desc = QLabel(
            "Каждый новый игрок начинает путь с пустой Чашей (0 капель совести) "
            "и получает роль Неофита в квесте «Посвящение»."
        )
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet("color: #94a3b8; font-size: 11.5px;")
        lbl_desc.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(lbl_desc)

        # Превью аватара
        avatar_row = QHBoxLayout()
        avatar_row.setSpacing(14)
        self.lbl_avatar_preview = QLabel()
        self._update_avatar_preview("Вольный Игрок")
        avatar_row.addWidget(self.lbl_avatar_preview)

        btn_pick_avatar = QPushButton("📷 Загрузить аватар")
        btn_pick_avatar.clicked.connect(self._pick_avatar)
        avatar_row.addWidget(btn_pick_avatar)
        avatar_row.addStretch()
        card_layout.addLayout(avatar_row)

        # Поля ввода
        card_layout.addWidget(QLabel("Вольное имя игрока:"))
        self.input_name = QLineEdit()
        self.input_name.setPlaceholderText("Например: Добрыня, Светлана, Радомир")
        self.input_name.textChanged.connect(self._on_name_changed)
        card_layout.addWidget(self.input_name)

        card_layout.addWidget(QLabel("О себе / Биография (по желанию):"))
        self.input_bio = QLineEdit()
        self.input_bio.setPlaceholderText("Стремлюсь жить по совести и ладу")
        card_layout.addWidget(self.input_bio)

        card_layout.addWidget(QLabel("ПИН-код для защиты на этом ПК (4 цифры, по желанию):"))
        self.input_pin = QLineEdit()
        self.input_pin.setMaxLength(4)
        self.input_pin.setValidator(
            QRegularExpressionValidator(QRegularExpression(r"^[0-9]{0,4}$"), self)
        )
        self.input_pin.setPlaceholderText("Оставьте пустым, если ПИН не требуется")
        card_layout.addWidget(self.input_pin)

        self.lbl_error = QLabel("")
        self.lbl_error.setStyleSheet("color: #ef4444; font-size: 12px;")
        card_layout.addWidget(self.lbl_error)

        # Кнопки
        btn_layout = QHBoxLayout()
        btn_cancel = QPushButton("Отмена")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        btn_create = QPushButton("🌿 Вступить в Посвящение")
        btn_create.setObjectName("primaryBtn")
        btn_create.clicked.connect(self._create_player)
        btn_layout.addWidget(btn_create)

        card_layout.addLayout(btn_layout)
        main_layout.addWidget(card)

    def _on_name_changed(self, text: str) -> None:
        if not self.custom_avatar_data:
            self._update_avatar_preview(text.strip() or "И")

    def _update_avatar_preview(self, name: str) -> None:
        if self.custom_avatar_data:
            pix = make_circular_pixmap(self.custom_avatar_data, size=64)
        else:
            raw = generate_default_avatar_png(name, name + "genesis_seed_preview", size=128)
            pix = make_circular_pixmap(raw, size=64)
        self.lbl_avatar_preview.setPixmap(pix)
        self.lbl_avatar_preview.setFixedSize(64, 64)

    def _pick_avatar(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите изображение аватара",
            "",
            "Изображения (*.png *.jpg *.jpeg *.webp)",
        )
        if path:
            try:
                self.custom_avatar_data = process_custom_avatar_png(path, size=256)
                self._update_avatar_preview(self.input_name.text())
            except Exception as e:
                self.lbl_error.setText(f"Ошибка загрузки аватара: {e}")

    def _create_player(self) -> None:
        name = self.input_name.text().strip()
        if not name:
            self.lbl_error.setText("Укажите вольное имя игрока.")
            return

        pin = self.input_pin.text().strip()
        if pin and (len(pin) != 4 or not pin.isdigit()):
            self.lbl_error.setText("ПИН-код должен состоять ровно из 4 цифр.")
            return

        try:
            player, dev_id = self.node.create_neophyte_player(
                username=name,
                bio=self.input_bio.text().strip(),
                pin=pin if pin else None,
                custom_avatar_data=self.custom_avatar_data,
            )
            self.accept()
        except Exception as e:
            self.lbl_error.setText(f"Ошибка создания: {e}")


class ImportKeyModal(QDialog):
    """Модальное окно импорта игрока по приватному ключу."""

    def __init__(self, node: VolyaNode, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.node = node

        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setStyleSheet(GLASS_DIALOG_STYLE)
        self.resize(460, 420)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        card = QFrame(self)
        card.setObjectName("glassModalCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 24, 28, 24)
        card_layout.setSpacing(14)

        lbl_title = QLabel("ВХОД ПО ПРИВАТНОМУ КЛЮЧУ")
        lbl_title.setFont(QFont("Georgia", 14, QFont.Bold))
        lbl_title.setStyleSheet("color: #fefae0;")
        lbl_title.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(lbl_title)

        card_layout.addWidget(QLabel("Приватный ключ (64 шестнадцатеричных символа):"))
        self.input_key = QLineEdit()
        self.input_key.setPlaceholderText("Вставьте ваш Ed25519 приватный ключ...")
        card_layout.addWidget(self.input_key)

        card_layout.addWidget(QLabel("Вольное имя игрока:"))
        self.input_name = QLineEdit()
        self.input_name.setPlaceholderText("Ваше имя в игре Воля")
        card_layout.addWidget(self.input_name)

        card_layout.addWidget(QLabel("ПИН-код для этого устройства (4 цифры, по желанию):"))
        self.input_pin = QLineEdit()
        self.input_pin.setMaxLength(4)
        self.input_pin.setValidator(
            QRegularExpressionValidator(QRegularExpression(r"^[0-9]{0,4}$"), self)
        )
        self.input_pin.setPlaceholderText("4 цифры")
        card_layout.addWidget(self.input_pin)

        self.lbl_error = QLabel("")
        self.lbl_error.setStyleSheet("color: #ef4444; font-size: 12px;")
        card_layout.addWidget(self.lbl_error)

        btn_layout = QHBoxLayout()
        btn_cancel = QPushButton("Отмена")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        btn_import = QPushButton("🔑 Войти в Обитель")
        btn_import.setObjectName("primaryBtn")
        btn_import.clicked.connect(self._import)
        btn_layout.addWidget(btn_import)

        card_layout.addLayout(btn_layout)
        main_layout.addWidget(card)

    def _import(self) -> None:
        key = self.input_key.text().strip()
        name = self.input_name.text().strip()
        pin = self.input_pin.text().strip()

        if not key or len(key) != 64:
            self.lbl_error.setText("Приватный ключ должен содержать ровно 64 символа.")
            return

        if not name:
            self.lbl_error.setText("Укажите ваше вольное имя.")
            return

        if pin and (len(pin) != 4 or not pin.isdigit()):
            self.lbl_error.setText("ПИН-код должен состоять ровно из 4 цифр.")
            return

        try:
            self.node.import_player_key(
                private_key_hex=key,
                username=name,
                pin=pin if pin else None,
            )
            self.accept()
        except Exception as e:
            self.lbl_error.setText(f"Ошибка импорта: {e}")
