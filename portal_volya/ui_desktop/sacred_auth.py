"""
Священный замок авторизации (SacredPinLockWidget).
Эфирный интерфейс без рамок и панелей:
- Аватарка в центре
- Имя игрока сверху
- Прозрачное поле ввода ПИНа справа
- Служебные надписи о попытках и таймауте ниже поля ввода
- Подсвечивающаяся дуга снизу, при наведении выпускающая светящуюся нить к прозрачной кнопке «Сменить»
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPointF, QRectF, QSize, QTimer, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from portal_volya.node import VolyaNode
from portal_volya.storage.device_identities import DevicePlayerIdentity
from portal_volya.ui_desktop.auth_dialogs import make_circular_pixmap
from portal_volya.ui_desktop.avatar_generator import generate_default_avatar_png


class CleanPinInput(QLineEdit):
    """
    Прозрачное поле ввода ПИН-кода без мигающего текстового курсора.
    Отрисовывает деликатные точки в уменьшенном благородном шрифте.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setEchoMode(QLineEdit.Password)
        self.setMaxLength(4)
        self.setAlignment(Qt.AlignCenter)
        self.setFont(QFont("Segoe UI", 13, QFont.Bold))
        self.setCursor(Qt.PointingHandCursor)

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)

        # Повышенная прозрачность фона и тонкой границы
        bg_alpha = 20 if self.hasFocus() else 8
        border_alpha = 110 if self.hasFocus() else 40
        painter.setBrush(QColor(255, 255, 255, bg_alpha))
        painter.setPen(QColor(212, 175, 55, border_alpha))
        painter.drawRoundedRect(rect, 7.0, 7.0)

        # Отрисовка точек без мигающего вертикального указателя |
        text = self.text()
        count = len(text)
        painter.setFont(self.font())

        if count > 0:
            dots = "  ".join(["•"] * count)
            painter.setPen(QColor("#fefae0"))
            painter.drawText(rect, Qt.AlignCenter, dots)
        else:
            # Деликатные полупрозрачные точки-заполнители
            painter.setPen(QColor(255, 255, 255, 50))
            painter.drawText(rect, Qt.AlignCenter, "•  •  •  •")

        painter.end()


