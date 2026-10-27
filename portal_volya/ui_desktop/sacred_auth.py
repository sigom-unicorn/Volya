"""
Священный замок авторизации (SacredPinLockWidget).
Эфирный интерфейс без рамок и панелей прямо поверх полотна Великого Баньяна:
1. Кнопки действий расположены строго вертикально друг под другом:
   - Верхняя кнопка соединена нитью с нижней точкой дуги аватарки
   - Каждая последующая кнопка соединена нитью с предыдущей кнопкой
2. Режим ввода ПИН-кода (MODE_PIN):
   - Верхняя кнопка «Сменить» (появляется ТОЛЬКО если на компьютере есть другие игроки)
   - При нажатии «Сменить» справа рядом с кнопкой появляется список доступных игроков:
     * Соединен с кнопкой «Сменить» светящейся нитью от правого края кнопки к левой стенке списка
     * Имеет тонкую стенку ТОЛЬКО сбоку (слева, куда причаливает нить)
     * Элементы списка разделяются горизонтальными нитями
     * Задний фон туманно-прозрачный (днем золотистый туман, ночью лунный белый)
     * Шрифт имени игрока — черный
     * Элемент списка — круглая аватарка небольшого размера и имя игрока рядом
   - Ниже кнопки «Новый» и «Войти по ключу»
3. Режим создания нового игрока (MODE_NEW):
   - Поля ввода справа: «Имя», «Био», «ПИН» без внешних заголовков (подсказки внутри)
   - Вертикальная цепочка кнопок: «Добавить аватар» -> «Вступить в Посвящение» -> «Отмена»
4. Режим входа по ключу (MODE_KEY):
   - Совсем пустая аватарка (эфирное кольцо с золотым пунктиром)
   - Поля справа: «Ключ», «ПИН»
   - При вводе 64-значного ключа загружается имя (сверху) и аватарка из БД
   - Если найден: цепочка кнопок «Войти в Портал» -> «Отмена»
   - Если не найден: только кнопка «Отмена»
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from PySide6.QtCore import (
    QPointF,
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
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRegularExpressionValidator,
)
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from portal_volya.core.crypto import KeyPair
from portal_volya.node import VolyaNode
from portal_volya.storage.device_identities import DevicePlayerIdentity
from portal_volya.ui_desktop.auth_dialogs import make_circular_pixmap
from portal_volya.ui_desktop.avatar_generator import (
    generate_default_avatar_png,
    process_custom_avatar_png,
)


def make_empty_avatar_pixmap(size: int = 96) -> QPixmap:
    """Создаёт изображение совсем пустой эфирной аватарки с деликатным золотым кольцом."""
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.Antialiasing, True)

    rect = QRectF(2.5, 2.5, float(size - 5), float(size - 5))
    painter.setBrush(QColor(255, 255, 255, 8))
    pen = QPen(QColor(212, 175, 55, 75), 1.2)
    pen.setStyle(Qt.DashLine)
    painter.setPen(pen)
    painter.drawEllipse(rect)
    painter.end()
    return QPixmap.fromImage(img)


class CleanPinInput(QLineEdit):
    """
    Прозрачное поле ввода ПИН-кода без мигающего текстового курсора.
    Отрисовывает деликатные черные точки в уменьшенном благородном шрифте
    на полупрозрачном туманном фоне (днем золотистом, ночью лунном).
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setEchoMode(QLineEdit.Password)
        self.setMaxLength(4)
        self.setValidator(QRegularExpressionValidator(QRegularExpression(r"^[0-9]{0,4}$"), self))
        self.setAlignment(Qt.AlignCenter)
        self.setFont(QFont("Segoe UI", 13, QFont.Bold))
        self.setCursor(Qt.PointingHandCursor)

    def is_night(self) -> bool:
        p = self.parent()
        if p and hasattr(p, "is_night"):
            return p.is_night()
        h = datetime.now().hour
        return not (7 <= h < 19)

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

        night = self.is_night()
        if night:
            bg_color = QColor(255, 255, 255, 175 if self.hasFocus() else 145)
            border_color = QColor(226, 232, 240, 220 if self.hasFocus() else 140)
        else:
            bg_color = QColor(254, 240, 138, 185 if self.hasFocus() else 155)
            border_color = QColor(212, 175, 55, 220 if self.hasFocus() else 140)

        painter.setBrush(QBrush(bg_color))
        painter.setPen(QPen(border_color, 1.2))
        painter.drawRoundedRect(rect, 7.0, 7.0)

        # Отрисовка черных точек без мигающего вертикального указателя |
        text = self.text()
        count = len(text)
        painter.setFont(self.font())

        if count > 0:
            dots = "  ".join(["•"] * count)
            painter.setPen(QColor("#000000"))
            painter.drawText(rect, Qt.AlignCenter, dots)
        else:
            # Чёткие, различимые точки-заполнители
            painter.setPen(QColor(0, 0, 0, 190))
            painter.drawText(rect, Qt.AlignCenter, "•  •  •  •")

        painter.end()


class SacredLineEdit(QLineEdit):
    """
    Поле ввода для формы создания игрока и входа по ключу.
    Отрисовывает чёткие, контрастные и легко читаемые подсказки (placeholder)
    насыщенным чёрным цветом при пустом поле, предотвращая блёклость на фоне листвы.
    """

    def __init__(self, placeholder: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._sacred_placeholder = placeholder

    def setPlaceholderText(self, text: str) -> None:
        self._sacred_placeholder = text
        super().setPlaceholderText("")

    def placeholderText(self) -> str:
        return self._sacred_placeholder

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if not self.text() and self._sacred_placeholder:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing, True)
            # Насыщенный черный цвет подсказки для идеальной читаемости на тумане
            pen_color = QColor(0, 0, 0, 160) if self.hasFocus() else QColor(0, 0, 0, 220)
            painter.setPen(pen_color)
            f = self.font()
            f.setFamily("Segoe UI")
            f.setPointSize(9)
            f.setWeight(QFont.DemiBold)
            painter.setFont(f)
            rect = QRectF(self.rect()).adjusted(12, 0, -10, 0)
            painter.drawText(rect, Qt.AlignVCenter | Qt.AlignLeft, self._sacred_placeholder)
            painter.end()


