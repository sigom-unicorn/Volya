"""
Виджет профиля вольного игрока (GlassPlayerPill) и карточка Души (PlayerProfileModal).
Плавный Glassmorphism, управление аватаром, ПИН-кодом и сменой игрока.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QRegularExpression, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
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
from portal_volya.ui_desktop.auth_dialogs import (
    GLASS_DIALOG_STYLE,
    PinCodeModal,
    PlayerSelectionModal,
    make_circular_pixmap,
)
from portal_volya.ui_desktop.avatar_generator import (
    generate_default_avatar_png,
    process_custom_avatar_png,
)


class ChangePinModal(QDialog):
    """Модальное окно установки или смены 4-значного ПИН-кода."""

    def __init__(self, node: VolyaNode, has_existing_pin: bool, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.node = node
        self.has_existing_pin = has_existing_pin

        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setStyleSheet(GLASS_DIALOG_STYLE)
        self.resize(380, 360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        card = QFrame(self)
        card.setObjectName("glassModalCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 24, 24, 24)
        card_layout.setSpacing(12)

        title = "СМЕНА ПИН-КОДА" if has_existing_pin else "УСТАНОВКА ПИН-КОДА"
        lbl_title = QLabel(title)
        lbl_title.setFont(QFont("Georgia", 13, QFont.Bold))
        lbl_title.setStyleSheet("color: #fefae0;")
        lbl_title.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(lbl_title)

        self.old_pin_input: Optional[QLineEdit] = None
        pin_validator = QRegularExpressionValidator(
            QRegularExpression(r"^[0-9]{0,4}$"), self
        )
        if has_existing_pin:
            card_layout.addWidget(QLabel("Текущий ПИН-код (4 цифры):"))
            self.old_pin_input = QLineEdit()
            self.old_pin_input.setEchoMode(QLineEdit.Password)
            self.old_pin_input.setMaxLength(4)
            self.old_pin_input.setValidator(pin_validator)
            self.old_pin_input.setPlaceholderText("••••")
            card_layout.addWidget(self.old_pin_input)

        card_layout.addWidget(QLabel("Новый ПИН-код (4 цифры):"))
        self.new_pin_input = QLineEdit()
        self.new_pin_input.setEchoMode(QLineEdit.Password)
        self.new_pin_input.setMaxLength(4)
        self.new_pin_input.setValidator(pin_validator)
        self.new_pin_input.setPlaceholderText("••••")
        card_layout.addWidget(self.new_pin_input)

        card_layout.addWidget(QLabel("Повторите новый ПИН-код:"))
        self.repeat_pin_input = QLineEdit()
        self.repeat_pin_input.setEchoMode(QLineEdit.Password)
        self.repeat_pin_input.setMaxLength(4)
        self.repeat_pin_input.setValidator(pin_validator)
        self.repeat_pin_input.setPlaceholderText("••••")
        card_layout.addWidget(self.repeat_pin_input)

        self.lbl_error = QLabel("")
        self.lbl_error.setStyleSheet("color: #ef4444; font-size: 11.5px;")
        card_layout.addWidget(self.lbl_error)

        btn_layout = QHBoxLayout()
        btn_cancel = QPushButton("Отмена")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        btn_save = QPushButton("Сохранить")
        btn_save.setObjectName("primaryBtn")
        btn_save.clicked.connect(self._save_pin)
        btn_layout.addWidget(btn_save)

        card_layout.addLayout(btn_layout)
        layout.addWidget(card)

    def _save_pin(self) -> None:
        new_pin = self.new_pin_input.text().strip()
        rep_pin = self.repeat_pin_input.text().strip()
        old_pin = self.old_pin_input.text().strip() if self.old_pin_input else None

        if len(new_pin) != 4 or not new_pin.isdigit():
            self.lbl_error.setText("Новый ПИН должен состоять из 4 цифр.")
            return

        if new_pin != rep_pin:
            self.lbl_error.setText("Введенные ПИН-коды не совпадают.")
            return

        try:
            self.node.set_player_pin(
                pubkey=self.node.identity.pubkey,
                new_pin=new_pin,
                current_pin=old_pin,
            )
            self.accept()
        except Exception as e:
            self.lbl_error.setText(str(e))


class PlayerProfileModal(QDialog):
    """Детальная карточка игрока: аватар, капли, роли, ПИН-код и суверенный ключ."""

    profile_updated = Signal()

    def __init__(self, node: VolyaNode, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.node = node

        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setStyleSheet(GLASS_DIALOG_STYLE)
        self.resize(520, 620)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        card = QFrame(self)
        card.setObjectName("glassModalCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 24, 28, 24)
        card_layout.setSpacing(14)

        # 1. Шапка профиля с аватаром
        header_layout = QHBoxLayout()
        header_layout.setSpacing(18)

        self.lbl_avatar = QLabel()
        self.lbl_avatar.setFixedSize(84, 84)
        header_layout.addWidget(self.lbl_avatar)

        name_info_layout = QVBoxLayout()
        name_info_layout.setSpacing(4)

        self.lbl_username = QLabel()
        self.lbl_username.setFont(QFont("Georgia", 16, QFont.Bold))
        self.lbl_username.setStyleSheet("color: #fefae0;")
        name_info_layout.addWidget(self.lbl_username)

        self.lbl_bio = QLabel()
        self.lbl_bio.setStyleSheet("color: #94a3b8; font-size: 12px;")
        self.lbl_bio.setWordWrap(True)
        name_info_layout.addWidget(self.lbl_bio)

        avatar_btns_layout = QHBoxLayout()
        avatar_btns_layout.setSpacing(8)

        btn_avatar = QPushButton("📷 Загрузить")
        btn_avatar.clicked.connect(self._change_avatar)
        avatar_btns_layout.addWidget(btn_avatar)

        btn_gen_pixel = QPushButton("🎲 Пиксельный тотем")
        btn_gen_pixel.setToolTip("Сгенерировать священный пиксельный тотем")
        btn_gen_pixel.clicked.connect(self._generate_pixel_avatar)
        avatar_btns_layout.addWidget(btn_gen_pixel)

        name_info_layout.addLayout(avatar_btns_layout)

        header_layout.addLayout(name_info_layout)
        header_layout.addStretch()
        card_layout.addLayout(header_layout)

        # Разделитель
        sep1 = QFrame()
        sep1.setStyleSheet("border-top: 1px solid rgba(255, 255, 255, 0.12);")
        card_layout.addWidget(sep1)

        # 2. Состояние Чаши Совести
        chalice_frame = QFrame()
        chalice_frame.setStyleSheet("""
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(212, 175, 55, 0.30);
            border-radius: 12px;
            padding: 10px;
        """)
        chalice_layout = QVBoxLayout(chalice_frame)
        chalice_layout.setSpacing(6)

        self.lbl_drops = QLabel()
        self.lbl_drops.setFont(QFont("Segoe UI", 14, QFont.Bold))
        self.lbl_drops.setStyleSheet("color: #67e8f9;")
        chalice_layout.addWidget(self.lbl_drops)

        self.lbl_chalice_desc = QLabel()
        self.lbl_chalice_desc.setStyleSheet("color: #cbd5e1; font-size: 11.5px;")
        self.lbl_chalice_desc.setWordWrap(True)
        chalice_layout.addWidget(self.lbl_chalice_desc)

        card_layout.addWidget(chalice_frame)

        # 3. Роли в квестах
        card_layout.addWidget(QLabel("🌿 Ступени и роли в Вольном Древе:"))
        self.roles_scroll = QScrollArea()
        self.roles_scroll.setWidgetResizable(True)
        self.roles_scroll.setFixedHeight(85)
        self.roles_scroll.setStyleSheet("background: transparent; border: none;")

        self.roles_container = QWidget()
        self.roles_container.setStyleSheet("background: transparent;")
        self.roles_layout = QVBoxLayout(self.roles_container)
        self.roles_layout.setContentsMargins(0, 0, 0, 0)
        self.roles_layout.setSpacing(4)
        self.roles_scroll.setWidget(self.roles_container)
        card_layout.addWidget(self.roles_scroll)

        # 4. Приватность и ПИН-код на этом устройстве
        pin_frame = QFrame()
        pin_frame.setStyleSheet("""
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 10px;
            padding: 8px;
        """)
        pin_box = QHBoxLayout(pin_frame)
        pin_box.setSpacing(10)

        self.lbl_pin_status = QLabel()
        self.lbl_pin_status.setStyleSheet("color: #e2e8f0; font-size: 12px;")
        pin_box.addWidget(self.lbl_pin_status)
        pin_box.addStretch()

        self.btn_set_pin = QPushButton("Настроить ПИН")
        self.btn_set_pin.clicked.connect(self._open_change_pin)
        pin_box.addWidget(self.btn_set_pin)

        self.btn_remove_pin = QPushButton("Удалить")
        self.btn_remove_pin.clicked.connect(self._remove_pin)
        pin_box.addWidget(self.btn_remove_pin)

        card_layout.addWidget(pin_frame)

        # 5. Публичный ключ Ed25519
        pk_layout = QHBoxLayout()
        pk_layout.setSpacing(8)
        self.lbl_pubkey = QLabel()
        self.lbl_pubkey.setStyleSheet("color: #64748b; font-family: monospace; font-size: 11px;")
        pk_layout.addWidget(self.lbl_pubkey)

        btn_copy_pk = QPushButton("📋 Копировать ключ")
        btn_copy_pk.setFixedHeight(28)
        btn_copy_pk.setStyleSheet("font-size: 11px; padding: 4px 8px;")
        btn_copy_pk.clicked.connect(self._copy_pubkey)
        pk_layout.addWidget(btn_copy_pk)
        card_layout.addLayout(pk_layout)

        # 6. Кнопки внизу
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(10)

        btn_switch = QPushButton("👤 Сменить игрока")
        btn_switch.clicked.connect(self._switch_player_clicked)
        bottom_layout.addWidget(btn_switch)

        bottom_layout.addStretch()

        btn_close = QPushButton("Закрыть")
        btn_close.setObjectName("primaryBtn")
        btn_close.clicked.connect(self.accept)
        bottom_layout.addWidget(btn_close)

        card_layout.addLayout(bottom_layout)
        main_layout.addWidget(card)

        self._refresh_content()

    def _refresh_content(self) -> None:
        pk = self.node.identity.pubkey
        player = self.node.dag_store.get_player(pk)
        dev_id = self.node.identities_mgr.get_player(pk)

        # Аватар
        avatar_bytes = self.node.get_player_avatar_bytes(pk)
        if not avatar_bytes:
            avatar_bytes = generate_default_avatar_png(self.node.identity.username, pk)
        self.lbl_avatar.setPixmap(make_circular_pixmap(avatar_bytes, size=84))

        # Имя и био
        username = dev_id.username if dev_id else self.node.identity.username
        bio = dev_id.bio if dev_id and dev_id.bio else (player.bio if player and player.bio else "Вольный путник")
        self.lbl_username.setText(username)
        self.lbl_bio.setText(bio)

        # Капли совести
        drops = player.conscience_drops if player else 0
        self.lbl_drops.setText(f"💧 Чаша Души: {drops} капель совести")

        is_neophyte = any(r.role_title == "Неофит" for r in (player.roles if player else []))
        if drops == 0 and is_neophyte:
            self.lbl_chalice_desc.setText(
                "🌿 Вы ступили на стезю квеста «Посвящение» с пустой Чашей. "
                "По завершении квеста наставники определят первоначальный объём капель совести."
            )
        else:
            self.lbl_chalice_desc.setText(
                "Каждая капля совести отражает проверенный в ладу опыт совместной гармоничной жизни."
            )

        # Роли
        while self.roles_layout.count():
            item = self.roles_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        roles = player.roles if player and player.roles else []
        if not roles:
            lbl = QLabel("• Вольный путник (роли пока не присвоены)")
            lbl.setStyleSheet("color: #94a3b8; font-size: 11.5px;")
            self.roles_layout.addWidget(lbl)
        else:
            for r in roles:
                quest_title = "Посвящение" if "posvyashchenie" in r.quest_id else "Воля"
                lbl = QLabel(f"• <strong>{r.role_title}</strong> (квест: {quest_title})")
                lbl.setStyleSheet("color: #e2e8f0; font-size: 12px;")
                self.roles_layout.addWidget(lbl)

        # ПИН-код
        has_pin = dev_id.has_pin if dev_id else False
        if has_pin:
            self.lbl_pin_status.setText("🔒 Вход на этом ПК защищен ПИН-кодом")
            self.btn_set_pin.setText("Сменить ПИН")
            self.btn_remove_pin.setVisible(True)
        else:
            self.lbl_pin_status.setText("🔓 Вход на этом ПК без ПИН-кода")
            self.btn_set_pin.setText("Задать ПИН")
            self.btn_remove_pin.setVisible(False)

        # Публичный ключ
        short_pk = f"Ключ: {pk[:10]}...{pk[-8:]}"
        self.lbl_pubkey.setText(short_pk)
        self.lbl_pubkey.setToolTip(pk)

    def _change_avatar(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите изображение для аватара",
            "",
            "Изображения (*.png *.jpg *.jpeg *.webp)",
        )
        if path:
            try:
                self.node.set_player_avatar(self.node.identity.pubkey, path)
                self._refresh_content()
                self.profile_updated.emit()
            except Exception as e:
                QMessageBox.warning(self, "Ошибка загрузки", f"Не удалось обновить аватар: {e}")

    def _generate_pixel_avatar(self) -> None:
        try:
            import time
            pk = self.node.identity.pubkey
            name = self.node.identity.username
            seed = f"{pk}:{time.time()}"
            png_bytes = generate_default_avatar_png(name, seed)
            self.node.set_player_avatar(pk, png_bytes)
            self._refresh_content()
            self.profile_updated.emit()
        except Exception as e:
            QMessageBox.warning(self, "Ошибка генерации", f"Не удалось сгенерировать тотем: {e}")

    def _open_change_pin(self) -> None:
        dev_id = self.node.identities_mgr.get_player(self.node.identity.pubkey)
        has_pin = dev_id.has_pin if dev_id else False
        modal = ChangePinModal(self.node, has_existing_pin=has_pin, parent=self)
        if modal.exec() == QDialog.Accepted:
            self._refresh_content()

    def _remove_pin(self) -> None:
        dev_id = self.node.identities_mgr.get_player(self.node.identity.pubkey)
        if not dev_id or not dev_id.has_pin:
            return

        pin_modal = PinCodeModal(dev_id, node=self.node, allow_switch_player=False, parent=self)
        if pin_modal.exec() == QDialog.Accepted:
            pin = pin_modal.pin_input.text().strip()
            try:
                self.node.remove_player_pin(dev_id.pubkey, current_pin=pin)
                self._refresh_content()
            except Exception as e:
                QMessageBox.warning(self, "Ошибка", str(e))

    def _copy_pubkey(self) -> None:
        cb = QGuiApplication.clipboard()
        cb.setText(self.node.identity.pubkey)
        QMessageBox.information(
            self,
            "Скопировано",
            "Публичный ключ игрока скопирован в буфер обмена.",
        )

    def _switch_player_clicked(self) -> None:
        self.done(2) # Специальный код для смены игрока


class GlassPlayerPill(QFrame):
    """
    Парящий полупрозрачный профильный бейдж в верхнем левом углу Living Window.
    Отображает: круговой аватар из RocksDB, имя игрока, капли совести 💧 и роль 🌿.
    """

    player_changed = Signal(str) # pubkey

    def __init__(self, node: VolyaNode, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.node = node

        self.setObjectName("glassPlayerPill")
        self.setStyleSheet("""
            #glassPlayerPill {
                background: rgba(14, 20, 36, 0.75);
                border: 1px solid rgba(212, 175, 55, 0.35);
                border-radius: 24px;
            }
            #glassPlayerPill:hover {
                background: rgba(18, 26, 48, 0.88);
                border-color: rgba(212, 175, 55, 0.65);
            }
            QLabel {
                color: #e2e8f0;
                font-family: 'Segoe UI', 'Roboto', sans-serif;
            }
            QPushButton#switchBtn {
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.18);
                border-radius: 12px;
                color: #f1f5f9;
                font-size: 11.5px;
                padding: 4px 10px;
                font-weight: 500;
            }
            QPushButton#switchBtn:hover {
                background: rgba(212, 175, 55, 0.25);
                border-color: #d4af37;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 5, 12, 5)
        layout.setSpacing(10)

        # 1. Круглый аватар
        self.lbl_avatar = QLabel()
        self.lbl_avatar.setFixedSize(38, 38)
        self.lbl_avatar.setCursor(Qt.PointingHandCursor)
        self.lbl_avatar.mousePressEvent = lambda e: self.open_profile()
        layout.addWidget(self.lbl_avatar)

        # 2. Информационный блок: Имя и статус
        info_widget = QWidget()
        info_widget.setCursor(Qt.PointingHandCursor)
        info_widget.mousePressEvent = lambda e: self.open_profile()
        info_layout = QVBoxLayout(info_widget)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(2)

        self.lbl_name = QLabel()
        self.lbl_name.setFont(QFont("Segoe UI", 12, QFont.Bold))
        self.lbl_name.setStyleSheet("color: #f8fafc;")
        info_layout.addWidget(self.lbl_name)

        self.lbl_status = QLabel()
        self.lbl_status.setFont(QFont("Segoe UI", 10.5))
        self.lbl_status.setStyleSheet("color: #67e8f9;")
        info_layout.addWidget(self.lbl_status)

        layout.addWidget(info_widget)

        # 3. Кнопка смены игрока
        self.btn_switch = QPushButton("👤 Сменить")
        self.btn_switch.setObjectName("switchBtn")
        self.btn_switch.setCursor(Qt.PointingHandCursor)
        self.btn_switch.clicked.connect(self.open_player_selection)
        layout.addWidget(self.btn_switch)

        self.refresh()

    def refresh(self) -> None:
        """Перезагрузка данных текущего игрока."""
        pk = self.node.identity.pubkey
        player = self.node.dag_store.get_player(pk)
        dev_id = self.node.identities_mgr.get_player(pk)

        # Имя
        name = dev_id.username if dev_id else self.node.identity.username
        self.lbl_name.setText(name)

        # Капли и роль
        drops = player.conscience_drops if player else 0
        role_title = "Вольный игрок"
        if player and player.roles:
            role_title = player.roles[-1].role_title

        role_icon = "🌿" if role_title == "Неофит" else "🌳"
        self.lbl_status.setText(f"💧 {drops}  •  {role_icon} {role_title}")

        # Аватар
        avatar_bytes = self.node.get_player_avatar_bytes(pk)
        if not avatar_bytes:
            avatar_bytes = generate_default_avatar_png(name, pk)
        pix = make_circular_pixmap(avatar_bytes, size=38)
        self.lbl_avatar.setPixmap(pix)

        self.adjustSize()

    def open_profile(self) -> None:
        """Открытие карточки Души игрока."""
        modal = PlayerProfileModal(self.node, parent=self.window())
        modal.profile_updated.connect(self.refresh)
        res = modal.exec()
        self.refresh()
        if res == 2: # Пользователь нажал "Сменить игрока" внутри профиля
            self.open_player_selection()

    def open_player_selection(self) -> None:
        """Открытие Врат Воли для выбора или добавления игрока."""
        modal = PlayerSelectionModal(self.node, parent=self.window())
        modal.player_selected.connect(self._on_player_switched)
        modal.exec()

    def _on_player_switched(self, new_pubkey: str) -> None:
        self.refresh()
        self.player_changed.emit(new_pubkey)