class SacredPinLockWidget(QWidget):
    """
    Эфирный замок ПИН-кода без панелей и рамок.
    Парит прямо поверх живого полотна Великого Баньяна.
    """

    authenticated = Signal()
    switch_player_requested = Signal()

    def __init__(
        self,
        node: VolyaNode,
        identity: DevicePlayerIdentity,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.node = node
        self.identity = identity

        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        # Размеры виджета
        self.setFixedSize(500, 260)

        # Геометрические константы
        # Центр аватарки в системе координат виджета
        self.cx = 160.0
        self.cy = 105.0
        self.avatar_size = 96.0
        self.avatar_radius = self.avatar_size / 2.0
        self.arc_radius = self.avatar_radius + 10.0  # 58.0 px

        # Состояние наведения на дугу
        self._arc_hovered = False

        # Таймер остывания (anti-bruteforce)
        self.cooldown_timer = QTimer(self)
        self.cooldown_timer.timeout.connect(self._on_cooldown_tick)
        self.cooldown_remaining = 0

        self._init_ui()
        self._check_initial_cooldown()

    def _init_ui(self) -> None:
        # 1. Имя игрока сверху аватарки (поменьше и поближе к аватарке)
        self.lbl_name = QLabel(self.identity.username, self)
        self.lbl_name.setFont(QFont("Georgia", 13, QFont.Bold))
        self.lbl_name.setStyleSheet("""
            color: #fefae0;
            background: transparent;
            letter-spacing: 1.2px;
        """)
        self.lbl_name.setAlignment(Qt.AlignCenter)
        self.lbl_name.setGeometry(int(self.cx - 120), 28, 240, 24)

        # 2. Аватарка (пиксельный тотем)
        avatar_bytes = self.node.get_player_avatar_bytes(self.identity.pubkey)
        if not avatar_bytes:
            avatar_bytes = generate_default_avatar_png(self.identity.username, self.identity.pubkey)

        pix = make_circular_pixmap(avatar_bytes, size=int(self.avatar_size))
        self.lbl_avatar = QLabel(self)
        self.lbl_avatar.setPixmap(pix)
        self.lbl_avatar.setGeometry(
            int(self.cx - self.avatar_radius),
            int(self.cy - self.avatar_radius),
            int(self.avatar_size),
            int(self.avatar_size),
        )
        self.lbl_avatar.setCursor(Qt.PointingHandCursor)

        # 3. Короткое прозрачное поле для ввода ПИНа (справа от аватарки)
        pin_x = int(self.cx + self.avatar_radius + 22)
        pin_y = int(self.cy - 15)

        self.pin_input = CleanPinInput(self)
        self.pin_input.setGeometry(pin_x, pin_y, 96, 30)
        self.pin_input.textChanged.connect(self._on_pin_changed)

        # 4. Служебные надписи о попытках и таймауте (ниже поля ввода ПИНа)
        self.lbl_status = QLabel("", self)
        self.lbl_status.setFont(QFont("Segoe UI", 10.5))
        self.lbl_status.setStyleSheet("color: #f87171; background: transparent;")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setGeometry(pin_x, pin_y + 36, 210, 46)

        # 5. Прозрачная кнопка «Сменить» (появляется внизу дуги на конце нити)
        btn_w, btn_h = 86, 26
        btn_x = int(self.cx - btn_w / 2)
        btn_y = int(self.cy + self.arc_radius + 28)

        self.btn_switch = QPushButton("Сменить", self)
        self.btn_switch.setGeometry(btn_x, btn_y, btn_w, btn_h)
        self.btn_switch.setCursor(Qt.PointingHandCursor)
        self.btn_switch.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.07);
                border: 1px solid rgba(212, 175, 55, 0.50);
                border-radius: 13px;
                color: #fefae0;
                font-family: 'Segoe UI', sans-serif;
                font-size: 11.5px;
                font-weight: 500;
                padding: 2px 8px;
            }
            QPushButton:hover {
                background: rgba(212, 175, 55, 0.25);
                border-color: #fde047;
                color: #ffffff;
            }
        """)
        self.btn_switch.clicked.connect(self._on_switch_clicked)
        self.btn_switch.setVisible(False)

        # Фокус сразу на поле ввода
        self.pin_input.setFocus()

    def set_identity(self, identity: DevicePlayerIdentity) -> None:
        """Обновление данных игрока."""
        self.identity = identity
        self.lbl_name.setText(self.identity.username)
        avatar_bytes = self.node.get_player_avatar_bytes(self.identity.pubkey)
        if not avatar_bytes:
            avatar_bytes = generate_default_avatar_png(self.identity.username, self.identity.pubkey)
        pix = make_circular_pixmap(avatar_bytes, size=int(self.avatar_size))
        self.lbl_avatar.setPixmap(pix)
        self.pin_input.clear()
        self.lbl_status.setText("")
        self._check_initial_cooldown()

    def _check_initial_cooldown(self) -> None:
        rem = self.node.get_pin_lockout_seconds(self.identity.pubkey)
        if rem > 0:
            self._start_cooldown(rem)
        else:
            self.pin_input.setEnabled(True)
            self.pin_input.setFocus()

    def _start_cooldown(self, seconds: int) -> None:
        self.cooldown_remaining = seconds
        self.pin_input.setEnabled(False)
        self.lbl_status.setStyleSheet("color: #fbbf24; background: transparent;")
        self.lbl_status.setText(f"⏳ Слишком много попыток.\nПодождите {self.cooldown_remaining} сек.")
        self.cooldown_timer.start(1000)

    def _on_cooldown_tick(self) -> None:
        self.cooldown_remaining -= 1
        if self.cooldown_remaining <= 0:
            self.cooldown_timer.stop()
            self.pin_input.setEnabled(True)
            self.pin_input.clear()
            self.pin_input.setFocus()
            self.lbl_status.setStyleSheet("color: #34d399; background: transparent;")
            self.lbl_status.setText("Можно попробовать снова")
        else:
            self.lbl_status.setStyleSheet("color: #fbbf24; background: transparent;")
            self.lbl_status.setText(f"⏳ Слишком много попыток.\nПодождите {self.cooldown_remaining} сек.")

    def _on_pin_changed(self, text: str) -> None:
        if self.cooldown_remaining > 0:
            return
        if len(text.strip()) == 4:
            self._verify_pin()

    def _verify_pin(self) -> None:
        pin = self.pin_input.text().strip()
        if self.identity.verify_pin(pin):
            self.node.reset_failed_pin_attempts(self.identity.pubkey)
            self.authenticated.emit()
        else:
            failed_count, cooldown = self.node.record_failed_pin_attempt(self.identity.pubkey)
            if cooldown > 0:
                self._start_cooldown(cooldown)
            else:
                attempts_left = 3 - failed_count
                self.lbl_status.setStyleSheet("color: #f87171; background: transparent;")
                self.lbl_status.setText(f"Неверный код.\nОсталось попыток: {attempts_left}")
                self.pin_input.selectAll()
                self.pin_input.setFocus()

    def _on_switch_clicked(self) -> None:
        self.switch_player_requested.emit()

    # -------------------------------------------------------------
    # Интерактив: Подсвечивающаяся дуга и светящаяся нить
    # -------------------------------------------------------------

    def mouseMoveEvent(self, event) -> None:
        pos = event.position()
        mx, my = pos.x(), pos.y()

        # Зона интерактивности дуги и кнопки:
        # Вокруг нижней дуги и кнопки «Сменить»
        in_x_range = abs(mx - self.cx) <= (self.arc_radius + 20)
        in_y_range = (self.cy + 15) <= my <= (self.cy + self.arc_radius + 65)

        is_hover = in_x_range and in_y_range

        if is_hover != self._arc_hovered:
            self._arc_hovered = is_hover
            self.btn_switch.setVisible(is_hover)
            self.update()

        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        if self._arc_hovered:
            self._arc_hovered = False
            self.btn_switch.setVisible(False)
            self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        # Координаты дуги
        # Ограничивающий прямоугольник окружности дуги
        arc_box = QRectF(
            self.cx - self.arc_radius,
            self.cy - self.arc_radius,
            2 * self.arc_radius,
            2 * self.arc_radius,
        )

        # Дуга снизу под аватаркой:
        # В Qt угол 270° соответствует нижней точке (6 часов).
        # Охват 100° (от 220° до 320°):
        start_angle = 220 * 16
        span_angle = 100 * 16

        # 1. Отрисовка подсвечивающейся дуги
        if self._arc_hovered:
            # Яркое свечение при наведении
            glow_pen = QPen(QColor(253, 224, 71, 90), 4.5)
            glow_pen.setCapStyle(Qt.RoundCap)
            painter.setPen(glow_pen)
            painter.drawArc(arc_box, start_angle, span_angle)

            core_pen = QPen(QColor(254, 240, 138, 240), 2.0)
            core_pen.setCapStyle(Qt.RoundCap)
            painter.setPen(core_pen)
            painter.drawArc(arc_box, start_angle, span_angle)
        else:
            # Деликатная мягкая дуга в спокойном состоянии
            calm_pen = QPen(QColor(212, 175, 55, 110), 1.8)
            calm_pen.setCapStyle(Qt.RoundCap)
            painter.setPen(calm_pen)
            painter.drawArc(arc_box, start_angle, span_angle)

        # 2. Если наведено: тонкая светящаяся нить от дуги к кнопке
        if self._arc_hovered:
            # Нижняя точка дуги
            arc_bottom_x = self.cx
            arc_bottom_y = self.cy + self.arc_radius

            # Верх кнопки «Сменить»
            btn_top_y = float(self.btn_switch.y())

            # Ореол нити
            thread_glow_pen = QPen(QColor(250, 204, 21, 80), 3.0)
            painter.setPen(thread_glow_pen)
            painter.drawLine(QPointF(arc_bottom_x, arc_bottom_y), QPointF(arc_bottom_x, btn_top_y))

            # Сердцевина нити (тонкая, светящаяся)
            thread_core_pen = QPen(QColor(254, 249, 195, 220), 1.2)
            painter.setPen(thread_core_pen)
            painter.drawLine(QPointF(arc_bottom_x, arc_bottom_y), QPointF(arc_bottom_x, btn_top_y))

            # Искорка в точке касания дуги
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(254, 240, 138, 230)))
            painter.drawEllipse(QPointF(arc_bottom_x, arc_bottom_y), 2.2, 2.2)

            # Искорка в точке касания кнопки
            painter.drawEllipse(QPointF(arc_bottom_x, btn_top_y), 2.0, 2.0)

        painter.end()
