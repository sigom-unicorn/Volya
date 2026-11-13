"""
Центральный парящий виджет Потока сотворчества (QuestFlowStreamView).
Отрисовка нити сока Древа: заглавие потока, эфирные капли (без рамок),
интерактивная капля ввода и создание новых текстовых капель по Кону.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
    QLinearGradient,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from portal_volya.core.models import DropKind, FlowDrop, FlowKind, QuestFlow
from portal_volya.node import VolyaNode
from portal_volya.ui_desktop.auth_dialogs import make_circular_pixmap
from portal_volya.ui_desktop.avatar_generator import generate_default_avatar_png


class EtherealDropItem(QWidget):
    """
    Эфирный квант сотворчества в потоке (капля).
    Полная прозрачность, никаких искусственных рамок и прямоугольных границ.
    Свои капли — справа (тёплый золотистый оттенок).
    Капли собеседников/Эйры — слева (с круглой аватаркой игрока).
    Время капли — снизу справа мелким шрифтом.
    """

    def __init__(
        self,
        drop: FlowDrop,
        is_mine: bool,
        avatar_pixmap: Optional[QPixmap] = None,
        is_night: bool = True,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.drop = drop
        self.is_mine = is_mine
        self.avatar_pixmap = avatar_pixmap
        self.is_night = is_night

        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._build_ui()

    def _format_time(self, iso_str: str) -> str:
        try:
            dt = datetime.fromisoformat(iso_str)
            return dt.strftime("%H:%M")
        except Exception:
            return ""

    def _build_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 6, 12, 6)
        main_layout.setSpacing(10)

        # Контейнер содержимого капли
        bubble = QFrame(self)
        bubble.setAttribute(Qt.WA_TranslucentBackground, True)
        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(12, 8, 12, 6)
        bubble_layout.setSpacing(4)

        # Текст мысли/капли
        lbl_content = QLabel(self.drop.content, bubble)
        lbl_content.setWordWrap(True)
        lbl_content.setTextInteractionFlags(Qt.TextSelectableByMouse)

        # Время внизу справа
        time_str = self._format_time(self.drop.created_at)
        lbl_time = QLabel(time_str, bubble)
        lbl_time.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lbl_time.setStyleSheet("font-size: 10px; color: rgba(255, 255, 255, 0.42); font-family: sans-serif;")

        if self.is_mine:
            # Своя капля (справа, золотистый эфир)
            main_layout.addStretch(1)
            lbl_content.setStyleSheet("""
                font-family: 'Georgia', serif;
                font-size: 13.5px;
                color: #fef08a;
                line-height: 1.45;
                background: transparent;
            """)
            bubble.setStyleSheet("""
                QFrame {
                    background: rgba(234, 179, 8, 0.08);
                    border-radius: 12px;
                }
            """)
            bubble_layout.addWidget(lbl_content)
            bubble_layout.addWidget(lbl_time)
            main_layout.addWidget(bubble, 0)
        else:
            # Чужая капля / Эйра (слева, лунно-серебристый эфир с аватаркой)
            avatar_lbl = QLabel(self)
            avatar_lbl.setFixedSize(32, 32)
            if self.avatar_pixmap and not self.avatar_pixmap.isNull():
                avatar_lbl.setPixmap(self.avatar_pixmap.scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                raw_png = generate_default_avatar_png(self.drop.author_name, size=64)
                pix = make_circular_pixmap(raw_png, 32)
                avatar_lbl.setPixmap(pix)

            main_layout.addWidget(avatar_lbl, 0, Qt.AlignTop)

            lbl_content.setStyleSheet("""
                font-family: 'Georgia', serif;
                font-size: 13.5px;
                color: #f1f5f9;
                line-height: 1.45;
                background: transparent;
            """)
            bubble.setStyleSheet("""
                QFrame {
                    background: rgba(255, 255, 255, 0.07);
                    border-radius: 12px;
                }
            """)
            bubble_layout.addWidget(lbl_content)
            bubble_layout.addWidget(lbl_time)
            main_layout.addWidget(bubble, 0)
            main_layout.addStretch(1)


class DropCreatorControl(QWidget):
    """
    Парящий орган добавления капли в поток:
    1. По центру внизу — символ капли сока Древа (💧).
    2. При наведении — распускается сегментированная окружность (виды капель: Текст, Ресурс...).
    3. При клике на «Текст» — вправо плавно вырастает поле ввода.
    4. При активизации поля — справа от него рождается дуга с окружностью и символом ✔.
    5. Клик по ✔ или нажатие Enter — вливает каплю в поток!
    """

    drop_submitted = Signal(str)  # content

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.setFixedHeight(56)

        # Состояния интерактива
        self._hovered_drop_glyph: bool = False
        self._wheel_expanded: bool = False
        self._text_input_visible: bool = False
        self._hovered_segment: Optional[str] = None  # 'text' | 'audio' | 'artifact'
        self._check_circle_hovered: bool = False

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 4, 16, 4)
        layout.setSpacing(12)

        # Пустой отступ слева для центрирования символа капли
        self.left_spacer = layout.addStretch(1)

        # Кнопка-глиф капли
        self.btn_glyph = QPushButton("💧", self)
        self.btn_glyph.setFixedSize(38, 38)
        self.btn_glyph.setCursor(Qt.PointingHandCursor)
        self.btn_glyph.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.12);
                border: 1.5px solid rgba(254, 240, 138, 0.65);
                border-radius: 19px;
                font-size: 17px;
                color: #fef08a;
            }
            QPushButton:hover {
                background: rgba(254, 240, 138, 0.25);
                border: 1.5px solid rgba(254, 240, 138, 0.95);
            }
        """)
        self.btn_glyph.clicked.connect(self._on_glyph_clicked)
        layout.addWidget(self.btn_glyph, 0, Qt.AlignCenter)

        # Поле ввода текста капли (появляется справа при выборе сегмента «Текст»)
        self.input_text = QLineEdit(self)
        self.input_text.setPlaceholderText("Влей каплю своей мысли в Поток...")
        self.input_text.setFixedHeight(36)
        self.input_text.setMinimumWidth(340)
        self.input_text.setMaximumWidth(480)
        self.input_text.setStyleSheet("""
            QLineEdit {
                background: rgba(14, 20, 36, 0.85);
                border: 1.5px solid rgba(254, 240, 138, 0.45);
                border-radius: 18px;
                padding: 4px 16px;
                color: #f8fafc;
                font-family: 'Georgia', serif;
                font-size: 13.5px;
            }
            QLineEdit:focus {
                border: 1.5px solid rgba(254, 240, 138, 0.90);
                background: rgba(14, 20, 36, 0.95);
            }
        """)
        self.input_text.returnPressed.connect(self._on_submit)
        self.input_text.textChanged.connect(self._on_text_changed)
        self.input_text.setVisible(False)
        layout.addWidget(self.input_text, 0, Qt.AlignCenter)

        # Кнопка отправки ✔ (на дуге справа от поля ввода)
        self.btn_submit = QPushButton("✔", self)
        self.btn_submit.setFixedSize(32, 32)
        self.btn_submit.setCursor(Qt.PointingHandCursor)
        self.btn_submit.setStyleSheet("""
            QPushButton {
                background: rgba(234, 179, 8, 0.22);
                border: 1.5px solid rgba(254, 240, 138, 0.75);
                border-radius: 16px;
                font-size: 14px;
                font-weight: bold;
                color: #fef08a;
            }
            QPushButton:hover {
                background: rgba(234, 179, 8, 0.45);
                border: 1.5px solid #ffffff;
                color: #ffffff;
            }
        """)
        self.btn_submit.clicked.connect(self._on_submit)
        self.btn_submit.setVisible(False)
        layout.addWidget(self.btn_submit, 0, Qt.AlignCenter)

        self.right_spacer = layout.addStretch(1)

    def _on_glyph_clicked(self) -> None:
        """Переключение показа поля ввода текстовой капли."""
        self._text_input_visible = not self._text_input_visible
        self.input_text.setVisible(self._text_input_visible)
        if self._text_input_visible:
            self.input_text.setFocus()
            self.btn_submit.setVisible(True)
        else:
            self.btn_submit.setVisible(False)
        self.update()

    def _on_text_changed(self, text: str) -> None:
        self.btn_submit.setVisible(bool(text.strip()))

    def _on_submit(self) -> None:
        text = self.input_text.text().strip()
        if text:
            self.drop_submitted.emit(text)
            self.input_text.clear()