class PlayerSwitchItem(QFrame):
    """
    Элемент списка игроков:
    - Круглая аватарка небольшого размера (полная, без обрезки)
    - Рядом вольное имя игрока (черный цвет шрифта)
    """

    clicked = Signal(object)  # DevicePlayerIdentity

    def __init__(
        self,
        node: VolyaNode,
        identity: DevicePlayerIdentity,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.identity = identity
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(34)
        self.setObjectName("playerSwitchItem")
        self.setStyleSheet("""
            QFrame#playerSwitchItem {
                background: transparent;
                border: none;
                border-radius: 6px;
            }
            QFrame#playerSwitchItem:hover {
                background: rgba(0, 0, 0, 0.08);
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 8, 2)
        layout.setSpacing(8)

        # Небольшая круглая аватарка (24x24)
        avatar_bytes = node.get_player_avatar_bytes(identity.pubkey)
        if not avatar_bytes:
            avatar_bytes = generate_default_avatar_png(identity.username, identity.pubkey)
        pix = make_circular_pixmap(avatar_bytes, size=24)

        lbl_av = QLabel(self)
        lbl_av.setPixmap(pix)
        lbl_av.setFixedSize(24, 24)
        lbl_av.setStyleSheet("background: transparent; border: none; padding: 0px; margin: 0px;")
        layout.addWidget(lbl_av)

        # Имя игрока рядом (черный цвет шрифта)
        lbl_name = QLabel(identity.username, self)
        lbl_name.setFont(QFont("Segoe UI", 11, QFont.Bold))
        lbl_name.setStyleSheet("""
            color: #000000;
            background: transparent;
            border: none;
            padding: 0px;
            margin: 0px;
            font-weight: 700;
            letter-spacing: 0.3px;
        """)
        layout.addWidget(lbl_name)
        layout.addStretch()

    def mousePressEvent(self, event) -> None:
        self.clicked.emit(self.identity)


class PlayerSwitchListWidget(QFrame):
    """
    Парящий туманный список игроков справа от кнопки «Сменить»:
    - Располагается справа от кнопки
    - Имеет тонкую стенку ТОЛЬКО сбоку (слева, где соединяется с нитью от кнопки)
    - Элементы списка разделяются горизонтальными нитями
    - Задний фон туманный (днем золотистый туман, ночью лунный белый)
    - Цвет шрифта: черный
    """

    player_selected = Signal(object)  # DevicePlayerIdentity

    def __init__(
        self,
        node: VolyaNode,
        lock_widget: SacredPinLockWidget,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.node = node
        self.lock_widget = lock_widget
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.setFixedWidth(170)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(8, 4, 8, 4)
        self.layout.setSpacing(0)
        self._row_count = 0

    def populate(self, current_pubkey: str) -> int:
        while self.layout.count():
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        other_players = [
            p for p in self.node.identities_mgr.list_players()
            if p.pubkey != current_pubkey
        ]
        self._row_count = len(other_players)

        for p in other_players:
            row = PlayerSwitchItem(self.node, p, self)
            row.clicked.connect(self.player_selected.emit)
            self.layout.addWidget(row)

        self.adjustSize()
        self.update()
        return self._row_count

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)

        is_night = self.lock_widget.is_night()

        # Туманный фон: днем золотистый туман, ночью лунный (белый)
        if is_night:
            fog_brush = QColor(255, 255, 255, 52)
            wall_color = QColor(226, 232, 240, 200)
            divider_glow = QColor(255, 255, 255, 60)
            divider_core = QColor(241, 245, 249, 150)
        else:
            fog_brush = QColor(254, 240, 138, 55)
            wall_color = QColor(212, 175, 55, 200)
            divider_glow = QColor(250, 204, 21, 55)
            divider_core = QColor(254, 249, 195, 160)

        # 1. Заливка туманного полупрозрачного фона (со скруглением правых углов)
        path = QPainterPath()
        r_radius = 8.0
        path.moveTo(rect.left(), rect.top())
        path.lineTo(rect.right() - r_radius, rect.top())
        path.quadTo(rect.right(), rect.top(), rect.right(), rect.top() + r_radius)
        path.lineTo(rect.right(), rect.bottom() - r_radius)
        path.quadTo(rect.right(), rect.bottom(), rect.right() - r_radius, rect.bottom())
        path.lineTo(rect.left(), rect.bottom())
        path.closeSubpath()

        painter.fillPath(path, QBrush(fog_brush))

        # 2. Тонкая стенка ТОЛЬКО сбоку (слева, та что соединяется с нитью от кнопки)
        wall_pen = QPen(wall_color, 1.5)
        wall_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(wall_pen)
        painter.drawLine(
            QPointF(rect.left(), rect.top() + 1.5),
            QPointF(rect.left(), rect.bottom() - 1.5),
        )

        # 3. Элементы списка разделяются горизонтальными нитями
        if self._row_count > 1:
            row_h = (rect.height() - 8) / self._row_count
            for i in range(1, self._row_count):
                div_y = rect.top() + 4 + i * row_h
                p_start = QPointF(rect.left() + 6, div_y)
                p_end = QPointF(rect.right() - 6, div_y)

                # Ореол нити-разделителя
                painter.setPen(QPen(divider_glow, 2.0))
                painter.drawLine(p_start, p_end)

                # Сердцевина нити-разделителя
                painter.setPen(QPen(divider_core, 0.9))
                painter.drawLine(p_start, p_end)

        painter.end()


class SacredPinLockWidget(QWidget):
    """
    Эфирный замок авторизации, создания и импорта игрока.
    Парит прямо поверх живого полотна Великого Баньяна без рамок и панелей.
    Кнопки расположены последовательно сверху вниз, соединенные нитями.
    """

    MODE_PIN = "pin"
    MODE_NEW = "new"
    MODE_KEY = "key"

    authenticated = Signal()
    switch_player_requested = Signal()

    def __init__(
        self,
        node: VolyaNode,
        identity: Optional[DevicePlayerIdentity] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.node = node
        self.identity = identity

        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        # Размеры виджета (комфортное пространство для цепочки кнопок и полей ввода)
        self.setFixedSize(640, 380)

        # Геометрические константы
        self.cx = 210.0
        self.cy = 100.0
        self.avatar_size = 96.0
        self.avatar_radius = self.avatar_size / 2.0
        self.arc_radius = self.avatar_radius + 10.0  # 58.0 px

        # Текущий режим интерфейса
        self.mode = self.MODE_PIN if identity is not None else self.MODE_NEW

        # Состояния интерактива
        self._arc_hovered = False
        self._switch_list_visible = False

        # Данные формы создания
        self._custom_avatar_bytes: Optional[bytes] = None

        # Данные формы входа по ключу
        self._key_found_player: Optional[Any] = None
        self._key_found_pubkey: Optional[str] = None
        self._key_found_privkey: Optional[str] = None

        # Состояния темы и остывания
        self._last_is_night: Optional[bool] = None
        self.cooldown_timer = QTimer(self)
        self.cooldown_timer.timeout.connect(self._on_cooldown_tick)
        self.cooldown_remaining = 0

        self._init_ui()
        if self.identity:
            self._check_initial_cooldown()

    def is_night(self) -> bool:
        """Определяет, день сейчас или ночь в живом мире Баньяна."""
        p = self.parent()
        if p and hasattr(p, "world_widget") and p.world_widget:
            canvas = getattr(p.world_widget, "canvas", None)
            if canvas and hasattr(canvas, "celestial"):
                return canvas.celestial.get_night_factor() >= 0.5
        h = datetime.now().hour
        return not (7 <= h < 19)

    def _apply_theme_styles(self) -> None:
        """
        Применяет полупрозрачный туманный фон (днем золотистый, ночью лунный)
        и чистый черный цвет шрифта (#000000) для всех кнопок и полей ввода.
        """
        night = self.is_night()
        if night:
            # Лунный туман (белый)
            btn_bg = "rgba(255, 255, 255, 0.38)"
            btn_hover_bg = "rgba(255, 255, 255, 0.60)"
            btn_border = "1px solid rgba(226, 232, 240, 0.65)"
            btn_hover_border = "#ffffff"

            primary_bg = "rgba(255, 255, 255, 0.50)"
            primary_hover_bg = "rgba(255, 255, 255, 0.70)"
            primary_border = "1.5px solid rgba(226, 232, 240, 0.90)"

            input_bg = "rgba(255, 255, 255, 0.58)"
            input_focus_bg = "rgba(255, 255, 255, 0.78)"
            input_border = "1.2px solid rgba(226, 232, 240, 0.75)"
            input_focus_border = "#ffffff"
        else:
            # Золотистый туман (днем)
            btn_bg = "rgba(254, 240, 138, 0.42)"
            btn_hover_bg = "rgba(254, 240, 138, 0.65)"
            btn_border = "1px solid rgba(212, 175, 55, 0.65)"
            btn_hover_border = "#fde047"

            primary_bg = "rgba(254, 240, 138, 0.55)"
            primary_hover_bg = "rgba(254, 240, 138, 0.75)"
            primary_border = "1.5px solid #d4af37"

            input_bg = "rgba(254, 240, 138, 0.62)"
            input_focus_bg = "rgba(254, 240, 138, 0.82)"
            input_border = "1.2px solid rgba(212, 175, 55, 0.75)"
            input_focus_border = "#fde047"

        self.btn_style = f"""
            QPushButton {{
                background: {btn_bg};
                border: {btn_border};
                border-radius: 13px;
                color: #000000;
                font-family: 'Segoe UI', sans-serif;
                font-size: 11.5px;
                font-weight: 600;
                padding: 2px 10px;
            }}
            QPushButton:hover {{
                background: {btn_hover_bg};
                border-color: {btn_hover_border};
                color: #000000;
            }}
            QPushButton#primarySacredBtn {{
                background: {primary_bg};
                border: {primary_border};
                color: #000000;
                font-weight: 700;
            }}
            QPushButton#primarySacredBtn:hover {{
                background: {primary_hover_bg};
                border-color: {btn_hover_border};
                color: #000000;
            }}
        """

        self.input_style = f"""
            QLineEdit {{
                background: {input_bg};
                border: {input_border};
                border-radius: 8px;
                color: #000000;
                font-family: 'Segoe UI', sans-serif;
                font-size: 12px;
                font-weight: 600;
                padding: 4px 10px;
            }}
            QLineEdit:focus {{
                background: {input_focus_bg};
                border-color: {input_focus_border};
            }}
        """

        if hasattr(self, "btn_switch"):
            for b in (
                self.btn_switch, self.btn_new, self.btn_key,
                self.btn_add_avatar, self.btn_submit_new, self.btn_cancel_new,
                self.btn_submit_key, self.btn_cancel_key,
            ):
                b.setStyleSheet(self.btn_style)

        if hasattr(self, "input_new_name"):
            for inp in (
                self.input_new_name, self.input_new_bio, self.input_new_pin,
                self.input_key, self.input_key_pin,
            ):
                inp.setStyleSheet(self.input_style)

        if hasattr(self, "pin_input"):
            self.pin_input.update()

    def _init_ui(self) -> None:
        self._last_is_night = self.is_night()
        self._apply_theme_styles()

        # 1. Имя игрока сверху аватарки
        name_text = self.identity.username if self.identity else ""
        self.lbl_name = QLabel(name_text, self)
        self.lbl_name.setFont(QFont("Georgia", 13, QFont.Bold))
        self.lbl_name.setStyleSheet("""
            color: #fefae0;
            background: transparent;
            letter-spacing: 1.2px;
        """)
        self.lbl_name.setAlignment(Qt.AlignCenter)
        self.lbl_name.setGeometry(int(self.cx - 130), 22, 260, 24)

        # 2. Аватарка в центре
        self.lbl_avatar = QLabel(self)
        self.lbl_avatar.setGeometry(
            int(self.cx - self.avatar_radius),
            int(self.cy - self.avatar_radius),
            int(self.avatar_size),
            int(self.avatar_size),
        )
        self.lbl_avatar.setCursor(Qt.PointingHandCursor)
        self._refresh_avatar_for_current_identity()

        # =========================================================
        # 3. ЭЛЕМЕНТЫ РЕЖИМА ВВОДА ПИН-КОДА (MODE_PIN)
        # =========================================================
        field_x = int(self.cx + self.avatar_radius + 40)

        self.pin_input = CleanPinInput(self)
        self.pin_input.setGeometry(field_x, 86, 100, 32)
        self.pin_input.textChanged.connect(self._on_pin_changed)

        self.lbl_status = QLabel("", self)
        self.lbl_status.setFont(QFont("Segoe UI", 10.5))
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setGeometry(field_x, 126, 310, 48)
        self._set_status_label(self.lbl_status, "")

        # =========================================================
        # 4. ЭЛЕМЕНТЫ РЕЖИМА РОЖДЕНИЯ НОВОГО ИГРОКА (MODE_NEW)
        # =========================================================
        new_w = 280

        self.input_new_name = SacredLineEdit(parent=self)
        self.input_new_name.setPlaceholderText("Имя")
        self.input_new_name.setStyleSheet(self.input_style)
        self.input_new_name.setGeometry(field_x, 56, new_w, 28)
        self.input_new_name.textChanged.connect(self._on_new_name_changed)
        self.input_new_name.returnPressed.connect(lambda: self.input_new_bio.setFocus())

        self.input_new_bio = SacredLineEdit(parent=self)
        self.input_new_bio.setPlaceholderText("Био")
        self.input_new_bio.setStyleSheet(self.input_style)
        self.input_new_bio.setGeometry(field_x, 90, new_w, 28)
        self.input_new_bio.returnPressed.connect(lambda: self.input_new_pin.setFocus())

        self.input_new_pin = SacredLineEdit(parent=self)
        self.input_new_pin.setPlaceholderText("ПИН (4 цифры, по желанию)")
        self.input_new_pin.setEchoMode(QLineEdit.Password)
        self.input_new_pin.setMaxLength(4)
        self.input_new_pin.setValidator(
            QRegularExpressionValidator(QRegularExpression(r"^[0-9]{0,4}$"), self)
        )
        self.input_new_pin.setStyleSheet(self.input_style)
        self.input_new_pin.setGeometry(field_x, 124, new_w, 28)
        self.input_new_pin.returnPressed.connect(self._on_submit_new_clicked)

        self.lbl_new_status = QLabel("", self)
        self.lbl_new_status.setFont(QFont("Segoe UI", 10.5))
        self.lbl_new_status.setWordWrap(True)
        self.lbl_new_status.setGeometry(field_x, 156, 310, 58)
        self._set_status_label(self.lbl_new_status, "")

        # =========================================================
        # 5. ЭЛЕМЕНТЫ РЕЖИМА ВХОДА ПО КЛЮЧУ (MODE_KEY)
        # =========================================================
        key_w = 310

        self.input_key = SacredLineEdit(parent=self)
        self.input_key.setPlaceholderText("Ключ (64 шестнадцатеричных символа)")
        self.input_key.setStyleSheet(self.input_style)
        self.input_key.setGeometry(field_x, 72, key_w, 30)
        self.input_key.textChanged.connect(self._on_key_text_changed)
        self.input_key.returnPressed.connect(lambda: self.input_key_pin.setFocus())

        self.input_key_pin = SacredLineEdit(parent=self)
        self.input_key_pin.setPlaceholderText("ПИН (4 цифры, по желанию)")
        self.input_key_pin.setEchoMode(QLineEdit.Password)
        self.input_key_pin.setMaxLength(4)
        self.input_key_pin.setValidator(
            QRegularExpressionValidator(QRegularExpression(r"^[0-9]{0,4}$"), self)
        )
        self.input_key_pin.setStyleSheet(self.input_style)
        self.input_key_pin.setGeometry(field_x, 110, key_w, 30)
        self.input_key_pin.returnPressed.connect(self._on_submit_key_clicked)

        self.lbl_key_status = QLabel("", self)
        self.lbl_key_status.setFont(QFont("Segoe UI", 10.5))
        self.lbl_key_status.setWordWrap(True)
        self.lbl_key_status.setGeometry(field_x, 146, 310, 48)
        self._set_status_label(self.lbl_key_status, "")

        # =========================================================
        # 6. КНОПКИ ДЕЙСТВИЙ (ВЕРТИКАЛЬНАЯ ЦЕПОЧКА ПОД ДУГОЙ)
        # =========================================================
        # Кнопки для MODE_PIN
        self.btn_switch = QPushButton("Сменить", self)
        self.btn_switch.setStyleSheet(self.btn_style)
        self.btn_switch.setCursor(Qt.PointingHandCursor)
        self.btn_switch.clicked.connect(self._toggle_switch_list)

        self.btn_new = QPushButton("Новый", self)
        self.btn_new.setStyleSheet(self.btn_style)
        self.btn_new.setCursor(Qt.PointingHandCursor)
        self.btn_new.clicked.connect(lambda: self.switch_mode(self.MODE_NEW))

        self.btn_key = QPushButton("Войти по ключу", self)
        self.btn_key.setStyleSheet(self.btn_style)
        self.btn_key.setCursor(Qt.PointingHandCursor)
        self.btn_key.clicked.connect(lambda: self.switch_mode(self.MODE_KEY))

        # Кнопки для MODE_NEW
        self.btn_add_avatar = QPushButton("Добавить аватар", self)
        self.btn_add_avatar.setStyleSheet(self.btn_style)
        self.btn_add_avatar.setCursor(Qt.PointingHandCursor)
        self.btn_add_avatar.clicked.connect(self._on_add_avatar_clicked)

        self.btn_submit_new = QPushButton("Вступить в Посвящение", self)
        self.btn_submit_new.setObjectName("primarySacredBtn")
        self.btn_submit_new.setStyleSheet(self.btn_style)
        self.btn_submit_new.setCursor(Qt.PointingHandCursor)
        self.btn_submit_new.clicked.connect(self._on_submit_new_clicked)

        self.btn_cancel_new = QPushButton("Отмена", self)
        self.btn_cancel_new.setStyleSheet(self.btn_style)
        self.btn_cancel_new.setCursor(Qt.PointingHandCursor)
        self.btn_cancel_new.clicked.connect(lambda: self.switch_mode(self.MODE_PIN))

        # Кнопки для MODE_KEY
        self.btn_submit_key = QPushButton("Войти в Портал", self)
        self.btn_submit_key.setObjectName("primarySacredBtn")
        self.btn_submit_key.setStyleSheet(self.btn_style)
        self.btn_submit_key.setCursor(Qt.PointingHandCursor)
        self.btn_submit_key.clicked.connect(self._on_submit_key_clicked)

        self.btn_cancel_key = QPushButton("Отмена", self)
        self.btn_cancel_key.setStyleSheet(self.btn_style)
        self.btn_cancel_key.setCursor(Qt.PointingHandCursor)
        self.btn_cancel_key.clicked.connect(lambda: self.switch_mode(self.MODE_PIN))

        # 7. Туманный список игроков справа от кнопки «Сменить»
        self.switch_list_widget = PlayerSwitchListWidget(self.node, self, self)
        self.switch_list_widget.player_selected.connect(self._on_switch_player_selected)
        self.switch_list_widget.setVisible(False)

        # Применяем стили тумана и видимость по текущему режиму
        self._apply_theme_styles()
        self.switch_mode(self.mode)

    def _set_status_label(self, lbl: QLabel, text: str, kind: str = "warning") -> None:
        """Деликатное отображение подсказок, сожаления о занятом имени и статуса."""
        if not text:
            lbl.setStyleSheet("background: transparent; border: none;")
            lbl.setText("")
            return

        if kind == "success":
            color = "#6ee7b7"
            border = "rgba(52, 211, 153, 0.45)"
        elif kind == "info":
            color = "#fef08a"
            border = "rgba(250, 204, 21, 0.45)"
        else:  # warning / regret / notice
            color = "#fef08a"
            border = "rgba(250, 204, 21, 0.50)"

        lbl.setStyleSheet(f"""
            QLabel {{
                color: {color};
                background: rgba(15, 23, 42, 0.72);
                border: 1px solid {border};
                border-radius: 8px;
                padding: 5px 9px;
                font-family: 'Segoe UI', sans-serif;
                font-size: 10.5px;
                font-weight: 500;
            }}
        """)
        lbl.setText(text)

    # -------------------------------------------------------------
    # Управление режимами (PIN, NEW, KEY)
    # -------------------------------------------------------------

    def switch_mode(self, mode: str) -> None:
        """Переключение режима формы."""
        self.mode = mode
        self._switch_list_visible = False
        self.switch_list_widget.setVisible(False)

        is_pin = (self.mode == self.MODE_PIN)
        is_new = (self.mode == self.MODE_NEW)
        is_key = (self.mode == self.MODE_KEY)

        # PIN элементы
        self.pin_input.setVisible(is_pin)
        self.lbl_status.setVisible(is_pin)

        # NEW элементы
        self.input_new_name.setVisible(is_new)
        self.input_new_bio.setVisible(is_new)
        self.input_new_pin.setVisible(is_new)
        self.lbl_new_status.setVisible(is_new)

        # KEY элементы
        self.input_key.setVisible(is_key)
        self.input_key_pin.setVisible(is_key)
        self.lbl_key_status.setVisible(is_key)

        if is_pin:
            self._set_status_label(self.lbl_status, "")
            if self.identity:
                self.lbl_name.setText(self.identity.username)
                self._refresh_avatar_for_current_identity()
                self._check_initial_cooldown()
            else:
                self.lbl_name.setText("")
                self.lbl_avatar.setPixmap(make_empty_avatar_pixmap(int(self.avatar_size)))

        elif is_new:
            self.lbl_name.setText("")
            self._custom_avatar_bytes = None
            self.input_new_name.clear()
            self.input_new_bio.clear()
            self.input_new_pin.clear()
            self._set_status_label(self.lbl_new_status, "")
            raw = generate_default_avatar_png("Игрок", "genesis_preview", size=128)
            self.lbl_avatar.setPixmap(make_circular_pixmap(raw, size=int(self.avatar_size)))
            self.input_new_name.setFocus()

        elif is_key:
            self.lbl_name.setText("")
            self.input_key.clear()
            self.input_key_pin.clear()
            self._set_status_label(self.lbl_key_status, "")
            self._key_found_player = None
            self._key_found_pubkey = None
            self._key_found_privkey = None
            self.lbl_avatar.setPixmap(make_empty_avatar_pixmap(int(self.avatar_size)))
            self.input_key.setFocus()

        self._relayout_buttons()
        self._update_buttons_visibility()
        self.update()

    def _get_other_players(self) -> List[DevicePlayerIdentity]:
        if not self.identity:
            return self.node.identities_mgr.list_players()
        return [
            p for p in self.node.identities_mgr.list_players()
            if p.pubkey != self.identity.pubkey
        ]

    def _get_active_chain(self) -> List[QPushButton]:
        """Возвращает упорядоченный список кнопок цепочки для текущего режима (сверху вниз)."""
        chain: List[QPushButton] = []
        if self.mode == self.MODE_PIN:
            has_others = len(self._get_other_players()) > 0
            if has_others:
                chain.append(self.btn_switch)
            chain.append(self.btn_new)
            chain.append(self.btn_key)
        elif self.mode == self.MODE_NEW:
            chain.append(self.btn_add_avatar)
            chain.append(self.btn_submit_new)
            chain.append(self.btn_cancel_new)
        elif self.mode == self.MODE_KEY:
            if self._key_found_player is not None:
                chain.append(self.btn_submit_key)
            chain.append(self.btn_cancel_key)
        return chain

    def _relayout_buttons(self) -> None:
        """Позиционирование кнопок строго вертикально одна под другой."""
        chain = self._get_active_chain()
        start_y = 180
        btn_h = 26
        gap = 14

        # Скрываем все кнопки за пределами активной цепочки
        all_btns = [
            self.btn_switch,
            self.btn_new,
            self.btn_key,
            self.btn_add_avatar,
            self.btn_submit_new,
            self.btn_cancel_new,
            self.btn_submit_key,
            self.btn_cancel_key,
        ]
        for b in all_btns:
            if b not in chain:
                b.setGeometry(0, 0, 0, 0)

        widths_map = {
            self.btn_switch: 116,
            self.btn_new: 116,
            self.btn_key: 130,
            self.btn_add_avatar: 134,
            self.btn_submit_new: 172,
            self.btn_cancel_new: 104,
            self.btn_submit_key: 140,
            self.btn_cancel_key: 104,
        }

        for i, btn in enumerate(chain):
            w = widths_map.get(btn, 120)
            x = int(self.cx - w / 2.0)
            y = start_y + i * (btn_h + gap)
            btn.setGeometry(x, y, w, btn_h)

        # Список игроков располагается СПРАВА от кнопки «Сменить»
        if self.btn_switch in chain:
            # Справа от кнопки с зазором 24px для светящейся нити
            list_x = int(self.btn_switch.x() + self.btn_switch.width() + 24)
            list_y = int(self.btn_switch.y() - 6)
            self.switch_list_widget.move(list_x, list_y)

    def _update_buttons_visibility(self) -> None:
        """Показ кнопок активной цепочки при наведении мыши."""
        show = self._arc_hovered
        chain = self._get_active_chain()

        all_btns = [
            self.btn_switch,
            self.btn_new,
            self.btn_key,
            self.btn_add_avatar,
            self.btn_submit_new,
            self.btn_cancel_new,
            self.btn_submit_key,
            self.btn_cancel_key,
        ]
        for b in all_btns:
            if b in chain:
                b.setVisible(show)
            else:
                b.setVisible(False)

        if not show:
            self._switch_list_visible = False
            self.switch_list_widget.setVisible(False)
        else:
            self.switch_list_widget.setVisible(self._switch_list_visible)

    # -------------------------------------------------------------
    # Логика режима ввода ПИН-кода
    # -------------------------------------------------------------

    def set_identity(self, identity: DevicePlayerIdentity) -> None:
        """Обновление данных игрока для входа."""
        self.identity = identity
        self.lbl_name.setText(self.identity.username)
        self._refresh_avatar_for_current_identity()
        self.pin_input.clear()
        self._set_status_label(self.lbl_status, "")
        self.switch_mode(self.MODE_PIN)

    def _refresh_avatar_for_current_identity(self) -> None:
        if not self.identity:
            self.lbl_avatar.setPixmap(make_empty_avatar_pixmap(int(self.avatar_size)))
            return
        avatar_bytes = self.node.get_player_avatar_bytes(self.identity.pubkey)
        if not avatar_bytes:
            avatar_bytes = generate_default_avatar_png(self.identity.username, self.identity.pubkey)
        pix = make_circular_pixmap(avatar_bytes, size=int(self.avatar_size))
        self.lbl_avatar.setPixmap(pix)

    def _check_initial_cooldown(self) -> None:
        if not self.identity:
            return
        rem = self.node.get_pin_lockout_seconds(self.identity.pubkey)
        if rem > 0:
            self._start_cooldown(rem)
        else:
            self.pin_input.setEnabled(True)
            self.pin_input.setFocus()

    def _start_cooldown(self, seconds: int) -> None:
        self.cooldown_remaining = seconds
        self.pin_input.setEnabled(False)
        self._set_status_label(
            self.lbl_status,
            f"⏳ Слишком много попыток.\nПодождите {self.cooldown_remaining} сек.",
            kind="warning",
        )
        self.cooldown_timer.start(1000)

    def _on_cooldown_tick(self) -> None:
        self.cooldown_remaining -= 1
        if self.cooldown_remaining <= 0:
            self.cooldown_timer.stop()
            self.pin_input.setEnabled(True)
            self.pin_input.clear()
            self.pin_input.setFocus()
            self._set_status_label(self.lbl_status, "Можно попробовать снова", kind="success")
        else:
            self._set_status_label(
                self.lbl_status,
                f"⏳ Слишком много попыток.\nПодождите {self.cooldown_remaining} сек.",
                kind="warning",
            )

    def _on_pin_changed(self, text: str) -> None:
        if self.cooldown_remaining > 0 or not self.identity:
            return
        if len(text.strip()) == 4:
            self._verify_pin()

    def _verify_pin(self) -> None:
        if not self.identity:
            return
        pin = self.pin_input.text().strip()
        if self.identity.verify_pin(pin):
            self.node.reset_failed_pin_attempts(self.identity.pubkey)
            self.node.switch_player(self.identity.pubkey, pin=pin)
            self.authenticated.emit()
        else:
            failed_count, cooldown = self.node.record_failed_pin_attempt(self.identity.pubkey)
            if cooldown > 0:
                self._start_cooldown(cooldown)
            else:
                attempts_left = 3 - failed_count
                self._set_status_label(
                    self.lbl_status,
                    f"Неверный код. Осталось попыток: {attempts_left}",
                    kind="warning",
                )
                self.pin_input.selectAll()
                self.pin_input.setFocus()

    def _toggle_switch_list(self) -> None:
        """Открытие или закрытие списка других игроков справа от кнопки «Сменить»."""
        self._switch_list_visible = not self._switch_list_visible
        if self._switch_list_visible:
            cur_pk = self.identity.pubkey if self.identity else ""
            count = self.switch_list_widget.populate(cur_pk)
            if count == 0:
                self._switch_list_visible = False
                self.switch_list_widget.setVisible(False)
            else:
                # Позиционируем справа от кнопки Сменить
                list_x = int(self.btn_switch.x() + self.btn_switch.width() + 24)
                list_y = int(self.btn_switch.y() - 6)
                self.switch_list_widget.move(list_x, list_y)
                self.switch_list_widget.setVisible(True)
        else:
            self.switch_list_widget.setVisible(False)
        self.update()

    def _on_switch_player_selected(self, new_ident: DevicePlayerIdentity) -> None:
        """Переключение на выбранного игрока из списка."""
        self._switch_list_visible = False
        self.switch_list_widget.setVisible(False)
        if new_ident.has_pin:
            self.set_identity(new_ident)
            self.pin_input.setFocus()
        else:
            self.node.switch_player(new_ident.pubkey)
            self.authenticated.emit()

    # -------------------------------------------------------------
    # Логика режима создания нового игрока (MODE_NEW)
    # -------------------------------------------------------------

    def _on_new_name_changed(self, text: str) -> None:
        if self._custom_avatar_bytes is None:
            name = text.strip() or "Игрок"
            raw = generate_default_avatar_png(name, name + "genesis_seed_preview", size=128)
            self.lbl_avatar.setPixmap(make_circular_pixmap(raw, size=int(self.avatar_size)))

    def _on_add_avatar_clicked(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите изображение аватара",
            "",
            "Изображения (*.png *.jpg *.jpeg *.webp)",
        )
        if path:
            try:
                self._custom_avatar_bytes = process_custom_avatar_png(path, size=256)
                pix = make_circular_pixmap(self._custom_avatar_bytes, size=int(self.avatar_size))
                self.lbl_avatar.setPixmap(pix)
                self._set_status_label(self.lbl_new_status, "Аватар успешно загружен", kind="success")
            except Exception as e:
                self._set_status_label(self.lbl_new_status, f"Не удалось загрузить аватар: {e}", kind="warning")

    def _on_submit_new_clicked(self) -> None:
        name = self.input_new_name.text().strip()
        if not name:
            self._set_status_label(
                self.lbl_new_status,
                "Укажите вольное имя игрока, пожалуйста",
                kind="warning",
            )
            self.input_new_name.setFocus()
            return

        pin = self.input_new_pin.text().strip()
        if pin and (len(pin) != 4 or not pin.isdigit()):
            self._set_status_label(
                self.lbl_new_status,
                "ПИН-код должен состоять ровно из 4 цифр",
                kind="warning",
            )
            self.input_new_pin.setFocus()
            return

        bio = self.input_new_bio.text().strip()
        try:
            player, dev_id = self.node.create_neophyte_player(
                username=name,
                bio=bio,
                pin=pin if pin else None,
                custom_avatar_data=self._custom_avatar_bytes,
            )
            self.identity = dev_id
            self.authenticated.emit()
        except Exception as e:
            msg = str(e)
            if msg.lower().startswith("ошибка:"):
                msg = msg[7:].strip()
            self._set_status_label(self.lbl_new_status, msg, kind="warning")

    # -------------------------------------------------------------
    # Логика режима входа по ключу (MODE_KEY)
    # -------------------------------------------------------------

    def _on_key_text_changed(self, text: str) -> None:
        key = text.strip()
        if len(key) == 64:
            try:
                kp = KeyPair.from_private_hex(key)
                pubkey = kp.public_hex

                found = None
                if hasattr(self.node, "dag_store") and self.node.dag_store:
                    try:
                        found = self.node.dag_store.get_player(pubkey)
                    except Exception:
                        pass
                if not found and hasattr(self.node, "identities_mgr") and self.node.identities_mgr:
                    try:
                        found = self.node.identities_mgr.get_player(pubkey)
                    except Exception:
                        pass

                if found:
                    self._key_found_player = found
                    self._key_found_pubkey = pubkey
                    self._key_found_privkey = key
                    self.lbl_name.setText(found.username)

                    avatar_bytes = self.node.get_player_avatar_bytes(pubkey)
                    if not avatar_bytes:
                        avatar_bytes = generate_default_avatar_png(found.username, pubkey)
                    self.lbl_avatar.setPixmap(make_circular_pixmap(avatar_bytes, size=int(self.avatar_size)))
                    self._set_status_label(self.lbl_key_status, "Игрок найден в Игре", kind="success")
                else:
                    self._key_found_player = None
                    self._key_found_pubkey = None
                    self._key_found_privkey = None
                    self.lbl_name.setText("")
                    self.lbl_avatar.setPixmap(make_empty_avatar_pixmap(int(self.avatar_size)))
                    self._set_status_label(
                        self.lbl_key_status,
                        "Игрок с таким ключом пока не найден в Игре",
                        kind="warning",
                    )
            except Exception:
                self._key_found_player = None
                self._key_found_pubkey = None
                self._key_found_privkey = None
                self.lbl_name.setText("")
                self.lbl_avatar.setPixmap(make_empty_avatar_pixmap(int(self.avatar_size)))
                self._set_status_label(
                    self.lbl_key_status,
                    "Некорректный формат приватного ключа",
                    kind="warning",
                )
        else:
            self._key_found_player = None
            self._key_found_pubkey = None
            self._key_found_privkey = None
            self.lbl_name.setText("")
            self.lbl_avatar.setPixmap(make_empty_avatar_pixmap(int(self.avatar_size)))
            self._set_status_label(self.lbl_key_status, "")

        self._relayout_buttons()
        self._update_buttons_visibility()
        self.update()

    def _on_submit_key_clicked(self) -> None:
        if not self._key_found_player or not self._key_found_privkey:
            return

        pin = self.input_key_pin.text().strip()
        if pin and (len(pin) != 4 or not pin.isdigit()):
            self._set_status_label(
                self.lbl_key_status,
                "ПИН-код должен состоять ровно из 4 цифр",
                kind="warning",
            )
            return

        try:
            self.node.import_player_key(
                private_key_hex=self._key_found_privkey,
                username=self._key_found_player.username,
                pin=pin if pin else None,
            )
            self.authenticated.emit()
        except Exception as e:
            self._set_status_label(self.lbl_key_status, f"Ошибка входа: {e}", kind="warning")

    # -------------------------------------------------------------
    # Интерактив: Наведение мыши, Подсвечивающаяся дуга и нити
    # -------------------------------------------------------------

    def mouseMoveEvent(self, event) -> None:
        pos = event.position()
        mx, my = pos.x(), pos.y()

        if self._switch_list_visible:
            is_hover = True
        else:
            # Зона дуги и вертикального ствола кнопок
            arc_zone = (abs(mx - self.cx) <= (self.arc_radius + 35)) and (
                (self.cy + 10) <= my <= (self.cy + self.arc_radius + 50)
            )
            btn_spine_zone = (abs(mx - self.cx) <= 100) and (170 <= my <= 315)
            is_hover = arc_zone or btn_spine_zone

        if is_hover != self._arc_hovered:
            self._arc_hovered = is_hover
            self._update_buttons_visibility()
            self.update()

        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        if not self._switch_list_visible:
            if self._arc_hovered:
                self._arc_hovered = False
                self._update_buttons_visibility()
                self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if self._switch_list_visible:
            pos = event.position()
            if not self.switch_list_widget.geometry().contains(int(pos.x()), int(pos.y())):
                self._switch_list_visible = False
                self.switch_list_widget.setVisible(False)
                self.update()
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:
        cur_night = self.is_night()
        if self._last_is_night != cur_night:
            self._last_is_night = cur_night
            self._apply_theme_styles()

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        # Координаты дуги
        arc_box = QRectF(
            self.cx - self.arc_radius,
            self.cy - self.arc_radius,
            2 * self.arc_radius,
            2 * self.arc_radius,
        )

        start_angle = 220 * 16
        span_angle = 100 * 16

        # 1. Отрисовка дуги
        if self._arc_hovered:
            glow_pen = QPen(QColor(253, 224, 71, 90), 4.5)
            glow_pen.setCapStyle(Qt.RoundCap)
            painter.setPen(glow_pen)
            painter.drawArc(arc_box, start_angle, span_angle)

            core_pen = QPen(QColor(254, 240, 138, 240), 2.0)
            core_pen.setCapStyle(Qt.RoundCap)
            painter.setPen(core_pen)
            painter.drawArc(arc_box, start_angle, span_angle)
        else:
            calm_pen = QPen(QColor(212, 175, 55, 110), 1.8)
            calm_pen.setCapStyle(Qt.RoundCap)
            painter.setPen(calm_pen)
            painter.drawArc(arc_box, start_angle, span_angle)

        # 2. Функция отрисовки светящейся нити с искорками
        def draw_thread(p1: QPointF, p2: QPointF) -> None:
            glow_line_pen = QPen(QColor(250, 204, 21, 75), 3.0)
            painter.setPen(glow_line_pen)
            painter.drawLine(p1, p2)

            core_line_pen = QPen(QColor(254, 249, 195, 230), 1.2)
            painter.setPen(core_line_pen)
            painter.drawLine(p1, p2)

            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(254, 240, 138, 240)))
            painter.drawEllipse(p1, 2.2, 2.2)
            painter.drawEllipse(p2, 2.0, 2.0)

        # 3. Отрисовка последовательной вертикальной цепочки нитей:
        # Дуга -> Верхняя кнопка -> Следующая кнопка -> ...
        if self._arc_hovered:
            chain = [b for b in self._get_active_chain() if b.isVisible()]
            if chain:
                # Верхняя кнопка соединена нитью с нижней точкой дуги
                arc_bottom = QPointF(self.cx, self.cy + self.arc_radius)
                top_btn_in = QPointF(self.cx, float(chain[0].y()))
                draw_thread(arc_bottom, top_btn_in)

                # Каждая последующая кнопка соединена нитью с предыдущей
                for i in range(len(chain) - 1):
                    p_from = QPointF(self.cx, float(chain[i].y() + chain[i].height()))
                    p_to = QPointF(self.cx, float(chain[i + 1].y()))
                    draw_thread(p_from, p_to)

            # 4. Нить от правого края кнопки «Сменить» к левой тонкой стенке списка игроков (справа)
            if self._switch_list_visible and self.switch_list_widget.isVisible() and self.btn_switch.isVisible():
                btn_right_mid = QPointF(
                    float(self.btn_switch.x() + self.btn_switch.width()),
                    float(self.btn_switch.y() + self.btn_switch.height() / 2.0),
                )
                list_left_mid = QPointF(
                    float(self.switch_list_widget.x()),
                    float(self.btn_switch.y() + self.btn_switch.height() / 2.0),
                )
                draw_thread(btn_right_mid, list_left_mid)

        painter.end()