class QuestFlowStreamView(QFrame):
    """
    Центральный парящий виджет Потока квеста:
    - Сверху: наименование потока и форма (Диалог / Беседа).
    - По центру: прозрачный свиток капель сока Древа без рамок.
    - Внизу: символ капли сока и поле ввода новой капли.
    """

    close_requested = Signal()

    def __init__(self, node: VolyaNode, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.node = node
        self.current_flow: Optional[QuestFlow] = None
        self._avatar_cache: dict[str, QPixmap] = {}

        self.setObjectName("questFlowStream")
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._build_ui()

    def _build_ui(self) -> None:
        # Glassmorphic прозрачное парящее полотно по центру
        self.setStyleSheet("""
            #questFlowStream {
                background: rgba(10, 16, 28, 0.82);
                border: 1.5px solid rgba(255, 255, 255, 0.16);
                border-radius: 24px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        # 1. Верхняя планка: Заглавие потока + крестик сворачивания
        header_bar = QHBoxLayout()
        header_bar.setContentsMargins(8, 0, 8, 4)

        info_box = QVBoxLayout()
        info_box.setSpacing(2)

        self.lbl_title = QLabel("Поток сотворчества", self)
        self.lbl_title.setStyleSheet("""
            font-family: 'Georgia', serif;
            font-size: 17px;
            font-weight: bold;
            color: #f8fafc;
            background: transparent;
        """)
        self.lbl_subtitle = QLabel("Диалог по Кону", self)
        self.lbl_subtitle.setStyleSheet("""
            font-family: sans-serif;
            font-size: 11px;
            color: rgba(254, 240, 138, 0.75);
            background: transparent;
        """)
        info_box.addWidget(self.lbl_title)
        info_box.addWidget(self.lbl_subtitle)
        header_bar.addLayout(info_box, 1)

        # Кнопка закрытия
        btn_close = QPushButton("✕", self)
        btn_close.setFixedSize(28, 28)
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 14px;
                color: rgba(255, 255, 255, 0.65);
                font-size: 12px;
            }
            QPushButton:hover {
                background: rgba(239, 68, 68, 0.35);
                border-color: #ef4444;
                color: #ffffff;
            }
        """)
        btn_close.clicked.connect(self.close_requested.emit)
        header_bar.addWidget(btn_close, 0, Qt.AlignTop)
        layout.addLayout(header_bar)

        # Тонкая разделительная золотистая нить под шапкой
        sep = QFrame(self)
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: rgba(254, 240, 138, 0.20);")
        layout.addWidget(sep)

        # 2. Область прокрутки капель
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAttribute(Qt.WA_TranslucentBackground, True)
        self.scroll_area.viewport().setAttribute(Qt.WA_TranslucentBackground, True)
        self.scroll_area.viewport().setStyleSheet("background: transparent;")
        self.scroll_area.setStyleSheet("""
            QScrollArea, QScrollArea > QWidget > QWidget {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background: rgba(255, 255, 255, 0.05);
                width: 6px;
                border-radius: 3px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: rgba(254, 240, 138, 0.35);
                border-radius: 3px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(254, 240, 138, 0.65);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        self.drops_container = QWidget()
        self.drops_container.setAttribute(Qt.WA_TranslucentBackground, True)
        self.drops_layout = QVBoxLayout(self.drops_container)
        self.drops_layout.setContentsMargins(4, 8, 4, 8)
        self.drops_layout.setSpacing(10)
        self.drops_layout.addStretch(1)

        self.scroll_area.setWidget(self.drops_container)
        layout.addWidget(self.scroll_area, 1)

        # 3. Нижний парящий орган добавления капли
        self.drop_creator = DropCreatorControl(self)
        self.drop_creator.drop_submitted.connect(self._on_drop_submitted)
        layout.addWidget(self.drop_creator, 0)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)

        # Тёмная глубинная стеклянная подложка
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(10, 16, 28, 240))
        painter.drawRoundedRect(rect, 22.0, 22.0)

        # Мягкий золотистый ободок
        painter.setPen(QPen(QColor(254, 240, 138, 85), 1.4))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect, 22.0, 22.0)
        painter.end()

    def load_flow(self, flow_id: str) -> None:
        """Загрузка и отображение потока квеста."""
        flow = self.node.dag_store.get_quest_flow(flow_id)
        if not flow:
            return
        self.current_flow = flow

        self.lbl_title.setText(flow.title)
        kind_name = flow.kind.value if hasattr(flow.kind, "value") else str(flow.kind)
        parts_count = len(flow.participants)
        self.lbl_subtitle.setText(f"{kind_name} • Участников: {parts_count}")

        # Очистка предыдущих капель
        while self.drops_layout.count() > 1:
            item = self.drops_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        # Загрузка доступных капель потока
        drops = self.node.get_accessible_drops(flow.id)
        my_pk = self.node.identity.pubkey

        for drop in drops:
            is_mine = (drop.author_pubkey == my_pk)
            avatar_pix = self._get_player_avatar(drop.author_pubkey, drop.author_name)
            drop_item = EtherealDropItem(drop, is_mine=is_mine, avatar_pixmap=avatar_pix, is_night=True)
            self.drops_layout.insertWidget(self.drops_layout.count() - 1, drop_item)

        # Прокрутка вниз
        QTimer.singleShot(60, self._scroll_to_bottom)

    def _scroll_to_bottom(self) -> None:
        vsb = self.scroll_area.verticalScrollBar()
        if vsb:
            vsb.setValue(vsb.maximum())

    def _get_player_avatar(self, pubkey: str, username: str) -> QPixmap:
        if pubkey in self._avatar_cache:
            return self._avatar_cache[pubkey]

        raw_bytes = self.node.get_player_avatar_bytes(pubkey)
        if raw_bytes:
            pix = make_circular_pixmap(raw_bytes, 64)
        else:
            png = generate_default_avatar_png(username, size=64)
            pix = make_circular_pixmap(png, 64)

        self._avatar_cache[pubkey] = pix
        return pix

    def _on_drop_submitted(self, content: str) -> None:
        """Добавление капли сока в активный поток."""
        if not self.current_flow:
            return

        qid = self.current_flow.quest_id or "quest-volya-root"
        fid = self.current_flow.id

        user_drop, eira_drop = self.node.post_flow_drop(
            quest_id=qid,
            flow_id=fid,
            content=content,
            kind=DropKind.TEXT,
        )

        my_pk = self.node.identity.pubkey
        user_pix = self._get_player_avatar(user_drop.author_pubkey, user_drop.author_name)
        user_item = EtherealDropItem(user_drop, is_mine=True, avatar_pixmap=user_pix, is_night=True)
        self.drops_layout.insertWidget(self.drops_layout.count() - 1, user_item)

        if eira_drop:
            eira_pix = self._get_player_avatar(eira_drop.author_pubkey, eira_drop.author_name)
            eira_item = EtherealDropItem(eira_drop, is_mine=False, avatar_pixmap=eira_pix, is_night=True)
            self.drops_layout.insertWidget(self.drops_layout.count() - 1, eira_item)

        QTimer.singleShot(50, self._scroll_to_bottom)
