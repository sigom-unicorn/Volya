"""
Сакральное Древо Квестов (QuestTreeHUD) Вселенной «Воля».
Нитевой интерфейс выбора квеста на базе живой сакральной геометрии:
- Наведение на аватарку игрока -> появление дуги справа.
- Наведение на дугу -> протягивание золотой нити к двойной спирали.
- Спираль плавно рисуется нитью, и её вторая ветвь разматывается вниз, образуя стебель Древа.
- Нанизывание бусинок-квестов (диаметр 48px, со своими священными аватарками):
  * Корневые квесты (ROOT_CHILD) — ветвятся влево от стебля.
  * Вольницы (TRUNK) — ветвятся вправо от стебля.
  * Дома — от Вольниц влево-вверх.
  * Другие квесты — от Вольниц вправо-вниз.
- Выбор квеста:
  * Клик по бусинке -> плавное перемещение по нити на место спирали и масштабирование 48 -> 64px.
  * Клик по спирали -> сворачивание дерева и выбор корневого квеста «Воля».
- Постоянное присутствие активного квеста на месте спирали (диаметр 64px).
- Всплывающие надписи квестов при наведении.
"""

from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import (
    QEasingCurve,
    QPointF,
    QRectF,
    QTimer,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QImage,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
    QLinearGradient,
)
from PySide6.QtWidgets import QLineEdit, QPushButton, QWidget

from portal_volya.core.models import (
    DropKind,
    FlowDrop,
    FlowKind,
    Player,
    Quest,
    QuestFlow,
    TreeTier,
)
from portal_volya.node import VolyaNode
from portal_volya.ui_desktop.auth_dialogs import make_circular_pixmap
from portal_volya.ui_desktop.avatar_generator import generate_default_avatar_png


class QuestTreeNode:
    """Узел квеста на живом Древе со своей бусинкой, позицией и аватаркой."""

    def __init__(
        self,
        quest: Quest,
        role_title: str,
        target_pos: QPointF,
        branch_type: str,  # 'root_child' | 'trunk' | 'house' | 'other'
        parent_pos: QPointF,
        pixmap: QPixmap,
    ) -> None:
        self.quest = quest
        self.role_title = role_title
        self.target_pos = target_pos
        self.branch_type = branch_type
        self.parent_pos = parent_pos
        self.pixmap = pixmap

        # Текущее анимированное состояние
        self.current_pos = QPointF(target_pos)
        self.current_size = 48.0
        self.hovered = False
        self.opacity = 1.0


class FlowNextButton(QWidget):
    """
    Сакральный выпуклый (embossed / 3D) диск с символом '>' внутри поля ввода.
    Обеспечивает четкое центрирование, объемную светотень и реакцию на клик.
    """

    clicked = Signal()

    def __init__(self, parent: QWidget, hud: 'QuestTreeHUD') -> None:
        super().__init__(parent)
        self.hud = hud
        self.setFixedSize(22, 22)
        self.setCursor(Qt.PointingHandCursor)
        self._hovered = False
        self._pressed = False
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_Hover, True)

    def enterEvent(self, event) -> None:
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._pressed = True
            self.update()
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self._pressed:
            self._pressed = False
            self.update()
            if self.rect().contains(event.pos()):
                self.clicked.emit()
            event.accept()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        w = self.width()
        h = self.height()
        c = QPointF(w / 2.0, h / 2.0)
        radius = 9.5

        # 1. Мягкая внешняя тень под диском
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(6, 9, 16, 180))
        painter.drawEllipse(QPointF(c.x(), c.y() + 1.0), radius, radius)

        # 2. Выпуклый купол диска (сферический градиент)
        grad = QLinearGradient(c.x() - radius, c.y() - radius, c.x() + radius, c.y() + radius)
        if self._hovered:
            grad.setColorAt(0.0, QColor(48, 62, 94, 255))
            grad.setColorAt(0.5, QColor(28, 38, 60, 255))
            grad.setColorAt(1.0, QColor(14, 20, 36, 255))
            border_pen = QPen(QColor(254, 240, 138, 240), 1.2)
        else:
            grad.setColorAt(0.0, QColor(36, 48, 74, 250))
            grad.setColorAt(0.5, QColor(22, 30, 48, 250))
            grad.setColorAt(1.0, QColor(12, 16, 30, 250))
            border_pen = QPen(QColor(254, 240, 138, 170), 1.1)

        painter.setBrush(QBrush(grad))
        painter.setPen(border_pen)
        painter.drawEllipse(c, radius, radius)

        # 3. Выпуклый (embossed / 3D) символ '>'
        # Эффект рельефа за счет светотени: темная тень снизу-справа, яркий блик сверху-слева
        font = QFont("Georgia", 10)
        font.setBold(True)
        painter.setFont(font)

        offset_y = 1.0 if self._pressed else 0.0
        # Точное геометрическое и оптическое центрирование символа '>'
        text_rect = QRectF(0.8, -0.4 + offset_y, w, h)

        # Теневая грань снизу-справа (объемное углубление рельефа)
        painter.setPen(QColor(4, 6, 12, 240))
        painter.drawText(text_rect.translated(0.8, 1.1), Qt.AlignCenter, ">")

        # Верхний светящийся блик (освещенная фаска символа)
        painter.setPen(QColor(255, 255, 255, 190 if self._hovered else 130))
        painter.drawText(text_rect.translated(-0.6, -0.6), Qt.AlignCenter, ">")

        # Основное рельефное золотое тело символа
        core_color = QColor(254, 240, 138, 255) if self._hovered else QColor(245, 218, 90, 235)
        painter.setPen(core_color)
        painter.drawText(text_rect, Qt.AlignCenter, ">")

        painter.end()


class QuestTreeHUD(QWidget):
    """
    Парящий оверлей навигатора Древа Квестов.
    Располагается поверх живого полотна Баньяна и не перекрывает клики по пустому миру.
    """

    quest_selected = Signal(str)  # quest_id
    flow_selected = Signal(str)   # flow_id

    def __init__(self, node: VolyaNode, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.node = node

        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMouseTracking(True)

        # Геометрия опорных точек
        # Центр аватарки игрока в координатах окна
        self.avatar_center = QPointF(72.0, 72.0)
        self.avatar_radius = 48.0
        self.arc_radius = 58.0

        # Центр двойной спирали (на той же горизонтали правее, увеличено на 30%: 148 * 1.30 = 192.4 -> 264.0)
        self.spiral_center = QPointF(264.0, 72.0)
        self.spiral_radius = 32.0  # диаметр 64px

        # Кэш аватарок квестов
        self._quest_pixmaps: Dict[str, QPixmap] = {}

        # Выбран ли квест (до первого выбора логотип не виден, после выбора дуга, нить и выбранный квест видны постоянно)
        self.has_selected_quest: bool = False
        self.active_quest_id: str = "quest-volya-root"
        self.active_quest_title: str = "Воля"
        self._active_quest_pixmap: Optional[QPixmap] = self.get_volya_logo_pixmap(size=128)

        # Список узлов открытого дерева
        self.tree_nodes: List[QuestTreeNode] = []

        # Состояния интерактива дерева
        self._avatar_hovered: bool = False
        self._arc_visible: bool = False
        self._arc_hovered: bool = False
        self._tree_open: bool = False
        self._hovered_bead: Optional[QuestTreeNode] = None
        self._spiral_hovered: bool = False

        # Ожидающий узел: сначала дерево полностью исчезает, затем бусинка перелетает к спирали
        self._pending_selection_node: Optional[QuestTreeNode] = None

        # Анимация разворачивания дерева (0.0 -> 1.0)
        self._unfold_progress: float = 0.0
        self._unfold_target: float = 0.0

        # Анимация перемещения бусинки на место спирали (0.0 -> 1.0)
        self._glide_progress: float = 0.0
        self._gliding_node: Optional[QuestTreeNode] = None
        self._glide_start_pos: QPointF = QPointF()

        # ---------------------------------------------------------
        # Состояния дуг Потоков выбранного квеста (Выбор и Создание)
        # ---------------------------------------------------------
        self._flow_menu_mode: str = "none"  # 'none' | 'both' | 'select' | 'create'
        self._sel_flow_kind: Optional[FlowKind] = None
        self._create_flow_kind: Optional[FlowKind] = None
        self._create_step: str = "idle"  # 'idle' | 'title' | 'players'
        self._selected_participants: set[str] = set()

        self._quest_flows_cache: list[QuestFlow] = []
        self._quest_players_cache: list[Player] = []
        self._player_avatar_cache: dict[str, QPixmap] = {}

        self._hovered_flow_kind_disc: Optional[FlowKind] = None
        self._hovered_flow_item: Optional[QuestFlow] = None
        self._hovered_create_segment: Optional[FlowKind] = None
        self._hovered_create_next_btn: bool = False
        self._hovered_create_confirm_btn: bool = False
        self._hovered_player_item: Optional[Player] = None

        # Поле ввода названия создаваемого потока
        self.flow_title_input = QLineEdit(self)
        self.flow_title_input.setPlaceholderText("Имя потока...")
        self.flow_title_input.setFixedHeight(28)
        self.flow_title_input.setFixedWidth(190)
        self.flow_title_input.setStyleSheet("""
            QLineEdit {
                background: rgba(14, 20, 36, 0.94);
                border: 1.5px solid rgba(254, 240, 138, 0.60);
                border-radius: 14px;
                padding: 2px 28px 2px 12px;
                color: #fef08a;
                font-family: 'Georgia', serif;
                font-size: 12px;
            }
            QLineEdit:focus {
                border: 1.5px solid rgba(254, 240, 138, 0.95);
                background: rgba(14, 20, 36, 0.98);
            }
        """)
        self.flow_title_input.setVisible(False)
        self.flow_title_input.textChanged.connect(self._on_flow_title_text_changed)

        # Выпуклый диск кнопки '>' внутри поля ввода справа
        self.flow_next_btn = FlowNextButton(self.flow_title_input, self)
        self.flow_next_btn.clicked.connect(self._proceed_to_players)

        # ---------------------------------------------------------
        # Состояние живого Потока капель на полотне мира (без окон)
        # ---------------------------------------------------------
        self._active_flow_id: Optional[str] = None
        self._active_flow: Optional[QuestFlow] = None
        self._active_flow_drops: list[FlowDrop] = []
        self._flow_spiral_center = QPointF(520.0, 72.0)
        self._flow_spiral_radius = 20.0
        self._flow_spiral_hovered: bool = False
        self._flow_drop_btn_hovered: bool = False
        self._flow_scroll_y: float = 0.0
        self._flow_input_active: bool = False

        # Поле ввода новой капли на левой ветви (рядом с кнопкой-каплей)
        self.flow_drop_input = QLineEdit(self)
        self.flow_drop_input.setPlaceholderText("Капля мысли в поток...")
        self.flow_drop_input.setFixedHeight(26)
        self.flow_drop_input.setFixedWidth(215)
        self.flow_drop_input.setStyleSheet("""
            QLineEdit {
                background: rgba(14, 20, 36, 0.94);
                border: 1.5px solid rgba(254, 240, 138, 0.60);
                border-radius: 13px;
                padding: 2px 28px 2px 10px;
                color: #FEF08A;
                font-family: 'Georgia', serif;
                font-size: 11px;
            }
            QLineEdit:focus {
                border: 1.5px solid rgba(254, 240, 138, 0.95);
                background: rgba(14, 20, 36, 0.98);
            }
        """)
        self.flow_drop_input.setVisible(False)
        self.flow_drop_input.returnPressed.connect(self._submit_new_flow_drop)

        # Кнопка подтверждения '✔' внутри поля ввода капли
        self.flow_drop_submit_btn = QPushButton("✔", self.flow_drop_input)
        self.flow_drop_submit_btn.setFixedSize(20, 20)
        self.flow_drop_submit_btn.setCursor(Qt.PointingHandCursor)
        self.flow_drop_submit_btn.setStyleSheet("""
            QPushButton {
                background: rgba(234, 179, 8, 0.25);
                border: 1px solid rgba(254, 240, 138, 0.70);
                border-radius: 10px;
                color: #FEF08A;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background: rgba(234, 179, 8, 0.50);
                border: 1px solid rgba(254, 240, 138, 0.95);
            }
        """)
        self.flow_drop_submit_btn.move(215, 3)
        self.flow_drop_submit_btn.clicked.connect(self._submit_new_flow_drop)

        # Таймер плавного закрытия меню потоков при уходе мыши
        self._flow_close_timer = QTimer(self)
        self._flow_close_timer.setSingleShot(True)
        self._flow_close_timer.timeout.connect(self._on_flow_menu_close_timeout)

        # Таймер плавной анимации (60 FPS)
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._on_anim_tick)
        self._anim_timer.start(16)

        # Таймер закрытия при уходе курсора
        self._auto_close_timer = QTimer(self)
        self._auto_close_timer.setSingleShot(True)
        self._auto_close_timer.timeout.connect(self._on_auto_close_timeout)

        self.refresh_quests()
        self.refresh_flows_and_players()

    # -------------------------------------------------------------
    # Определение времени суток (День / Лунная ночь)
    # -------------------------------------------------------------

    def is_night(self) -> bool:
        p = self.window()
        if p and p is not self and hasattr(p, "is_night"):
            return p.is_night()
        now = datetime.now()
        h = now.hour + now.minute / 60.0
        return not (7.0 <= h < 18.8)

    # -------------------------------------------------------------
    # Загрузка и генерация аватарок квестов
    # -------------------------------------------------------------

    def get_volya_logo_pixmap(self, size: int = 128) -> QPixmap:
        """Получение или кэширование круглого аватара Вольного Древа из модели квеста «Воля» (quest.logo)."""
        cache_key = f"quest-volya-root:{size}"
        if cache_key in self._quest_pixmaps:
            return self._quest_pixmaps[cache_key]

        logo_bytes = None
        # 1. Загружаем модель корневого квеста «Воля» из DAGStore и извлекаем его логотип
        try:
            root_q = self.node.dag_store.get_quest("quest-volya-root")
            if root_q and root_q.logo:
                logo_bytes = self.node.dag_store.get_quest_logo(root_q)
        except Exception:
            logo_bytes = None

        # 2. Резервный источник: файл на диске
        if not logo_bytes:
            candidates = [
                Path(__file__).resolve().parent.parent.parent / "volya_logo.jpg",
                Path("volya_logo.jpg"),
            ]
            logo_path = next((p for p in candidates if p.exists()), None)
            if logo_path:
                try:
                    logo_bytes = logo_path.read_bytes()
                except Exception:
                    pass

        if logo_bytes:
            try:
                img = QImage()
                img.loadFromData(logo_bytes)
                if not img.isNull():
                    # Кадрируем круглый медальон без белых угловых полей (111, 111, 1826, 1826)
                    if img.width() > 500 and img.height() > 500:
                        cropped = img.copy(111, 111, 1826, 1826)
                    else:
                        cropped = img

                    scaled = cropped.scaled(
                        size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
                    )

                    target = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
                    target.fill(Qt.transparent)

                    painter = QPainter(target)
                    painter.setRenderHint(QPainter.Antialiasing, True)
                    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
                    clip_path = QPainterPath()
                    clip_path.addEllipse(0, 0, size, size)
                    painter.setClipPath(clip_path)
                    painter.drawImage(0, 0, scaled)
                    painter.end()

                    pix = QPixmap.fromImage(target)
                    self._quest_pixmaps[cache_key] = pix
                    return pix
            except Exception:
                pass

        # Резервный аватар, если файл логотипа недоступен
        fallback_bytes = generate_default_avatar_png("Воля", "quest-volya-root:Воля", size=size)
        pix = make_circular_pixmap(fallback_bytes, size=size)
        self._quest_pixmaps[cache_key] = pix
        return pix

    def get_double_spiral_pixmap(self, size: int = 96) -> QPixmap:
        """Получение пиксмапа сакральной двойной спирали."""
        if hasattr(self, "_cached_double_spiral_pixmap") and self._cached_double_spiral_pixmap:
            return self._cached_double_spiral_pixmap
        base_dir = Path(__file__).parent / "assets" / "images"
        gold_path = base_dir / "sacred_double_spiral_gold.webp"
        if not gold_path.exists():
            gold_path = base_dir / "sacred_double_spiral_gold.png"
        if gold_path.exists():
            pix = QPixmap(str(gold_path))
            self._cached_double_spiral_pixmap = pix.scaled(
                size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            return self._cached_double_spiral_pixmap
        return QPixmap()

    def get_quest_pixmap(self, quest: Quest, size: int = 128) -> QPixmap:
        """Получение аватара квеста из модели (quest.logo), из RocksDB CAS или процедурная генерация."""
        if quest.id in self._quest_pixmaps:
            return self._quest_pixmaps[quest.id]

        avatar_bytes = None
        # 1. Извлекаем логотип из модели Quest через DAGStore
        if quest.logo:
            try:
                avatar_bytes = self.node.dag_store.get_quest_logo(quest)
            except Exception:
                avatar_bytes = None

        # 2. Проверяем сохраненный блоб по quest.id
        if not avatar_bytes:
            try:
                avatar_bytes = self.node.dag_store.get_blob(quest.id)
            except Exception:
                avatar_bytes = None

        # 3. Если логотип не найден — генерируем процедурные золотые нити
        if not avatar_bytes:
            avatar_bytes = generate_default_avatar_png(quest.title, f"{quest.id}:{quest.title}", size=size)

        pix = make_circular_pixmap(avatar_bytes, size=size)
        self._quest_pixmaps[quest.id] = pix
        return pix

    def set_active_quest(self, quest_id: str) -> None:
        """Установка активного выбранного квеста."""
        self.active_quest_id = quest_id
        if quest_id == "quest-volya-root":
            self.active_quest_title = "Воля"
            self._active_quest_pixmap = self.get_volya_logo_pixmap(size=128)
        else:
            q = self.node.dag_store.get_quest(quest_id)
            if q:
                self.active_quest_title = q.title
                self._active_quest_pixmap = self.get_quest_pixmap(q, size=128)
            else:
                self.active_quest_title = "Воля"
                self._active_quest_pixmap = self.get_volya_logo_pixmap(size=128)
        self.quest_selected.emit(quest_id)
        self.refresh_flows_and_players()
        self.update()

    def refresh_flows_and_players(self) -> None:
        """Обновление кэша потоков и игроков для текущего выбранного квеста."""
        try:
            self._quest_flows_cache = self.node.get_quest_flows(self.active_quest_id)
        except Exception:
            self._quest_flows_cache = []

        try:
            self._quest_players_cache = self.node.get_quest_players(self.active_quest_id)
        except Exception:
            self._quest_players_cache = []

    def _on_flow_title_text_changed(self, text: str) -> None:
        self.update()

    def _on_flow_menu_close_timeout(self) -> None:
        # Если курсор не в интерактивных зонах — закрываем меню потоков
        self._flow_menu_mode = "none"
        self._hovered_flow_kind_disc = None
        self._hovered_flow_item = None
        self._hovered_create_segment = None
        self._hovered_create_next_btn = False
        self._hovered_create_confirm_btn = False
        self._hovered_player_item = None
        self._create_step = "idle"
        self.flow_title_input.setVisible(False)
        self.update()

    # -------------------------------------------------------------
    # Управление Живым Потоком сотворчества (без окон на полотне)
    # -------------------------------------------------------------

    def open_flow(self, flow_id: str) -> None:
        """Открытие живого потока капель на полотне мира без окон."""
        self._active_flow_id = flow_id
        try:
            self._active_flow = self.node.dag_store.get_quest_flow(flow_id)
        except Exception:
            self._active_flow = None
        self._flow_menu_mode = "none"
        self.flow_title_input.setVisible(False)
        self._load_active_flow_drops()
        self._flow_input_active = False
        self.flow_drop_input.setVisible(False)
        self.flow_drop_input.setText("")
        self._flow_scroll_y = 0.0
        self.update()

    def close_active_flow(self) -> None:
        """Закрытие открытого потока капель по клику на двойную спираль."""
        self._active_flow_id = None
        self._active_flow = None
        self._active_flow_drops.clear()
        self._flow_input_active = False
        self.flow_drop_input.setVisible(False)
        self.update()

    def _load_active_flow_drops(self) -> None:
        """Загрузка капель открытого потока."""
        if not self._active_flow_id:
            self._active_flow_drops = []
            return
        try:
            self._active_flow_drops = self.node.get_accessible_drops(self._active_flow_id)
        except Exception:
            self._active_flow_drops = []

    def _toggle_flow_input(self) -> None:
        """Включение/выключение поля ввода новой капли у кнопки-капли."""
        self._flow_input_active = not self._flow_input_active
        if self._flow_input_active:
            self._position_flow_input()
            self.flow_drop_input.setVisible(True)
            self.flow_drop_input.setFocus()
        else:
            self.flow_drop_input.setVisible(False)
        self.update()

    def _position_flow_input(self) -> None:
        """Позиционирование поля ввода капли справа от кнопки-капли (внутрь потока)."""
        c_btn = self._get_flow_drop_btn_center()
        self.flow_drop_input.setGeometry(int(c_btn.x() + 20.0), int(c_btn.y() - 13.0), 215, 26)
        self.flow_drop_submit_btn.move(
            self.flow_drop_input.width() - 23, (self.flow_drop_input.height() - 20) // 2
        )

    def _submit_new_flow_drop(self) -> None:
        """Отправка новой капли мысли в поток."""
        text = self.flow_drop_input.text().strip()
        if not text or not self._active_flow_id:
            return

        quest_id = self.active_quest_id
        flow_id = self._active_flow_id

        try:
            self.node.post_flow_drop(quest_id=quest_id, flow_id=flow_id, content=text)
        except Exception as e:
            print(f"Error posting flow drop: {e}")

        self.flow_drop_input.clear()
        self._flow_input_active = False
        self.flow_drop_input.setVisible(False)
        self._load_active_flow_drops()
        self.update()

    def _is_near_flow_spiral(self, pt: QPointF) -> bool:
        """Проверка наведения на двойную спираль активного потока."""
        if not self._active_flow_id:
            return False
        return math.hypot(pt.x() - self._flow_spiral_center.x(), pt.y() - self._flow_spiral_center.y()) <= 24.0

    def _is_near_flow_drop_btn(self, pt: QPointF) -> bool:
        """Проверка наведения на круглую кнопку-каплю на левой ветви."""
        if not self._active_flow_id:
            return False
        c_btn = self._get_flow_drop_btn_center()
        return math.hypot(pt.x() - c_btn.x(), pt.y() - c_btn.y()) <= 18.0

    def _flow_left_trunk_point(self, y: float) -> QPointF:
        """Плавная органическая форма левой ветви потока (без прямых линий и без изломов!)."""
        c_spiral = self._flow_spiral_center
        p_fork = QPointF(c_spiral.x(), 102.0)
        x_base = 270.0
        y_trans = 240.0

        if y <= 102.0:
            return p_fork
        elif y < y_trans:
            t = (y - 102.0) / (y_trans - 102.0)
            for _ in range(5):
                u = 1.0 - t
                yt = u**3 * 102.0 + 3.0*u**2*t * 147.0 + 3.0*u*t**2 * 175.0 + t**3 * 240.0
                dy = 135.0*u**2 + 168.0*u*t + 195.0*t**2
                if abs(dy) < 1e-6:
                    break
                t = max(0.0, min(1.0, t - (yt - y) / dy))
            u = 1.0 - t
            x = u**3 * 520.0 + 3.0*u**2*t * 410.0 + 3.0*u*t**2 * 270.0 + t**3 * 270.0
            return QPointF(x, y)
        else:
            dy = y - y_trans
            offset_x = 5.0 * (1.0 - math.cos(dy * 0.035)) * math.sin(dy * 0.018)
            return QPointF(x_base + offset_x, y)

    def _flow_right_trunk_point(self, y: float) -> QPointF:
        """Плавная органическая форма правой ветви потока (без прямых линий и без изломов!)."""
        c_spiral = self._flow_spiral_center
        p_fork = QPointF(c_spiral.x(), 102.0)
        x_base = 770.0
        y_trans = 240.0

        if y <= 102.0:
            return p_fork
        elif y < y_trans:
            t = (y - 102.0) / (y_trans - 102.0)
            for _ in range(5):
                u = 1.0 - t
                yt = u**3 * 102.0 + 3.0*u**2*t * 147.0 + 3.0*u*t**2 * 175.0 + t**3 * 240.0
                dy = 135.0*u**2 + 168.0*u*t + 195.0*t**2
                if abs(dy) < 1e-6:
                    break
                t = max(0.0, min(1.0, t - (yt - y) / dy))
            u = 1.0 - t
            x = u**3 * 520.0 + 3.0*u**2*t * 630.0 + 3.0*u*t**2 * 770.0 + t**3 * 770.0
            return QPointF(x, y)
        else:
            dy = y - y_trans
            offset_x = -5.0 * (1.0 - math.cos(dy * 0.035)) * math.sin(dy * 0.018)
            return QPointF(x_base + offset_x, y)

    def _get_flow_drop_btn_center(self) -> QPointF:
        """Расчет позиции кнопки-капли на конце левой ветви (внизу всего потока)."""
        y_cursor = 260.0 + self._flow_scroll_y
        y_left_last = 250.0 + self._flow_scroll_y

        for drop in self._active_flow_drops:
            my_pk = self.node.identity.pubkey if hasattr(self.node, 'identity') and self.node.identity else ''
            if my_pk and drop.author_pubkey:
                is_mine = (drop.author_pubkey == my_pk)
            elif drop.author_name:
                is_mine = (drop.author_name == self.node.username)
            else:
                is_mine = True
            text_lines = max(1, len(drop.content) // 26 + 1)
            h_drop = max(38.0, text_lines * 18.0 + 16.0)

            if is_mine:
                y_pos = max(y_cursor, y_left_last + 26.0)
                y_left_last = y_pos + h_drop
                y_cursor = max(y_cursor, y_pos) + h_drop + 14.0
            else:
                y_pos = max(y_cursor, y_left_last + 26.0)
                y_cursor = max(y_cursor, y_pos) + h_drop + 14.0

        y_btn = max(275.0, y_cursor + 24.0)
        return self._flow_left_trunk_point(y_btn)

    # -------------------------------------------------------------
    # Построение Древа Квестов по правилам Воли
    # -------------------------------------------------------------

    def refresh_quests(self) -> None:
        """
        Перестроение иерархии Древа по квестам, где участвует текущий игрок:
        - Корневые квесты (ROOT_CHILD) -> влево от нити.
        - Вольницы (TRUNK) -> вправо от нити.
        - Дома -> от Вольниц влево-вверх.
        - Другие дочерние квесты -> от Вольниц вправо-вниз.
        """
        pk = self.node.identity.pubkey
        player = self.node.dag_store.get_player(pk)
        all_quests = self.node.dag_store.get_all_quests()

        # Определяем квесты игрока
        user_roles_by_quest: Dict[str, str] = {}
        if player and player.roles:
            for r in player.roles:
                user_roles_by_quest[r.quest_id] = r.role_title

        # Вольные игроки всегда участники «Воли»
        if "quest-volya-root" not in user_roles_by_quest:
            user_roles_by_quest["quest-volya-root"] = "Вольный игрок"

        # Фильтруем квесты, в которых участвует игрок или является создателем
        participating_quests: List[Quest] = []
        for q in all_quests:
            if q.id in user_roles_by_quest or q.owner_pubkey == pk:
                participating_quests.append(q)

        # Раскладываем по ветвям
        root_children = [
            q for q in participating_quests
            if q.parent_quest_id == "quest-volya-root" and q.tier == TreeTier.ROOT_CHILD
        ]
        trunks = [
            q for q in participating_quests
            if q.tier == TreeTier.TRUNK or (q.parent_quest_id == "quest-volya-root" and "вольница" in q.title.lower())
        ]

        nodes: List[QuestTreeNode] = []
        stem_x = self.spiral_center.x()

        # 1. Корневые квесты (влево от нити)
        cur_y = 175.0
        for q in root_children:
            bx = stem_x - 90.0
            by = cur_y
            role = user_roles_by_quest.get(q.id, "Сотворец")
            pix = self.get_quest_pixmap(q, size=128)
            parent_p = QPointF(stem_x, by)
            nodes.append(QuestTreeNode(q, role, QPointF(bx, by), "root_child", parent_p, pix))
            cur_y += 95.0

        # 2. Вольницы (вправо от нити)
        cur_trunk_y = 205.0
        for tr in trunks:
            tx = stem_x + 105.0
            ty = cur_trunk_y
            role = user_roles_by_quest.get(tr.id, "Вольный житель")
            pix = self.get_quest_pixmap(tr, size=128)
            parent_p = QPointF(stem_x, ty)
            nodes.append(QuestTreeNode(tr, role, QPointF(tx, ty), "trunk", parent_p, pix))

            # Дочерние квесты от этой Вольницы
            trunk_children = [
                q for q in participating_quests if q.parent_quest_id == tr.id
            ]
            house_idx = 0
            other_idx = 0
            for ch in trunk_children:
                is_house = "дом" in ch.title.lower()
                ch_role = user_roles_by_quest.get(ch.id, "Сотворец")
                ch_pix = self.get_quest_pixmap(ch, size=128)
                ch_parent_p = QPointF(tx, ty)

                if is_house:
                    # Влево вверх от Вольницы
                    hx = tx - 72.0 - house_idx * 48.0
                    hy = ty - 65.0 - house_idx * 42.0
                    nodes.append(QuestTreeNode(ch, ch_role, QPointF(hx, hy), "house", ch_parent_p, ch_pix))
                    house_idx += 1
                else:
                    # Вправо вниз от Вольницы
                    ox = tx + 82.0 + other_idx * 48.0
                    oy = ty + 70.0 + other_idx * 44.0
                    nodes.append(QuestTreeNode(ch, ch_role, QPointF(ox, oy), "other", ch_parent_p, ch_pix))
                    other_idx += 1

            cur_trunk_y += 140.0

        self.tree_nodes = nodes
        self.update()

    # -------------------------------------------------------------
    # Управление разворачиванием и сворачиванием
    # -------------------------------------------------------------

    def on_avatar_hovered(self, hovered: bool) -> None:
        """Реакция на наведение мыши на аватарку игрока в углу."""
        self._avatar_hovered = hovered
        if hovered:
            self._arc_visible = True
            self._auto_close_timer.stop()
            self.update()
        else:
            if self.has_selected_quest:
                self._arc_visible = True
            elif not self._tree_open and not self._arc_hovered:
                self._schedule_close(400)

    def open_tree(self) -> None:
        """Запуск плавного разворачивания дерева нитью."""
        if not self._tree_open:
            self.refresh_quests()
        self._tree_open = True
        self._arc_visible = True
        self._unfold_target = 1.0
        self._auto_close_timer.stop()

    def fold_tree(self, immediate: bool = False) -> None:
        """Сворачивание дерева обратно в спираль."""
        self._unfold_target = 0.0
        self._hovered_bead = None
        self._arc_hovered = False
        if immediate:
            self._unfold_progress = 0.0
            self._tree_open = False
            if not self.has_selected_quest:
                self._arc_visible = False
        self.update()

    def _schedule_close(self, ms: int = 400) -> None:
        if not self._auto_close_timer.isActive():
            self._auto_close_timer.start(ms)

    def _on_auto_close_timeout(self) -> None:
        if not self._avatar_hovered and not self._arc_hovered and not self._hovered_bead:
            self.fold_tree()
            if not self.has_selected_quest:
                self._arc_visible = False
            self.update()

    def _on_anim_tick(self) -> None:
        """Шаг плавной интерполяции разворачивания и перемещения бусинки."""
        needs_update = False

        # 1. Интерполяция разворачивания дерева
        if abs(self._unfold_progress - self._unfold_target) > 0.005:
            delta = (self._unfold_target - self._unfold_progress) * 0.16
            self._unfold_progress += delta
            needs_update = True
        else:
            if self._unfold_progress != self._unfold_target:
                self._unfold_progress = self._unfold_target
                if self._unfold_progress == 0.0:
                    self._tree_open = False
                    if not self.has_selected_quest:
                        self._arc_visible = False
                    # После полного исчезновения дерева запускаем полёт бусинки, если был выбор!
                    if self._pending_selection_node:
                        self._gliding_node = self._pending_selection_node
                        self._pending_selection_node = None
                        self._glide_progress = 0.0
                        self._glide_start_pos = QPointF(self._gliding_node.target_pos)
                needs_update = True

        # 2. Анимация скольжения бусинки к спирали (после полного исчезновения дерева)
        if self._gliding_node and self._glide_progress < 1.0:
            self._glide_progress = min(1.0, self._glide_progress + 0.065)
            # Плавная кривая замедления
            t = QEasingCurve(QEasingCurve.InOutCubic).valueForProgress(self._glide_progress)

            start = self._glide_start_pos
            target = self.spiral_center

            cur_x = start.x() + (target.x() - start.x()) * t
            cur_y = start.y() + (target.y() - start.y()) * t
            self._gliding_node.current_pos = QPointF(cur_x, cur_y)
            # Масштабирование бусинки с 48px до 64px
            self._gliding_node.current_size = 48.0 + (64.0 - 48.0) * t

            if self._glide_progress >= 1.0:
                # Скольжение завершено: квест выбран!
                selected_qid = self._gliding_node.quest.id
                self._gliding_node = None
                self.has_selected_quest = True
                self.set_active_quest(selected_qid)

            needs_update = True

        if needs_update:
            self.update()

    # -------------------------------------------------------------
    # Обработка мыши (Hit-Testing, наведение, выбор)
    # -------------------------------------------------------------

    def _is_near_arc(self, pt: QPointF) -> bool:
        """Проверка, наведён ли курсор на правую дугу аватарки."""
        dx = pt.x() - self.avatar_center.x()
        dy = pt.y() - self.avatar_center.y()
        dist = math.hypot(dx, dy)
        # Находится справа от центра (dx > 20) и в радиусе дуги +-14px
        if dx > 20.0 and abs(dist - self.arc_radius) <= 16.0:
            angle_deg = math.degrees(math.atan2(dy, dx))
            return -55.0 <= angle_deg <= 55.0
        return False

    def _is_near_spiral(self, pt: QPointF) -> bool:
        """Проверка, наведён ли курсор на двойную спираль или выбранный квест."""
        # Если квест ещё не выбран и дерево закрыто — спираль не видна и не интерактивна
        if not self.has_selected_quest and not self._tree_open and self._unfold_progress <= 0.20:
            return False
        dx = pt.x() - self.spiral_center.x()
        dy = pt.y() - self.spiral_center.y()
        return math.hypot(dx, dy) <= (self.spiral_radius + 4.0)

    def _find_hovered_bead(self, pt: QPointF) -> Optional[QuestTreeNode]:
        """Поиск бусинки под курсором."""
        if self._unfold_progress < 0.6:
            return None
        for node in self.tree_nodes:
            dx = pt.x() - node.current_pos.x()
            dy = pt.y() - node.current_pos.y()
            if math.hypot(dx, dy) <= (node.current_size / 2.0 + 3.0):
                return node
        return None

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pt = event.position()
        old_arc_hovered = self._arc_hovered
        old_spiral_hovered = self._spiral_hovered
        old_bead = self._hovered_bead

        # 1. Проверка наведения на дугу
        if self._is_near_arc(pt):
            self._arc_hovered = True
            self._arc_visible = True
            self.open_tree()
        else:
            self._arc_hovered = False

        # 2. Проверка наведения на спираль
        self._spiral_hovered = self._is_near_spiral(pt)

        # 3. Проверка наведения на бусинки
        self._hovered_bead = self._find_hovered_bead(pt)
        for n in self.tree_nodes:
            n.hovered = (n == self._hovered_bead)

        # 4. Проверка дуг и органов управления Потоками выбранного квеста
        if self.has_selected_quest and not self._tree_open and not self._gliding_node:
            if self._handle_flow_mouse_move(pt):
                self.update()
                event.accept()
                return

        # Управление курсором
        can_click_spiral = self._tree_open and self._spiral_hovered
        if self._arc_hovered or can_click_spiral or self._hovered_bead:
            self.setCursor(Qt.PointingHandCursor)
            self._auto_close_timer.stop()
        else:
            self.setCursor(Qt.ArrowCursor)
            # Если курсор далеко от дерева, запускаем таймер закрытия
            if self._tree_open:
                # Проверяем габариты активного дерева
                in_tree_zone = (
                    pt.x() >= 40.0 and pt.x() <= 590.0 and
                    pt.y() >= 20.0 and pt.y() <= 650.0
                )
                if not in_tree_zone and not self._avatar_hovered:
                    self._schedule_close(500)

        if (
            old_arc_hovered != self._arc_hovered or
            old_spiral_hovered != self._spiral_hovered or
            old_bead != self._hovered_bead
        ):
            self.update()

        # Интерактив открытого живого потока капель
        if self._active_flow_id:
            old_spiral_hov = self._flow_spiral_hovered
            old_drop_hov = self._flow_drop_btn_hovered
            self._flow_spiral_hovered = self._is_near_flow_spiral(pt)
            self._flow_drop_btn_hovered = self._is_near_flow_drop_btn(pt)

            if self._flow_spiral_hovered or self._flow_drop_btn_hovered:
                self.setCursor(Qt.PointingHandCursor)
                self._auto_close_timer.stop()
            if old_spiral_hov != self._flow_spiral_hovered or old_drop_hov != self._flow_drop_btn_hovered:
                self.update()

        # Если событие не в интерактивной зоне — пропускаем родителю
        in_flow_zone = (self.has_selected_quest and (self._flow_menu_mode != "none" or self._active_flow_id is not None))
        if not (self._arc_hovered or self._spiral_hovered or self._hovered_bead or self._tree_open or in_flow_zone):
            event.ignore()
        else:
            super().mouseMoveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.LeftButton:
            event.ignore()
            return

        pt = event.position()

        # 0. Клик по элементам открытого живого потока капель
        if self._active_flow_id:
            if self._is_near_flow_spiral(pt):
                self.close_active_flow()
                event.accept()
                return
            if self._is_near_flow_drop_btn(pt):
                self._toggle_flow_input()
                event.accept()
                return

        # 1. Клик по бусинке квеста в развёрнутом дереве:
        # Сначала исчезает дерево, а затем бусинка перелетает к спирали!
        hit_bead = self._find_hovered_bead(pt)
        if hit_bead and not self._gliding_node and not self._pending_selection_node:
            self._pending_selection_node = hit_bead
            self._unfold_target = 0.0
            self._hovered_bead = None
            self._arc_hovered = False
            self.update()
            return

        # 2. Клик по спирали при открытом дереве -> выбор квеста «Воля»
        if self._tree_open and self._is_near_spiral(pt):
            self.has_selected_quest = True
            self.set_active_quest("quest-volya-root")
            self.fold_tree()
            self.update()
            return

        # 3. Клик вне дерева при открытом дереве -> свернуть
        if self._tree_open:
            self.fold_tree()
            self.update()
            return

        # 4. Клик по органам выбора или создания потока у выбранного квеста
        if self.has_selected_quest and not self._tree_open and not self._gliding_node:
            if self._handle_flow_mouse_press(pt):
                self.update()
                event.accept()
                return

        # По щелчку мыши ничего пока не должно происходить у выбранного квеста при закрытом дереве
        event.ignore()

    def wheelEvent(self, event) -> None:
        if self._active_flow_id:
            delta = event.angleDelta().y() * 0.45
            self._flow_scroll_y = min(0.0, self._flow_scroll_y + delta)
            if self._flow_input_active:
                self._position_flow_input()
            self.update()
            event.accept()
        else:
            super().wheelEvent(event)

    # -------------------------------------------------------------
    # Отрисовка: Дуга, Нить, Двойная Спираль, Стебель, Ветви, Бусины
    # -------------------------------------------------------------

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        night = self.is_night()
        glow_color = QColor(241, 245, 249) if night else QColor(250, 204, 21)
        core_color = QColor(255, 255, 255) if night else QColor(254, 240, 138)
        stem_color = QColor(226, 232, 240, 190) if night else QColor(212, 175, 55, 190)

        # 1. Правая дуга аватарки игрока:
        # Если квест выбран — видна постоянно (вместе с соединительной нитью).
        # До выбора квеста — появляется только при наведении на аватарку или дугу, и горит ярко!
        if (
            self.has_selected_quest
            or self._arc_visible
            or self._avatar_hovered
            or self._arc_hovered
            or self._tree_open
        ):
            self._draw_avatar_arc(painter, glow_color, core_color)

        # 2. Соединительная нить: Дуга -> Спираль
        # Если квест выбран — видна постоянно. До выбора — при разворачивании или перелёте
        if (
            self.has_selected_quest
            or self._unfold_progress > 0.0
            or self._tree_open
            or self._arc_hovered
            or self._gliding_node is not None
            or self._pending_selection_node is not None
        ):
            self._draw_bridge_thread(painter, glow_color, core_color)

        # 3. Стебель Древа и Ветви
        if self._unfold_progress > 0.5:
            self._draw_tree_stem_and_branches(painter, stem_color, glow_color)

        # 4. Двойная Спираль (или аватарка выбранного квеста) на месте спирали
        self._draw_spiral_or_selected_quest(painter, glow_color, core_color)

        # 5. Бусинки квестов
        if self._unfold_progress > 0.7:
            self._draw_quest_beads(painter, glow_color, core_color)

        # 6. Ожидающая бусинка (пока дерево исчезает)
        if self._pending_selection_node:
            self._draw_single_bead(painter, self._pending_selection_node, glow_color, core_color)

        # 7. Скользящая бусинка (когда дерево уже исчезло и идёт перелёт)
        if self._gliding_node:
            self._draw_single_bead(painter, self._gliding_node, glow_color, core_color)

        # 8. Всплывающее лёгкое полупрозрачное облако с названием квеста при наведении
        self._draw_hover_tooltip(painter)

        # 9. Сакральные дуги выбора и создания Потока у выбранного квеста (видны только когда поток не открыт)
        if self.has_selected_quest and not self._tree_open and not self._gliding_node and not self._active_flow_id:
            self._draw_flow_selection_and_creation(painter, glow_color, core_color)

        # 10. Живой Поток капель прямо на полотне мира (без окон)
        if self._active_flow_id and self._active_flow and not self._tree_open and not self._gliding_node:
            self._draw_living_flow_stream(painter, glow_color, core_color, night)

        painter.end()

    def _draw_avatar_arc(self, painter: QPainter, glow_color: QColor, core_color: QColor) -> None:
        """Отрисовка дуги справа от аватарки игрока."""
        arc_box = QRectF(
            self.avatar_center.x() - self.arc_radius,
            self.avatar_center.y() - self.arc_radius,
            2 * self.arc_radius,
            2 * self.arc_radius,
        )
        start_angle = int(-45 * 16)
        span_angle = int(90 * 16)

        # Активное состояние выбора: до первого выбора, при открытом дереве, наведении или перелёте
        is_active_selection = (
            not self.has_selected_quest
            or self._tree_open
            or self._unfold_progress > 0.001
            or self._arc_hovered
            or self._avatar_hovered
            or self._gliding_node is not None
            or self._pending_selection_node is not None
        )

        if is_active_selection:
            # АКТИВНОЕ ВЫБИРАНИЕ / ПРИЗЫВ: дуга горит ярко и заново сияет в полную силу
            hovered = self._arc_hovered or self._avatar_hovered
            alpha = 255 if hovered else 225
            glow_alpha = 180 if hovered else 140

            # 1. Широкий внешний ореол яркого свечения (8.6px)
            glow_pen_wide = QPen(
                QColor(glow_color.red(), glow_color.green(), glow_color.blue(), int(glow_alpha * 0.45)),
                8.6,
                Qt.SolidLine,
                Qt.RoundCap,
            )
            painter.setPen(glow_pen_wide)
            painter.drawArc(arc_box, start_angle, span_angle)

            # 2. Плотный ореол свечения (5.6px)
            glow_pen_inner = QPen(
                QColor(glow_color.red(), glow_color.green(), glow_color.blue(), int(glow_alpha * 0.85)),
                5.6,
                Qt.SolidLine,
                Qt.RoundCap,
            )
            painter.setPen(glow_pen_inner)
            painter.drawArc(arc_box, start_angle, span_angle)

            # 3. Сияющее белое/золотое ядро дуги (3.4px)
            core_pen = QPen(
                QColor(core_color.red(), core_color.green(), core_color.blue(), alpha),
                3.4,
                Qt.SolidLine,
                Qt.RoundCap,
            )
            painter.setPen(core_pen)
            painter.drawArc(arc_box, start_angle, span_angle)

        else:
            # ЗАТУХАНИЕ ПОСЛЕ ВЫБОРА (в покое при закрытом дереве):
            # Не мрачное, а чистое, более прозрачное и слегка менее яркое (воздушное)
            alpha = 145
            glow_alpha = 50

            base_color = QColor(core_color.red(), core_color.green(), core_color.blue(), alpha)
            halo_color = QColor(glow_color.red(), glow_color.green(), glow_color.blue(), glow_alpha)

            # 1. Мягкий полупрозрачный ореол (5.4px)
            glow_pen = QPen(halo_color, 5.4, Qt.SolidLine, Qt.RoundCap)
            painter.setPen(glow_pen)
            painter.drawArc(arc_box, start_angle, span_angle)

            # 2. Деликатное прозрачное ядро (3.2px)
            core_pen = QPen(base_color, 3.2, Qt.SolidLine, Qt.RoundCap)
            painter.setPen(core_pen)
            painter.drawArc(arc_box, start_angle, span_angle)

    def _make_ribbon_path(
        self, pts: List[QPointF], w_start: float, w_end: float, expand: float = 0.0
    ) -> QPainterPath:
        """Построение непрерывной объемной ленты ветви без стыков и сегментов."""
        n = len(pts) - 1
        if n < 1:
            return QPainterPath()

        normals: List[QPointF] = []
        for i in range(len(pts)):
            if i == 0:
                tang = QPointF(pts[1].x() - pts[0].x(), pts[1].y() - pts[0].y())
            elif i == len(pts) - 1:
                tang = QPointF(pts[-1].x() - pts[-2].x(), pts[-1].y() - pts[-2].y())
            else:
                tang = QPointF(pts[i + 1].x() - pts[i - 1].x(), pts[i + 1].y() - pts[i - 1].y())
            l = math.hypot(tang.x(), tang.y()) or 1.0
            normals.append(QPointF(-tang.y() / l, tang.x() / l))

        left_pts: List[QPointF] = []
        right_pts: List[QPointF] = []
        for i in range(len(pts)):
            u = i / n
            w = ((w_start * (1.0 - u) + w_end * u) / 2.0) + expand
            left_pts.append(QPointF(pts[i].x() + normals[i].x() * w, pts[i].y() + normals[i].y() * w))
            right_pts.append(QPointF(pts[i].x() - normals[i].x() * w, pts[i].y() - normals[i].y() * w))

        path = QPainterPath()
        path.moveTo(left_pts[0])
        for pt in left_pts[1:]:
            path.lineTo(pt)

        # Плавное скругление на растущем конце
        tip_norm = normals[-1]
        tip_tang = QPointF(pts[-1].x() - pts[-2].x(), pts[-1].y() - pts[-2].y())
        lt = math.hypot(tip_tang.x(), tip_tang.y()) or 1.0
        tip_dir = QPointF(tip_tang.x() / lt, tip_tang.y() / lt)
        w_tip = (w_end / 2.0) + expand
        p_tip_apex = QPointF(pts[-1].x() + tip_dir.x() * w_tip, pts[-1].y() + tip_dir.y() * w_tip)

        path.cubicTo(
            QPointF(left_pts[-1].x() + tip_dir.x() * (w_tip * 0.55), left_pts[-1].y() + tip_dir.y() * (w_tip * 0.55)),
            QPointF(p_tip_apex.x() + tip_norm.x() * (w_tip * 0.55), p_tip_apex.y() + tip_norm.y() * (w_tip * 0.55)),
            p_tip_apex,
        )
        path.cubicTo(
            QPointF(p_tip_apex.x() - tip_norm.x() * (w_tip * 0.55), p_tip_apex.y() - tip_norm.y() * (w_tip * 0.55)),
            QPointF(right_pts[-1].x() + tip_dir.x() * (w_tip * 0.55), right_pts[-1].y() + tip_dir.y() * (w_tip * 0.55)),
            right_pts[-1],
        )

        for pt in reversed(right_pts[:-1]):
            path.lineTo(pt)

        # Плавное скругление у основания
        base_norm = normals[0]
        base_tang = QPointF(pts[0].x() - pts[1].x(), pts[0].y() - pts[1].y())
        lb = math.hypot(base_tang.x(), base_tang.y()) or 1.0
        base_dir = QPointF(base_tang.x() / lb, base_tang.y() / lb)
        w_base = (w_start / 2.0) + expand
        p_base_apex = QPointF(pts[0].x() + base_dir.x() * w_base, pts[0].y() + base_dir.y() * w_base)

        path.cubicTo(
            QPointF(right_pts[0].x() + base_dir.x() * (w_base * 0.55), right_pts[0].y() + base_dir.y() * (w_base * 0.55)),
            QPointF(p_base_apex.x() - base_norm.x() * (w_base * 0.55), p_base_apex.y() - base_norm.y() * (w_base * 0.55)),
            p_base_apex,
        )
        path.cubicTo(
            QPointF(p_base_apex.x() + base_norm.x() * (w_base * 0.55), p_base_apex.y() + base_norm.y() * (w_base * 0.55)),
            QPointF(left_pts[0].x() + base_dir.x() * (w_base * 0.55), left_pts[0].y() + base_dir.y() * (w_base * 0.55)),
            left_pts[0],
        )

        path.closeSubpath()
        return path

    def _draw_volumetric_branch(
        self,
        painter: QPainter,
        pts: List[QPointF],
        w_start: float,
        w_end: float,
        night: bool,
    ) -> None:
        """Отрисовка цельной утончающейся ветви с градиентным объемом и контуром (без сегментов)."""
        if len(pts) < 2:
            return

        # 1. Мягкий внешний ореол свечения
        glow_color = QColor(241, 245, 249, 35) if night else QColor(250, 204, 21, 40)
        glow_path = self._make_ribbon_path(pts, w_start, w_end, expand=3.0)
        painter.setPen(Qt.NoPen)
        painter.setBrush(glow_color)
        painter.drawPath(glow_path)

        # 2. Объемное тело ветви с плавным градиентом вдоль древесины
        body_path = self._make_ribbon_path(pts, w_start, w_end, expand=0.0)
        grad = QLinearGradient(pts[0], pts[-1])
        if night:
            grad.setColorAt(0.0, QColor(255, 255, 255, 240))
            grad.setColorAt(0.4, QColor(226, 232, 240, 220))
            grad.setColorAt(1.0, QColor(148, 163, 184, 190))
            rim_color = QColor(255, 255, 255, 130)
            spine_color = QColor(255, 255, 255, 200)
        else:
            grad.setColorAt(0.0, QColor(254, 240, 138, 250))
            grad.setColorAt(0.4, QColor(250, 204, 21, 230))
            grad.setColorAt(1.0, QColor(217, 119, 6, 190))
            rim_color = QColor(254, 240, 138, 160)
            spine_color = QColor(255, 255, 255, 210)

        # 3. Градиентный контур, подчеркивающий объем
        painter.setBrush(QBrush(grad))
        painter.setPen(QPen(rim_color, 0.85))
        painter.drawPath(body_path)

        # 4. Светящаяся центральная жила-сердцевина (непрерывный штрих без стыков)
        spine = QPainterPath()
        spine.moveTo(pts[0])
        for pt in pts[1:]:
            spine.lineTo(pt)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(spine_color, 1.1, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawPath(spine)

    def _draw_translucent_bridge(
        self,
        painter: QPainter,
        pts: List[QPointF],
        w_start: float,
        w_end: float,
        glow_color: QColor,
        core_color: QColor,
    ) -> None:
        """
        Отрисовка чистого, полупрозрачного и спокойного моста связи в покое.
        Не мрачный, а чистый, воздушный, в тон живого света Древа.
        """
        if len(pts) < 2:
            return

        alpha = 145
        glow_alpha = 45

        base_color = QColor(core_color.red(), core_color.green(), core_color.blue(), alpha)
        halo_color = QColor(glow_color.red(), glow_color.green(), glow_color.blue(), glow_alpha)
        rim_color = QColor(core_color.red(), core_color.green(), core_color.blue(), int(alpha * 0.85))

        # 1. Мягкий полупрозрачный ореол того же живого цвета (expand=2.0)
        glow_path = self._make_ribbon_path(pts, w_start, w_end, expand=2.0)
        painter.setPen(Qt.NoPen)
        painter.setBrush(halo_color)
        painter.drawPath(glow_path)

        # 2. Чистое полупрозрачное тело ветви (однотонное, без мрачности)
        body_path = self._make_ribbon_path(pts, w_start, w_end, expand=0.0)
        painter.setBrush(QBrush(base_color))
        painter.setPen(QPen(rim_color, 0.6))
        painter.drawPath(body_path)

    def _draw_leaf(
        self,
        painter: QPainter,
        pos: QPointF,
        angle_rad: float,
        length: float = 13.0,
        width: float = 5.2,
        night: bool = True,
        alpha_scale: float = 1.0,
    ) -> None:
        """Вспомогательная отрисовка листочка (сохранена для совместимости)."""
        pass

    def _trunk_point(self, y: float, stem_top_y: float) -> QPointF:
        """Плавная органическая форма ствола Древа с мягким живым изгибом."""
        stem_x = self.spiral_center.x()
        dy = max(0.0, y - stem_top_y)
        offset_x = 4.2 * math.sin(dy * 0.022) + 2.2 * math.sin(dy * 0.055)
        return QPointF(stem_x + offset_x, y)

    def _draw_bridge_thread(
        self, painter: QPainter, glow_color: QColor, core_color: QColor
    ) -> None:
        """
        Протягивание живой утончающейся веточки от правой дуги аватарки к левому краю Истока («Воля»).
        """
        p_start = QPointF(self.avatar_center.x() + self.arc_radius, self.avatar_center.y())
        p_target = QPointF(self.spiral_center.x() - self.spiral_radius, self.spiral_center.y())

        # Если квест уже выбран, или идёт анимация перелёта — веточка распущена полностью
        if self.has_selected_quest or self._gliding_node or self._pending_selection_node:
            t = 1.0
        else:
            t = min(1.0, self._unfold_progress / 0.22) if self._unfold_progress > 0 else 0.0
            if self._arc_hovered and t < 0.2:
                t = 0.2

        if t <= 0.001:
            return

        dx = p_target.x() - p_start.x()
        c1 = QPointF(p_start.x() + dx * 0.35, p_start.y() + 11.0)
        c2 = QPointF(p_start.x() + dx * 0.70, p_target.y() - 7.0)

        def bz_pt(u: float) -> QPointF:
            mu = 1.0 - u
            return QPointF(
                mu**3 * p_start.x() + 3.0 * mu**2 * u * c1.x() + 3.0 * mu * u**2 * c2.x() + u**3 * p_target.x(),
                mu**3 * p_start.y() + 3.0 * mu**2 * u * c1.y() + 3.0 * mu * u**2 * c2.y() + u**3 * p_target.y(),
            )

        steps = 28
        max_step = max(1, int(steps * t))
        pts = [bz_pt((i / steps) * t) for i in range(max_step + 1)]

        # Утончение от дуги аватарки (3.6px) к Истоку (2.0px)
        w_s = 3.6
        w_e = 3.6 * (1.0 - t) + 2.0 * t
        night = self.is_night()

        is_active_selection = (
            not self.has_selected_quest
            or self._tree_open
            or self._unfold_progress > 0.001
            or self._arc_hovered
            or self._avatar_hovered
            or self._gliding_node is not None
            or self._pending_selection_node is not None
        )

        if is_active_selection:
            # АКТИВНОЕ ВЫБИРАНИЕ: ветка заново ярко светится вместе со всем Древом
            self._draw_volumetric_branch(painter, pts, w_s, w_e, night)
            if t < 1.0 and t > 0.01:
                painter.setPen(Qt.NoPen)
                painter.setBrush(core_color)
                painter.drawEllipse(pts[-1], 2.8, 2.8)
        else:
            # ЗАТУХАНИЕ ПОСЛЕ ВЫБОРА (в покое при закрытом дереве):
            # Чистая, более прозрачная, слегка менее яркая однотонная ветвь
            self._draw_translucent_bridge(painter, pts, w_s, w_e, glow_color, core_color)

    def _draw_spiral_or_selected_quest(
        self, painter: QPainter, glow_color: QColor, core_color: QColor
    ) -> None:
        """
        Отрисовка канонического логотипа Вольного Древа (Исток «Воля») или аватарки выбранного квеста.
        На месте истока (264, 72) диаметром 64px элемент присутствует постоянно после выбора.
        До первого выбора не виден в спокойном состоянии.
        """
        cx = self.spiral_center.x()
        cy = self.spiral_center.y()

        # 1. Если дерево закрыто и квест ещё не выбран — элемент не рисуется
        if not self.has_selected_quest and not self._tree_open and self._unfold_progress <= 0.0 and not self._gliding_node:
            return

        # 2. Если дерево закрыто и не скользит узел:
        # рисуется выбранный квест (будь то Воля с логотипом Вольного Древа или любой другой квест)
        if (
            self.has_selected_quest
            and not self._tree_open
            and not self._gliding_node
        ):
            pixmap = self._active_quest_pixmap or self.get_volya_logo_pixmap(size=128)
            self._draw_bead_disc(
                painter,
                self.spiral_center,
                64.0,
                pixmap,
                glow_color,
                core_color,
                hovered=self._spiral_hovered,
            )
            return

        # 3. При открытом дереве (или в процессе его разворачивания):
        # На вершине стебля (Исток Древа) отображается канонический логотип квеста «Воля»
        appear_t = 1.0
        if self._tree_open or self._unfold_progress < 1.0:
            if self._unfold_progress <= 0.20:
                appear_t = 0.0
            else:
                appear_t = min(1.0, (self._unfold_progress - 0.20) / 0.35)

        # Если квест «Воля» уже выбран — логотип остаётся виден на 100% при сворачивании дерева
        if self.has_selected_quest and self.active_quest_id == "quest-volya-root":
            appear_t = 1.0

        if appear_t <= 0.0:
            return

        volya_pix = self.get_volya_logo_pixmap(size=128)
        self._draw_bead_disc(
            painter,
            self.spiral_center,
            64.0 * appear_t,
            volya_pix,
            glow_color,
            core_color,
            hovered=self._spiral_hovered,
        )

    def _draw_tree_stem_and_branches(
        self, painter: QPainter, stem_color: QColor, glow_color: QColor
    ) -> None:
        """Отрисовка ниспадающего утончающегося ствола Древа и гибких веточек к квестам."""
        stem_x = self.spiral_center.x()
        stem_top_y = self.spiral_center.y() + self.spiral_radius  # 104.0

        # Ствол имеет плавное органическое продолжение вниз за нижнее ответвление
        stem_nodes = [n for n in self.tree_nodes if abs(n.parent_pos.x() - stem_x) < 1.0]
        max_y = max((n.parent_pos.y() for n in stem_nodes), default=stem_top_y)
        stem_bottom_target = (max_y + 55.0) if stem_nodes else stem_top_y

        # Фаза разворачивания ствола: 0.50 -> 0.75
        stem_t = min(1.0, max(0.0, (self._unfold_progress - 0.50) / 0.25))
        current_stem_bottom = stem_top_y + (stem_bottom_target - stem_top_y) * stem_t

        pts_stem = []
        stem_glow = QPainterPath()
        stem_body = QPainterPath()

        # 1. Живой ствол Древа: утончается сверху вниз (4.8px -> 2.0px)
        if current_stem_bottom > stem_top_y:
            stem_steps = 32
            max_s = max(1, int(stem_steps * stem_t))
            for i in range(max_s + 1):
                y = stem_top_y + (current_stem_bottom - stem_top_y) * (i / max_s)
                pts_stem.append(self._trunk_point(y, stem_top_y))

            w_s = 4.8
            w_e = 4.8 * (1.0 - stem_t) + 2.0 * stem_t
            stem_glow = self._make_ribbon_path(pts_stem, w_s, w_e, expand=3.0)
            stem_body = self._make_ribbon_path(pts_stem, w_s, w_e, expand=0.0)

        # 2. Живые веточки к узлам (фаза: 0.70 -> 1.0)
        branch_t = min(1.0, max(0.0, (self._unfold_progress - 0.70) / 0.30))
        branch_glows = []
        branch_bodies = []
        branch_spines = []

        if branch_t > 0.0:
            child_parent_ids = {n.quest.parent_quest_id for n in self.tree_nodes}

            for node in self.tree_nodes:
                if node == self._gliding_node:
                    continue

                is_from_stem = abs(node.parent_pos.x() - stem_x) < 1.0
                p_start = self._trunk_point(node.parent_pos.y(), stem_top_y) if is_from_stem else node.parent_pos
                p_quest = node.target_pos
                radius = node.current_size / 2.0
                has_child = node.quest.id in child_parent_ids

                w_start = 3.6 if is_from_stem else 2.6
                w_end = 2.0 if has_child else 1.0

                bdx = p_quest.x() - p_start.x()
                bdy = p_quest.y() - p_start.y()

                # Естественный природный изгиб с плавным отхождением от ствола без изломов
                if node.branch_type == "root_child":
                    bc1 = QPointF(p_start.x() + bdx * 0.35, p_start.y() + 6.0)
                    bc2 = QPointF(p_start.x() + bdx * 0.75, p_quest.y() - 10.0)
                elif node.branch_type == "trunk":
                    bc1 = QPointF(p_start.x() + bdx * 0.35, p_start.y() + 6.0)
                    bc2 = QPointF(p_start.x() + bdx * 0.75, p_quest.y() - 8.0)
                elif node.branch_type == "house":
                    bc1 = QPointF(p_start.x() + bdx * 0.25 - 12.0, p_start.y() + bdy * 0.50)
                    bc2 = QPointF(p_start.x() + bdx * 0.70 - 10.0, p_start.y() + bdy * 0.85)
                else:
                    bc1 = QPointF(p_start.x() + bdx * 0.40 + 12.0, p_start.y() + bdy * 0.30)
                    bc2 = QPointF(p_start.x() + bdx * 0.80 + 8.0, p_start.y() + bdy * 0.75)

                tdx = p_quest.x() - bc2.x()
                tdy = p_quest.y() - bc2.y()
                tlen = math.hypot(tdx, tdy) or 1.0
                t_ux = tdx / tlen
                t_uy = tdy / tlen

                N = 32
                full_pts = []
                if has_child:
                    # Ветвь к родительскому квесту плавно входит в его центр
                    for i in range(N + 1):
                        t = i / N
                        mt = 1.0 - t
                        full_pts.append(QPointF(
                            mt**3 * p_start.x() + 3.0*mt**2*t * bc1.x() + 3.0*mt*t**2 * bc2.x() + t**3 * p_quest.x(),
                            mt**3 * p_start.y() + 3.0*mt**2*t * bc1.y() + 3.0*mt*t**2 * bc2.y() + t**3 * p_quest.y(),
                        ))
                else:
                    # Терминальный квест: ветвь проходит под центром квеста и продолжается растущим побегом
                    ext_len = radius + 22.0
                    curl_x = -t_uy * 4.0
                    curl_y = t_ux * 4.0
                    p_tip = QPointF(p_quest.x() + t_ux * ext_len + curl_x, p_quest.y() + t_uy * ext_len + curl_y)
                    bc3 = QPointF(p_quest.x() + t_ux * (ext_len * 0.45), p_quest.y() + t_uy * (ext_len * 0.45))

                    for i in range(N + 1):
                        u = i / N
                        if u <= 0.68:
                            t = u / 0.68
                            mt = 1.0 - t
                            full_pts.append(QPointF(
                                mt**3 * p_start.x() + 3.0*mt**2*t * bc1.x() + 3.0*mt*t**2 * bc2.x() + t**3 * p_quest.x(),
                                mt**3 * p_start.y() + 3.0*mt**2*t * bc1.y() + 3.0*mt*t**2 * bc2.y() + t**3 * p_quest.y(),
                            ))
                        else:
                            t = (u - 0.68) / 0.32
                            mt = 1.0 - t
                            full_pts.append(QPointF(
                                mt**2 * p_quest.x() + 2.0*mt*t * bc3.x() + t**2 * p_tip.x(),
                                mt**2 * p_quest.y() + 2.0*mt*t * bc3.y() + t**2 * p_tip.y(),
                            ))

                # Срез точек по текущему прогрессу раскрытия ветвей
                max_b = max(1, int(N * branch_t))
                active_pts = full_pts[:max_b + 1]
                w_cur_end = w_start * (1.0 - branch_t) + w_end * branch_t
                branch_glows.append(self._make_ribbon_path(active_pts, w_start, w_cur_end, expand=3.0))
                branch_bodies.append(self._make_ribbon_path(active_pts, w_start, w_cur_end, expand=0.0))
                if len(active_pts) >= 2:
                    branch_spines.append(active_pts)

        # 3. Бесшовное объединение ствола и всех ветвей (ликвидация любых стыков и узелков)
        united_glow = stem_glow
        for bg in branch_glows:
            united_glow = united_glow.united(bg)

        united_body = stem_body
        for bb in branch_bodies:
            united_body = united_body.united(bb)

        if not united_body.isEmpty():
            night = self.is_night()
            p_top = pts_stem[0] if pts_stem else QPointF(stem_x, stem_top_y)
            p_bot = pts_stem[-1] if pts_stem else QPointF(stem_x, current_stem_bottom)
            grad = QLinearGradient(p_top, p_bot)

            if night:
                glow_col = QColor(241, 245, 249, 35)
                rim_color = QColor(255, 255, 255, 130)
                spine_color = QColor(255, 255, 255, 200)
                grad.setColorAt(0.0, QColor(255, 255, 255, 240))
                grad.setColorAt(0.4, QColor(226, 232, 240, 220))
                grad.setColorAt(1.0, QColor(148, 163, 184, 190))
            else:
                glow_col = QColor(250, 204, 21, 40)
                rim_color = QColor(254, 240, 138, 160)
                spine_color = QColor(255, 255, 255, 210)
                grad.setColorAt(0.0, QColor(254, 240, 138, 250))
                grad.setColorAt(0.4, QColor(250, 204, 21, 230))
                grad.setColorAt(1.0, QColor(217, 119, 6, 190))

            # 3.1. Единый внешний ореол свечения
            if not united_glow.isEmpty():
                painter.setPen(Qt.NoPen)
                painter.setBrush(glow_col)
                painter.drawPath(united_glow)

            # 3.2. Единое монолитное тело Древа со световым рельефным кантом
            painter.setBrush(QBrush(grad))
            painter.setPen(QPen(rim_color, 0.85))
            painter.drawPath(united_body)

            # 3.3. Непрерывная спекулярная жила ствола
            if pts_stem and len(pts_stem) >= 2:
                spine_stem = QPainterPath()
                spine_stem.moveTo(pts_stem[0])
                for p in pts_stem[1:]:
                    spine_stem.lineTo(p)
                painter.setBrush(Qt.NoBrush)
                painter.setPen(QPen(spine_color, 1.1, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                painter.drawPath(spine_stem)

            # 3.4. Спекулярные жилы боковых веточек (мягко выходят из ствола без узелков)
            branch_spine_pen = QPen(spine_color, 1.0, Qt.SolidLine, Qt.FlatCap, Qt.RoundJoin)
            painter.setPen(branch_spine_pen)
            for b_pts in branch_spines:
                if len(b_pts) >= 2:
                    b_spine = QPainterPath()
                    b_spine.moveTo(b_pts[1])
                    for p in b_pts[2:]:
                        b_spine.lineTo(p)
                    painter.drawPath(b_spine)

    def _draw_quest_beads(self, painter: QPainter, glow_color: QColor, core_color: QColor) -> None:
        """Отрисовка круглых бусинок квестов, расположенных поверх ветвей по центру."""
        # Фаза распускания бусинок: 0.80 -> 1.0
        beads_t = min(1.0, max(0.0, (self._unfold_progress - 0.80) / 0.20))
        if beads_t <= 0.0:
            return

        for node in self.tree_nodes:
            if node == self._gliding_node or node == self._pending_selection_node:
                continue

            size = node.current_size * beads_t

            # Диск бусинки квеста поверх ветви по центру
            self._draw_bead_disc(
                painter,
                node.current_pos,
                size,
                node.pixmap,
                glow_color,
                core_color,
                hovered=node.hovered,
            )

    def _draw_single_bead(
        self, painter: QPainter, node: QuestTreeNode, glow_color: QColor, core_color: QColor
    ) -> None:
        """Отрисовка скользящей или ожидающей бусинки."""
        self._draw_bead_disc(
            painter,
            node.current_pos,
            node.current_size,
            node.pixmap,
            glow_color,
            core_color,
            hovered=True,
        )

    def _draw_bead_disc(
        self,
        painter: QPainter,
        center: QPointF,
        diameter: float,
        pixmap: Optional[QPixmap],
        glow_color: QColor,
        core_color: QColor,
        hovered: bool = False,
    ) -> None:
        """Отрисовка одной круглой бусинки с аватаркой, градиентным свечением и ободком."""
        radius = max(2.0, diameter / 2.0)
        cx = center.x()
        cy = center.y()

        # 1. Радиальное градиентное свечение от контура бусинки
        glow_spread = 8.0 if hovered else 5.5
        r_outer = radius + glow_spread
        r_ratio = radius / r_outer
        span = 1.0 - r_ratio

        peak_alpha = 190 if hovered else 130
        grad = QRadialGradient(center, r_outer)
        grad.setColorAt(0.0, QColor(glow_color.red(), glow_color.green(), glow_color.blue(), 0))
        grad.setColorAt(max(0.0, r_ratio * 0.94), QColor(glow_color.red(), glow_color.green(), glow_color.blue(), 0))
        grad.setColorAt(r_ratio, QColor(glow_color.red(), glow_color.green(), glow_color.blue(), peak_alpha))
        grad.setColorAt(r_ratio + span * 0.35, QColor(glow_color.red(), glow_color.green(), glow_color.blue(), int(peak_alpha * 0.50)))
        grad.setColorAt(r_ratio + span * 0.70, QColor(glow_color.red(), glow_color.green(), glow_color.blue(), int(peak_alpha * 0.15)))
        grad.setColorAt(1.0, QColor(glow_color.red(), glow_color.green(), glow_color.blue(), 0))

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawEllipse(center, r_outer, r_outer)

        # 2. Аватарка квеста с круглой обрезкой
        if pixmap and not pixmap.isNull():
            clip_path = QPainterPath()
            clip_path.addEllipse(center, radius, radius)
            painter.save()
            painter.setClipPath(clip_path)
            target_rect = QRectF(cx - radius, cy - radius, radius * 2.0, radius * 2.0)
            painter.drawPixmap(target_rect.toRect(), pixmap)
            painter.restore()
        else:
            # Тёмный стеклянный диск, если аватарка ещё загружается
            painter.setBrush(QColor(18, 26, 44, 220))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(center, radius, radius)

        # 3. Тонкий контурный ободок
        rim_alpha = 240 if hovered else 180
        rim_pen = QPen(QColor(core_color.red(), core_color.green(), core_color.blue(), rim_alpha), 1.5 if hovered else 1.2)
        painter.setPen(rim_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(center, radius, radius)

    def _draw_hover_tooltip(self, painter: QPainter) -> None:
        """Отрисовка лёгкого полупрозрачного облака с названием квеста при наведении."""
        text = ""
        pos = QPointF()

        if self._hovered_bead:
            text = self._hovered_bead.quest.title
            pos = self._hovered_bead.current_pos
        elif self._spiral_hovered:
            pos = self.spiral_center
            # Если выбран другой квест и дерево закрыто — подсказка показывает имя выбранного квеста
            if self.has_selected_quest and self.active_quest_id != "quest-volya-root" and not self._tree_open:
                text = self.active_quest_title
            else:
                # Для квеста «Воля» подсказки нет вообще
                text = ""

        # Для квеста «Воля» подсказки нет вообще
        if not text or text.strip() == "Воля":
            return

        font = QFont("Georgia", 11)
        fm = QFontMetrics(font)
        text_w = fm.horizontalAdvance(text)
        cloud_w = max(56.0, text_w + 24.0)
        cloud_h = 28.0

        cloud_x = pos.x() - cloud_w / 2.0
        cloud_y = pos.y() + 34.0
        cloud_rect = QRectF(cloud_x, cloud_y, cloud_w, cloud_h)

        night = self.is_night()
        if night:
            # Эфирное лунное облако
            cloud_brush = QColor(255, 255, 255, 26)
            cloud_pen = QPen(QColor(255, 255, 255, 55), 1.0)
            text_color = QColor(241, 245, 249, 240)
        else:
            # Тёплое солнечное полупрозрачное облако
            cloud_brush = QColor(255, 255, 255, 48)
            cloud_pen = QPen(QColor(254, 240, 138, 70), 1.0)
            text_color = QColor(255, 253, 231, 245)

        painter.setPen(cloud_pen)
        painter.setBrush(cloud_brush)
        painter.drawRoundedRect(cloud_rect, 14.0, 14.0)

        painter.setFont(font)
        painter.setPen(text_color)
        painter.drawText(cloud_rect, Qt.AlignCenter, text)

    # -------------------------------------------------------------
    # Интерактив и Отрисовка Сакральных Дуг Потоков (Выбор и Создание)
    # -------------------------------------------------------------

    def _handle_flow_mouse_move(self, pt: QPointF) -> bool:
        """Обработка наведения на дуги и органы управления Потоками квеста."""
        dist_quest = math.hypot(pt.x() - self.spiral_center.x(), pt.y() - self.spiral_center.y())

        # 1. Наведение на сам выбранный квест -> раскрываются ОБЕ дуги
        if dist_quest <= (self.spiral_radius + 6.0):
            if self._flow_menu_mode == "none":
                self._flow_menu_mode = "both"
                self.refresh_flows_and_players()
            self._flow_close_timer.stop()
            self.setCursor(Qt.PointingHandCursor)
            return True

        # 2. Если меню открыто в режиме "both", фокус на дугу скрывает другую:
        if self._flow_menu_mode == "both":
            # Движение вправо к дуге выбора
            if pt.x() > (self.spiral_center.x() + 20.0) and abs(pt.y() - self.spiral_center.y()) < 50.0:
                self._flow_menu_mode = "select"
                if not self._sel_flow_kind:
                    self._sel_flow_kind = FlowKind.DIALOGUE
            # Движение вниз к дуге создания
            elif pt.y() > (self.spiral_center.y() + 22.0) and abs(pt.x() - self.spiral_center.x()) < 50.0:
                self._flow_menu_mode = "create"

        # 3. Интерактив режима выбора потоков (Правая дуга)
        if self._flow_menu_mode in ("both", "select"):
            c_dia = QPointF(306.6, 54.8)
            c_conv = QPointF(306.6, 89.2)
            d_dia = math.hypot(pt.x() - c_dia.x(), pt.y() - c_dia.y())
            d_conv = math.hypot(pt.x() - c_conv.x(), pt.y() - c_conv.y())

            if d_dia <= 15.0:
                self._hovered_flow_kind_disc = FlowKind.DIALOGUE
                self._sel_flow_kind = FlowKind.DIALOGUE
                self._flow_menu_mode = "select"
                self._flow_close_timer.stop()
                self.setCursor(Qt.PointingHandCursor)
                return True
            elif d_conv <= 15.0:
                self._hovered_flow_kind_disc = FlowKind.CONVERSATION
                self._sel_flow_kind = FlowKind.CONVERSATION
                self._flow_menu_mode = "select"
                self._flow_close_timer.stop()
                self.setCursor(Qt.PointingHandCursor)
                return True
            else:
                self._hovered_flow_kind_disc = None

            # Проверка наведения на элементы списка потоков
            if self._sel_flow_kind:
                flows = [f for f in self._quest_flows_cache if f.kind == self._sel_flow_kind]
                self._hovered_flow_item = None
                start_y = 54.8 if self._sel_flow_kind == FlowKind.DIALOGUE else 89.2
                stem_x = 392.0
                for idx, f in enumerate(flows):
                    y_f = (start_y + 48.0) + idx * 36.0
                    r_f = QRectF(stem_x + 30.0, y_f - 14.0, 200.0, 28.0)
                    if r_f.contains(pt):
                        self._hovered_flow_item = f
                        self._flow_close_timer.stop()
                        self.setCursor(Qt.PointingHandCursor)
                        return True

        # 4. Интерактив режима создания потока (Нижняя дуга)
        if self._flow_menu_mode in ("both", "create"):
            c_seg = QPointF(264.0, 118.0)
            d_seg = math.hypot(pt.x() - c_seg.x(), pt.y() - c_seg.y())
            if d_seg <= 17.0:
                self._flow_menu_mode = "create"
                if pt.x() <= 264.0:
                    self._hovered_create_segment = FlowKind.DIALOGUE
                else:
                    self._hovered_create_segment = FlowKind.CONVERSATION
                self._flow_close_timer.stop()
                self.setCursor(Qt.PointingHandCursor)
                return True
            else:
                self._hovered_create_segment = None

            # Проверка кнопки '>' перехода к игрокам
            if self._create_step in ("title", "players"):
                c_next_in = QPointF(self.flow_title_input.x() + self.flow_title_input.width() - 14.0, 184.0)
                if math.hypot(pt.x() - c_next_in.x(), pt.y() - c_next_in.y()) <= 15.0 or (330.0 <= pt.x() <= 385.0 and 168.0 <= pt.y() <= 200.0):
                    self._hovered_create_next_btn = True
                    self._flow_close_timer.stop()
                    self.setCursor(Qt.PointingHandCursor)
                    return True
                else:
                    self._hovered_create_next_btn = False

            # Проверка кнопки подтверждения '✔' для беседы
            if self._create_step == "players" and self._create_flow_kind == FlowKind.CONVERSATION:
                c_conf = QPointF(420.0, 202.0)
                if math.hypot(pt.x() - c_conf.x(), pt.y() - c_conf.y()) <= 15.0:
                    self._hovered_create_confirm_btn = True
                    self._flow_close_timer.stop()
                    self.setCursor(Qt.PointingHandCursor)
                    return True
                else:
                    self._hovered_create_confirm_btn = False

            # Проверка списка игроков
            if self._create_step == "players":
                self._hovered_player_item = None
                for idx, p in enumerate(self._quest_players_cache):
                    y_p = 232.0 + idx * 36.0
                    r_p = QRectF(436.0, y_p - 14.0, 160.0, 28.0)
                    if r_p.contains(pt):
                        self._hovered_player_item = p
                        self._flow_close_timer.stop()
                        self.setCursor(Qt.PointingHandCursor)
                        return True

        # 5. Если курсор вне активных зон — запускаем мягкий таймер затухания
        in_active_zone = False
        if self._flow_menu_mode in ("both", "select"):
            if 240.0 <= pt.x() <= 580.0 and 20.0 <= pt.y() <= 340.0:
                in_active_zone = True
        if self._flow_menu_mode in ("both", "create"):
            if 160.0 <= pt.x() <= 620.0 and 50.0 <= pt.y() <= 520.0:
                in_active_zone = True

        if not in_active_zone and self._flow_menu_mode != "none":
            if not self._flow_close_timer.isActive():
                self._flow_close_timer.start(700)

        return False

    def _handle_flow_mouse_press(self, pt: QPointF) -> bool:
        """Обработка кликов по органам выбора и создания потоков."""
        if self._flow_menu_mode in ("both", "select"):
            if self._hovered_flow_kind_disc:
                self._sel_flow_kind = self._hovered_flow_kind_disc
                self._flow_menu_mode = "select"
                return True

            if self._hovered_flow_item:
                flow_id = self._hovered_flow_item.id
                self._flow_menu_mode = "none"
                self.flow_selected.emit(flow_id)
                return True

        if self._flow_menu_mode in ("both", "create"):
            if self._hovered_create_segment:
                self._create_flow_kind = self._hovered_create_segment
                self._create_step = "title"
                self._flow_menu_mode = "create"
                kind_ru = "диалога" if self._create_flow_kind == FlowKind.DIALOGUE else "беседы"
                self.flow_title_input.clear()
                self.flow_title_input.setPlaceholderText(f"Имя {kind_ru}...")
                self.flow_title_input.setGeometry(int(264.0 - 95.0), 170, 190, 28)
                self.flow_next_btn.move(self.flow_title_input.width() - 25, (self.flow_title_input.height() - 22) // 2)
                self.flow_next_btn.show()
                self.flow_title_input.setVisible(True)
                self.flow_title_input.setFocus()
                return True

            if self._hovered_create_next_btn:
                self._proceed_to_players()
                return True

            if self._hovered_player_item:
                if self._create_flow_kind == FlowKind.DIALOGUE:
                    # Выбор одного игрока сразу завершает создание диалога
                    title = self.flow_title_input.text().strip() or f"Диалог с {self._hovered_player_item.username}"
                    flow = self.node.create_quest_flow(
                        self.active_quest_id,
                        FlowKind.DIALOGUE,
                        title,
                        [self._hovered_player_item.pubkey],
                    )
                    self._on_flow_menu_close_timeout()
                    self.flow_selected.emit(flow.id)
                    return True
                else:
                    # Беседа: мультивыбор участников
                    pk = self._hovered_player_item.pubkey
                    if pk in self._selected_participants:
                        if len(self._selected_participants) > 1:
                            self._selected_participants.remove(pk)
                    else:
                        self._selected_participants.add(pk)
                    return True

            if self._hovered_create_confirm_btn and self._create_flow_kind == FlowKind.CONVERSATION:
                title = self.flow_title_input.text().strip() or f"Беседа квеста {self.active_quest_title}"
                flow = self.node.create_quest_flow(
                    self.active_quest_id,
                    FlowKind.CONVERSATION,
                    title,
                    list(self._selected_participants),
                )
                self._on_flow_menu_close_timeout()
                self.flow_selected.emit(flow.id)
                return True

        return False

    def _proceed_to_players(self) -> None:
        """Переход от ввода названия потока к выбору участников."""
        self._create_step = "players"
        self._quest_players_cache = self.node.get_quest_players(self.active_quest_id)
        if self._quest_players_cache:
            self._selected_participants = {self._quest_players_cache[0].pubkey}
        self.update()

    def _draw_flow_selection_and_creation(
        self, painter: QPainter, glow_color: QColor, core_color: QColor
    ) -> None:
        """Отрисовка дуг и органов управления Потоками сотворчества у выбранного квеста."""
        if self._flow_menu_mode == "none":
            return

        night = self.is_night()
        quest_center = self.spiral_center  # QPointF(264.0, 72.0)
        arc_radius = 46.0

        # 1. Правая дуга (Выбор потока)
        if self._flow_menu_mode in ("both", "select"):
            self._draw_right_flow_selection_arc(painter, quest_center, arc_radius, glow_color, core_color, night)

        # 2. Нижняя дуга (Создание потока)
        if self._flow_menu_mode in ("both", "create"):
            self._draw_bottom_flow_creation_arc(painter, quest_center, arc_radius, glow_color, core_color, night)

    def _draw_right_flow_selection_arc(
        self,
        painter: QPainter,
        center: QPointF,
        radius: float,
        glow_color: QColor,
        core_color: QColor,
        night: bool,
    ) -> None:
        """Отрисовка правой дуги выбора потока с кружками-типами (Диалог и Беседа) и ветками."""
        arc_box = QRectF(center.x() - radius, center.y() - radius, 2 * radius, 2 * radius)
        start_angle = int(-45 * 16)
        span_angle = int(90 * 16)

        # Ореол и светящееся ядро дуги
        glow_pen = QPen(QColor(glow_color.red(), glow_color.green(), glow_color.blue(), 100), 4.8, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(glow_pen)
        painter.drawArc(arc_box, start_angle, span_angle)

        core_pen = QPen(QColor(core_color.red(), core_color.green(), core_color.blue(), 230), 2.2, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(core_pen)
        painter.drawArc(arc_box, start_angle, span_angle)

        # Точки кружков на дуге:
        # Диалог (-22°) и Беседа (+22°)
        c_dia = QPointF(306.6, 54.8)
        c_conv = QPointF(306.6, 89.2)

        # 1. СНАЧАЛА отрисовываем ветвь со списком потоков:
        # Она начинается ИЗ-ПОД кружка снизу, а не поверх его центра!
        if self._sel_flow_kind in (FlowKind.DIALOGUE, FlowKind.CONVERSATION):
            start_p = c_dia if self._sel_flow_kind == FlowKind.DIALOGUE else c_conv
            self._draw_flow_stream_branches(painter, start_p, self._sel_flow_kind, glow_color, core_color, night)

        # 2. Отрисовка кружка «Диалог» поверх основания ветви
        is_dia_hovered = (self._hovered_flow_kind_disc == FlowKind.DIALOGUE or self._sel_flow_kind == FlowKind.DIALOGUE)
        self._draw_flow_type_circle(painter, c_dia, 13.0, FlowKind.DIALOGUE, is_dia_hovered, glow_color, core_color, night)

        # 3. Отрисовка кружка «Беседа» поверх основания ветви
        is_conv_hovered = (self._hovered_flow_kind_disc == FlowKind.CONVERSATION or self._sel_flow_kind == FlowKind.CONVERSATION)
        self._draw_flow_type_circle(painter, c_conv, 13.0, FlowKind.CONVERSATION, is_conv_hovered, glow_color, core_color, night)

    def _draw_flow_type_circle(
        self,
        painter: QPainter,
        center: QPointF,
        radius: float,
        kind: FlowKind,
        is_active: bool,
        glow_color: QColor,
        core_color: QColor,
        night: bool,
    ) -> None:
        """Отрисовка кружка типа потока с процедурным сакральным глифом."""
        # Ореол
        if is_active:
            grad = QRadialGradient(center, radius + 8.0)
            grad.setColorAt(0.0, QColor(glow_color.red(), glow_color.green(), glow_color.blue(), 190))
            grad.setColorAt(0.6, QColor(glow_color.red(), glow_color.green(), glow_color.blue(), 80))
            grad.setColorAt(1.0, QColor(glow_color.red(), glow_color.green(), glow_color.blue(), 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(grad))
            painter.drawEllipse(center, radius + 8.0, radius + 8.0)

        # Тело кружка
        bg_color = QColor(24, 32, 54, 230) if night else QColor(42, 36, 24, 220)
        painter.setPen(Qt.NoPen)
        painter.setBrush(bg_color)
        painter.drawEllipse(center, radius, radius)

        # Ободок
        border_alpha = 240 if is_active else 150
        border_pen = QPen(QColor(core_color.red(), core_color.green(), core_color.blue(), border_alpha), 1.5 if is_active else 1.1)
        painter.setPen(border_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(center, radius, radius)

        # Процедурная иконка
        painter.save()
        painter.translate(center.x(), center.y())
        icon_pen = QPen(core_color if is_active else glow_color, 1.4, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(icon_pen)
        painter.setBrush(Qt.NoBrush)

        if kind == FlowKind.DIALOGUE:
            # Две встречные сакральные дуги (симбиоз диалога)
            painter.drawArc(QRectF(-6.5, -6.5, 9.0, 13.0), int(-70 * 16), int(140 * 16))
            painter.drawArc(QRectF(-2.5, -6.5, 9.0, 13.0), int(110 * 16), int(140 * 16))
            painter.setBrush(core_color)
            painter.drawEllipse(QPointF(0, 0), 1.4, 1.4)
        else:
            # Триада созвездия (беседа)
            p1 = QPointF(0.0, -4.8)
            p2 = QPointF(-4.5, 3.5)
            p3 = QPointF(4.5, 3.5)
            line_pen = QPen(QColor(glow_color.red(), glow_color.green(), glow_color.blue(), 140), 0.9)
            painter.setPen(line_pen)
            painter.drawLine(p1, p2)
            painter.drawLine(p2, p3)
            painter.drawLine(p3, p1)

            painter.setPen(Qt.NoPen)
            painter.setBrush(core_color)
            painter.drawEllipse(p1, 2.0, 2.0)
            painter.drawEllipse(p2, 2.0, 2.0)
            painter.drawEllipse(p3, 2.0, 2.0)

        painter.restore()

    def _draw_flow_stream_branches(
        self,
        painter: QPainter,
        start_pt: QPointF,
        kind: FlowKind,
        glow_color: QColor,
        core_color: QColor,
        night: bool,
    ) -> None:
        """Отрисовка органической ветви вправо и вниз со списком существующих потоков."""
        flows = [f for f in self._quest_flows_cache if f.kind == kind]
        count = max(1, len(flows))
        stem_x = 392.0
        y_top = start_pt.y()
        y_last_item = (y_top + 48.0) + (count - 1) * 36.0
        y_bottom = y_last_item + 42.0

        # 1. Главная ветвь: сначала далеко ВПРАВО, затем ПЛАВНО ВНИЗ без острых углов
        pts: List[QPointF] = []
        bend_steps = 24
        p0 = start_pt
        c1 = QPointF(start_pt.x() + 54.0, y_top)      # строго горизонтальный отход вправо
        c2 = QPointF(stem_x, y_top + 10.0)            # плавное закругление
        p3 = QPointF(stem_x, y_top + 42.0)            # строго вертикальный вход вниз

        for i in range(bend_steps + 1):
            t = i / bend_steps
            x = (1 - t)**3 * p0.x() + 3 * (1 - t)**2 * t * c1.x() + 3 * (1 - t) * t**2 * c2.x() + t**3 * p3.x()
            y = (1 - t)**3 * p0.y() + 3 * (1 - t)**2 * t * c1.y() + 3 * (1 - t) * t**2 * c2.y() + t**3 * p3.y()
            pts.append(QPointF(x, y))

        # Ствол вниз между элементами
        v_steps = max(6, count * 6)
        for i in range(1, v_steps + 1):
            t = i / v_steps
            y = (y_top + 42.0) + (y_last_item - (y_top + 42.0)) * t
            pts.append(QPointF(stem_x, y))

        # 2. Плавное органическое утоньшение кончика ветви (без обрыва!)
        tail_steps = 14
        for i in range(1, tail_steps + 1):
            u = i / tail_steps
            y = y_last_item + (y_bottom - y_last_item) * u
            # легкий живой природный изгиб
            x = stem_x + 2.5 * math.sin(u * math.pi)
            pts.append(QPointF(x, y))

        # Отрисовка объемной утончающейся ветви (от 3.4px до тончайших 0.5px на кончике!)
        self._draw_volumetric_branch(painter, pts, 3.4, 0.5, night)

        # 3. Живые гибкие веточки к каждому потоку
        font = QFont("Georgia", 10)
        font.setBold(False)
        fm = QFontMetrics(font)

        for idx, flow in enumerate(flows):
            y_item = (y_top + 48.0) + idx * 36.0
            p_twig_start = QPointF(stem_x, y_item)
            p_twig_end = QPointF(stem_x + 30.0, y_item)

            is_hov = (self._hovered_flow_item == flow)

            # Формируем органическую изогнутую веточку (кубический сплайн вместо прямой!)
            twig_pts: List[QPointF] = []
            tw_steps = 10
            tw_c1 = QPointF(stem_x + 9.0, y_item + 1.8)
            tw_c2 = QPointF(stem_x + 20.0, y_item - 2.2)

            for ti in range(tw_steps + 1):
                tt = ti / tw_steps
                tx = (1 - tt)**3 * p_twig_start.x() + 3 * (1 - tt)**2 * tt * tw_c1.x() + 3 * (1 - tt) * tt**2 * tw_c2.x() + tt**3 * p_twig_end.x()
                ty = (1 - tt)**3 * p_twig_start.y() + 3 * (1 - tt)**2 * tt * tw_c1.y() + 3 * (1 - tt) * tt**2 * tw_c2.y() + tt**3 * p_twig_end.y()
                twig_pts.append(QPointF(tx, ty))

            # Отрисовываем веточку утончающейся лентой (от 2.2px к 0.8px)
            self._draw_volumetric_branch(painter, twig_pts, 2.2, 0.8, night)

            # Концевая почка веточки
            painter.setPen(Qt.NoPen)
            painter.setBrush(core_color if is_hov else glow_color)
            painter.drawEllipse(p_twig_end, 2.2 if is_hov else 1.6, 2.2 if is_hov else 1.6)

            # Табличка названия потока
            t_w = fm.horizontalAdvance(flow.title)
            pill_rect = QRectF(stem_x + 34.0, y_item - 12.0, max(84.0, t_w + 18.0), 24.0)

            if is_hov:
                painter.setBrush(QColor(234, 179, 8, 45))
                painter.setPen(QPen(QColor(254, 240, 138, 185), 1.0))
                painter.drawRoundedRect(pill_rect, 12.0, 12.0)
                text_color = QColor(254, 240, 138, 255)
            else:
                painter.setBrush(QColor(18, 26, 44, 150))
                painter.setPen(QPen(QColor(255, 255, 255, 45), 1.0))
                painter.drawRoundedRect(pill_rect, 12.0, 12.0)
                text_color = QColor(226, 232, 240, 215)

            painter.setFont(font)
            painter.setPen(text_color)
            painter.drawText(pill_rect, Qt.AlignCenter, flow.title)

    def _draw_bottom_flow_creation_arc(
        self,
        painter: QPainter,
        center: QPointF,
        radius: float,
        glow_color: QColor,
        core_color: QColor,
        night: bool,
    ) -> None:
        """Отрисовка нижней дуги создания потока с разделенным на сегменты кружком."""
        arc_box = QRectF(center.x() - radius, center.y() - radius, 2 * radius, 2 * radius)
        start_angle = int(-135 * 16)
        span_angle = int(90 * 16)

        # Если сектор активирован (выбран тип потока) — дуга не рисуется по слову Сига!
        is_activated = (self._create_flow_kind is not None or self._create_step in ("title", "players"))
        if not is_activated:
            # Ореол и светящееся ядро дуги (видны только до активизации сектора)
            glow_pen = QPen(QColor(glow_color.red(), glow_color.green(), glow_color.blue(), 100), 4.8, Qt.SolidLine, Qt.RoundCap)
            painter.setPen(glow_pen)
            painter.drawArc(arc_box, start_angle, span_angle)

            core_pen = QPen(QColor(core_color.red(), core_color.green(), core_color.blue(), 230), 2.2, Qt.SolidLine, Qt.RoundCap)
            painter.setPen(core_pen)
            painter.drawArc(arc_box, start_angle, span_angle)

        # Центр сегментированного кружка на нижней дуге (90°)
        c_seg = QPointF(center.x(), center.y() + radius)  # (264.0, 118.0)
        self._draw_creation_segmented_circle(painter, c_seg, 16.0, glow_color, core_color, night)

        # Если нажат сегмент — веточка вниз к полю ввода названия
        if self._create_step in ("title", "players"):
            self._draw_creation_stem_to_input(painter, c_seg, glow_color, core_color, night)

    def _draw_creation_segmented_circle(
        self,
        painter: QPainter,
        center: QPointF,
        radius: float,
        glow_color: QColor,
        core_color: QColor,
        night: bool,
    ) -> None:
        """Отрисовка кружка, разделенного на 2 сегмента: Диалог (слева) и Беседа (справа)."""
        left_hovered = (self._hovered_create_segment == FlowKind.DIALOGUE or self._create_flow_kind == FlowKind.DIALOGUE)
        right_hovered = (self._hovered_create_segment == FlowKind.CONVERSATION or self._create_flow_kind == FlowKind.CONVERSATION)

        # 0. Сплошная непрозрачная подложка диска (чтобы фон и дуги сзади никогда не просвечивали)
        painter.save()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(16, 22, 38, 255))
        painter.drawEllipse(center, radius, radius)
        painter.restore()

        # 1. Левый сегмент (Диалог)
        painter.save()
        clip_left = QPainterPath()
        clip_left.addRect(QRectF(center.x() - radius - 4, center.y() - radius - 4, radius + 4, 2 * radius + 8))
        painter.setClipPath(clip_left)

        brush_l = QColor(212, 165, 36, 230) if left_hovered else QColor(24, 32, 54, 240)
        painter.setBrush(brush_l)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(center, radius, radius)

        # Иконка диалога слева
        p_dia_icon = QPointF(center.x() - radius * 0.45, center.y())
        pen_dia = QPen(QColor(14, 20, 34, 240) if left_hovered else glow_color, 1.4, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen_dia)
        painter.setBrush(Qt.NoBrush)
        painter.drawArc(QRectF(p_dia_icon.x() - 4.5, p_dia_icon.y() - 5.5, 6.0, 11.0), int(-70 * 16), int(140 * 16))
        painter.drawArc(QRectF(p_dia_icon.x() - 1.5, p_dia_icon.y() - 5.5, 6.0, 11.0), int(110 * 16), int(140 * 16))
        painter.restore()

        # 2. Правый сегмент (Беседа)
        painter.save()
        clip_right = QPainterPath()
        clip_right.addRect(QRectF(center.x(), center.y() - radius - 4, radius + 4, 2 * radius + 8))
        painter.setClipPath(clip_right)

        brush_r = QColor(212, 165, 36, 230) if right_hovered else QColor(24, 32, 54, 240)
        painter.setBrush(brush_r)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(center, radius, radius)

        # Иконка беседы справа
        p_c_r = QPointF(center.x() + radius * 0.45, center.y())
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(14, 20, 34, 240) if right_hovered else glow_color)
        painter.drawEllipse(QPointF(p_c_r.x(), p_c_r.y() - 3.5), 1.5, 1.5)
        painter.drawEllipse(QPointF(p_c_r.x() - 3.0, p_c_r.y() + 2.5), 1.5, 1.5)
        painter.drawEllipse(QPointF(p_c_r.x() + 3.0, p_c_r.y() + 2.5), 1.5, 1.5)
        painter.restore()

        # 3. Разделительная вертикальная линия по центру
        sep_pen = QPen(QColor(core_color.red(), core_color.green(), core_color.blue(), 200), 1.2)
        painter.setPen(sep_pen)
        painter.drawLine(QPointF(center.x(), center.y() - radius), QPointF(center.x(), center.y() + radius))

        # Ободок кружка
        rim_pen = QPen(core_color, 1.4)
        painter.setPen(rim_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(center, radius, radius)

    def _draw_creation_stem_to_input(
        self,
        painter: QPainter,
        c_seg: QPointF,
        glow_color: QColor,
        core_color: QColor,
        night: bool,
    ) -> None:
        """Отрисовка веточки вниз к полю ввода и разветвления к игрокам."""
        pts = [
            QPointF(c_seg.x(), c_seg.y() + 16.0),
            QPointF(c_seg.x(), c_seg.y() + 32.0),
            QPointF(c_seg.x(), 168.0),
        ]
        self._draw_volumetric_branch(painter, pts, 2.6, 1.4, night)

        # Если перешли к выбору игроков — рисуем ветвь вправо и вниз к списку участников
        if self._create_step == "players":
            btn_right_edge = QPointF(self.flow_title_input.x() + self.flow_title_input.width(), 184.0)
            self._draw_creation_players_list(painter, btn_right_edge, glow_color, core_color, night)

    def _draw_creation_players_list(
        self,
        painter: QPainter,
        start_pt: QPointF,
        glow_color: QColor,
        core_color: QColor,
        night: bool,
    ) -> None:
        """Отрисовка списка игроков квеста с аватарками и кнопкой подтверждения для беседы."""
        corner_bend = QPointF(420.0, 202.0)
        players = self._quest_players_cache
        count = max(1, len(players))
        y_last_p = 232.0 + (count - 1) * 36.0
        y_bottom = y_last_p + 36.0

        pts_curve: List[QPointF] = []
        for i in range(13):
            t = i / 12.0
            p0 = QPointF(start_pt.x() - 2.0, start_pt.y())
            p1 = QPointF(corner_bend.x() - 10.0, start_pt.y())
            p2 = corner_bend
            x = (1 - t) ** 2 * p0.x() + 2 * (1 - t) * t * p1.x() + t ** 2 * p2.x()
            y = (1 - t) ** 2 * p0.y() + 2 * (1 - t) * t * p1.y() + t ** 2 * p2.y()
            pts_curve.append(QPointF(x, y))

        v_steps = max(6, count * 5)
        for i in range(1, v_steps + 1):
            t = i / v_steps
            pts_curve.append(QPointF(corner_bend.x(), corner_bend.y() + (y_last_p - corner_bend.y()) * t))

        # Плавное утоньшение кончика ветви игроков
        tail_steps = 10
        for i in range(1, tail_steps + 1):
            u = i / tail_steps
            y = y_last_p + 36.0 * u
            x = corner_bend.x() + 2.0 * math.sin(u * math.pi)
            pts_curve.append(QPointF(x, y))

        self._draw_volumetric_branch(painter, pts_curve, 2.6, 0.5, night)

        # Если создаётся Беседа — в месте изгиба рисуем окружность с символом ✔
        if self._create_flow_kind == FlowKind.CONVERSATION:
            is_conf_hov = self._hovered_create_confirm_btn
            if is_conf_hov:
                grad = QRadialGradient(corner_bend, 18.0)
                grad.setColorAt(0.0, QColor(glow_color.red(), glow_color.green(), glow_color.blue(), 190))
                grad.setColorAt(1.0, QColor(glow_color.red(), glow_color.green(), glow_color.blue(), 0))
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(grad))
                painter.drawEllipse(corner_bend, 18.0, 18.0)

            painter.setPen(QPen(core_color, 1.5 if is_conf_hov else 1.2))
            painter.setBrush(QColor(34, 197, 94, 60) if is_conf_hov else QColor(24, 32, 54, 230))
            painter.drawEllipse(corner_bend, 12.0, 12.0)

            font = QFont("Georgia", 11)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(core_color)
            painter.drawText(QRectF(corner_bend.x() - 12.0, corner_bend.y() - 12.0, 24.0, 24.0), Qt.AlignCenter, "✔")

        # Отрисовка списка игроков
        font = QFont("Georgia", 10.5)
        painter.setFont(font)

        for idx, player in enumerate(players):
            y_p = 232.0 + idx * 36.0
            p_start = QPointF(corner_bend.x(), y_p)
            p_end = QPointF(corner_bend.x() + 16.0, y_p)

            is_sel = (player.pubkey in self._selected_participants)
            is_hov = (self._hovered_player_item == player)
            active = is_sel or (self._create_flow_kind == FlowKind.DIALOGUE and is_hov)

            # Изогнутая веточка к игроку
            p_start = QPointF(corner_bend.x(), y_p)
            p_end = QPointF(corner_bend.x() + 16.0, y_p)
            tw_pts = [
                p_start,
                QPointF(corner_bend.x() + 5.0, y_p + 1.2),
                QPointF(corner_bend.x() + 11.0, y_p - 1.2),
                p_end,
            ]
            self._draw_volumetric_branch(painter, tw_pts, 1.8, 0.8, night)

            # Аватарка игрока (24px)
            c_avatar = QPointF(corner_bend.x() + 28.0, y_p)
            r_av = 10.0

            pix = self._get_player_avatar_pixmap(player)
            if pix and not pix.isNull():
                clip_path = QPainterPath()
                clip_path.addEllipse(c_avatar, r_av, r_av)
                painter.save()
                painter.setClipPath(clip_path)
                target_rect = QRectF(c_avatar.x() - r_av, c_avatar.y() - r_av, 2 * r_av, 2 * r_av)
                painter.drawPixmap(target_rect.toRect(), pix)
                painter.restore()

            av_pen = QPen(core_color if active else QColor(255, 255, 255, 120), 1.5 if active else 1.0)
            painter.setPen(av_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(c_avatar, r_av, r_av)

            # Имя игрока (туманнее при неактивном состоянии, ярче при выборе)
            name_rect = QRectF(corner_bend.x() + 44.0, y_p - 11.0, 130.0, 22.0)
            if active:
                text_color = QColor(254, 240, 138, 255)
            else:
                text_color = QColor(226, 232, 240, 140)

            painter.setPen(text_color)
            painter.drawText(name_rect, Qt.AlignLeft | Qt.AlignVCenter, player.username)

    def _get_player_avatar_pixmap(self, player: Player) -> QPixmap:
        """Кэширование круглой аватарки игрока для HUD."""
        if player.pubkey in self._player_avatar_cache:
            return self._player_avatar_cache[player.pubkey]

        raw_bytes = self.node.get_player_avatar_bytes(player.pubkey)
        if raw_bytes:
            pix = make_circular_pixmap(raw_bytes, 48)
        else:
            png = generate_default_avatar_png(player.username, size=48)
            pix = make_circular_pixmap(png, 48)

        self._player_avatar_cache[player.pubkey] = pix
        return pix

    # -------------------------------------------------------------
    # Отрисовка Живого Потока капель (без окон, прямо на полотне мира)
    # -------------------------------------------------------------

    def _sample_cubic_bezier(
        self, p0: QPointF, p1: QPointF, p2: QPointF, p3: QPointF, steps: int = 35
    ) -> list[QPointF]:
        """Дискретизация кубической кривой Безье с непрерывной кривизной без изломов."""
        pts: list[QPointF] = []
        for i in range(steps + 1):
            t = i / steps
            u = 1.0 - t
            u2 = u * u
            u3 = u2 * u
            t2 = t * t
            t3 = t2 * t
            x = u3 * p0.x() + 3.0 * u2 * t * p1.x() + 3.0 * u * t2 * p2.x() + t3 * p3.x()
            y = u3 * p0.y() + 3.0 * u2 * t * p1.y() + 3.0 * u * t2 * p2.y() + t3 * p3.y()
            pts.append(QPointF(x, y))
        return pts

    def _draw_living_flow_stream(
        self,
        painter: QPainter,
        glow_color: QColor,
        core_color: QColor,
        night: bool,
    ) -> None:
        """
        Отрисовка живого потока капель прямо на полотне мира:
        - от квеста вправо органическая ветвь до сакральной двойной спирали;
        - от спирали стебель вниз к развилке;
        - плавные криволинейные ветви Безье без острых углов:
          левая ветвь с каплями игрока и кнопкой 💧,
          правая ветвь с каплями собеседников;
        - капли и поле ввода растут ВНУТРЬ потока.
        """
        c_quest = self.spiral_center
        c_spiral = self._flow_spiral_center
        r_spiral = self._flow_spiral_radius

        # 1. Органическая ветвь вправо от выбранного квеста до двойной спирали
        p_q_right = QPointF(c_quest.x() + self.spiral_radius, c_quest.y())
        p_sp_left = QPointF(c_spiral.x() - r_spiral, c_spiral.y())
        dx = p_sp_left.x() - p_q_right.x()
        pts_bridge = self._sample_cubic_bezier(
            p_q_right,
            QPointF(p_q_right.x() + dx * 0.35, p_q_right.y() + 9.0),
            QPointF(p_q_right.x() + dx * 0.70, p_q_right.y() - 7.0),
            p_sp_left,
            steps=35,
        )
        self._draw_volumetric_branch(painter, pts_bridge, 3.6, 2.4, night)

        # 2. Сакральная двойная спираль потока
        self._draw_flow_double_spiral(
            painter, c_spiral, r_spiral, glow_color, core_color, self._flow_spiral_hovered
        )

        # Подсказка с заглавием потока при наведении на спираль
        if self._flow_spiral_hovered and self._active_flow:
            self._draw_flow_spiral_tooltip(painter, c_spiral)

        # 3. Стебель от нижнего полюса спирали вниз к развилке
        p_sp_bottom = QPointF(c_spiral.x(), c_spiral.y() + r_spiral)
        p_fork = QPointF(c_spiral.x(), 102.0)
        stem_pts = [
            p_sp_bottom,
            QPointF(c_spiral.x(), 97.0),
            p_fork,
        ]
        self._draw_volumetric_branch(painter, stem_pts, 3.4, 3.2, night)

        # 4. Расчет положения левой и правой живых ветвей
        c_btn = self._get_flow_drop_btn_center()
        y_btn = c_btn.y()

        # Построение живой органической левой ветви (без единой прямой линии!)
        y_left_tail = y_btn + 32.0
        n_left = max(32, int((y_left_tail - 102.0) / 5.0))
        left_pts = [
            self._flow_left_trunk_point(102.0 + (y_left_tail - 102.0) * (i / n_left))
            for i in range(n_left + 1)
        ]
        # Постепенное природное утоньшение: 3.2px у развилки -> 0.7px на хвостике
        self._draw_volumetric_branch(painter, left_pts, 3.2, 0.7, night)

        # Круглая кнопка-капля 💧 на конце левой ветви (поверх живого ствола перед хвостиком)
        self._draw_flow_drop_button(painter, c_btn, glow_color, core_color, night)

        # Расчет длины правой ветви (собеседники)
        y_cursor = 260.0 + self._flow_scroll_y
        y_right_last = 250.0 + self._flow_scroll_y
        for drop in self._active_flow_drops:
            my_pk = self.node.identity.pubkey if hasattr(self.node, 'identity') and self.node.identity else ''
            if my_pk and drop.author_pubkey:
                is_mine = (drop.author_pubkey == my_pk)
            elif drop.author_name:
                is_mine = (drop.author_name == self.node.username)
            else:
                is_mine = True
            text_lines = max(1, len(drop.content) // 26 + 1)
            h_drop = max(38.0, text_lines * 18.0 + 16.0)
            if not is_mine:
                y_pos = max(y_cursor, y_right_last + 26.0)
                y_right_last = y_pos + h_drop
                y_cursor = max(y_cursor, y_pos) + h_drop + 14.0
            else:
                y_pos = max(y_cursor, y_right_last + 26.0)
                y_cursor = max(y_cursor, y_pos) + h_drop + 14.0

        y_right_tip = max(y_btn, y_right_last + 40.0)

        # Построение живой органической правой ветви (без единой прямой линии!)
        y_right_tail = y_right_tip + 36.0
        n_right = max(32, int((y_right_tail - 102.0) / 5.0))
        right_pts = [
            self._flow_right_trunk_point(102.0 + (y_right_tail - 102.0) * (i / n_right))
            for i in range(n_right + 1)
        ]
        # Постепенное природное утоньшение: 3.2px у развилки -> 0.5px на кончике
        self._draw_volumetric_branch(painter, right_pts, 3.2, 0.5, night)

        # 5. Отрисовка нанизанных капель ВНУТРЬ потока (исчезают у поворота ветвей y=240)
        y_turn = 240.0
        clip_rect = QRectF(0.0, y_turn, float(self.width()), float(self.height() - y_turn))

        y_c = 260.0 + self._flow_scroll_y
        y_l_acc = 250.0 + self._flow_scroll_y
        y_r_acc = 250.0 + self._flow_scroll_y

        for drop in self._active_flow_drops:
            my_pk = self.node.identity.pubkey if hasattr(self.node, 'identity') and self.node.identity else ''
            if my_pk and drop.author_pubkey:
                is_mine = (drop.author_pubkey == my_pk)
            elif drop.author_name:
                is_mine = (drop.author_name == self.node.username)
            else:
                is_mine = True
            text_lines = max(1, len(drop.content) // 26 + 1)
            h_drop = max(38.0, text_lines * 18.0 + 16.0)

            if is_mine:
                y_pos = max(y_c, y_l_acc + 26.0)
                y_node = y_pos + 12.0
                y_l_acc = y_pos + h_drop
                y_c = max(y_c, y_pos) + h_drop + 14.0

                # Если капля ушла выше поворота ветвей вниз — она полностью исчезает
                if y_node < y_turn:
                    continue

                pt_node = self._flow_left_trunk_point(y_node)
                fade = min(1.0, max(0.0, (y_node - y_turn) / 32.0))

                painter.save()
                painter.setClipRect(clip_rect)
                painter.setOpacity(fade)
                self._draw_strung_user_drop(
                    painter, pt_node, drop, h_drop, glow_color, core_color
                )
                painter.restore()
            else:
                y_pos = max(y_c, y_r_acc + 26.0)
                y_node = y_pos + 12.0
                y_r_acc = y_pos + h_drop
                y_c = max(y_c, y_pos) + h_drop + 14.0

                # Если капля ушла выше поворота ветвей вниз — она полностью исчезает
                if y_node < y_turn:
                    continue

                pt_node = self._flow_right_trunk_point(y_node)
                fade = min(1.0, max(0.0, (y_node - y_turn) / 32.0))

                painter.save()
                painter.setClipRect(clip_rect)
                painter.setOpacity(fade)
                self._draw_strung_partner_drop(
                    painter, pt_node, drop, h_drop, glow_color, core_color
                )
                painter.restore()

    def _draw_flow_double_spiral(
        self,
        painter: QPainter,
        center: QPointF,
        radius: float,
        glow_color: QColor,
        core_color: QColor,
        hovered: bool,
    ) -> None:
        """Отрисовка сакральной двойной спирали потока по каноническому образцу."""
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        # 1. Радиальное свечение вокруг медальона
        glow_spread = 10.0 if hovered else 6.5
        r_outer = radius + glow_spread
        grad = QRadialGradient(center, r_outer)
        peak_alpha = 210 if hovered else 130
        grad.setColorAt(0.0, QColor(glow_color.red(), glow_color.green(), glow_color.blue(), peak_alpha))
        grad.setColorAt(0.65, QColor(glow_color.red(), glow_color.green(), glow_color.blue(), int(peak_alpha * 0.45)))
        grad.setColorAt(1.0, QColor(glow_color.red(), glow_color.green(), glow_color.blue(), 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawEllipse(center, r_outer, r_outer)

        # 2. Темная стеклянная подложка медальона
        painter.setBrush(QColor(14, 20, 36, 235))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(center, radius, radius)

        # 3. Сакральная двойная спираль из изображения
        pix = self.get_double_spiral_pixmap(size=int(radius * 2.0))
        if pix and not pix.isNull():
            target_rect = QRectF(center.x() - radius + 1.0, center.y() - radius + 1.0, (radius - 1.0) * 2.0, (radius - 1.0) * 2.0)
            painter.drawPixmap(target_rect.toRect(), pix)

        # 4. Тонкий золотой ободок медальона
        rim_pen = QPen(
            QColor(core_color.red(), core_color.green(), core_color.blue(), 230 if hovered else 170),
            1.4 if hovered else 1.1,
        )
        painter.setPen(rim_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(center, radius, radius)

        painter.restore()

    def _draw_flow_spiral_tooltip(self, painter: QPainter, center: QPointF) -> None:
        """Отрисовка всплывающей подсказки с заглавием потока над двойной спиралью."""
        if not self._active_flow:
            return
        painter.save()
        font = QFont("Georgia", 11)
        font.setBold(True)
        painter.setFont(font)
        fm = QFontMetrics(font)

        title = self._active_flow.title
        text_w = fm.horizontalAdvance(title)
        pill_w = max(110.0, text_w + 24.0)
        pill_rect = QRectF(center.x() - pill_w * 0.5, center.y() - 38.0, pill_w, 24.0)

        painter.setPen(QPen(QColor(254, 240, 138, 200), 1.2))
        painter.setBrush(QColor(14, 20, 36, 235))
        painter.drawRoundedRect(pill_rect, 12.0, 12.0)

        painter.setPen(QColor(254, 240, 138, 255))
        painter.drawText(pill_rect, Qt.AlignCenter, title)
        painter.restore()

    def _draw_flow_drop_button(
        self,
        painter: QPainter,
        center: QPointF,
        glow_color: QColor,
        core_color: QColor,
        night: bool,
    ) -> None:
        """Отрисовка круглой кнопки с символом капли 💧 на конце левой ветви."""
        painter.save()
        radius = 13.5
        hovered = self._flow_drop_btn_hovered

        if hovered or self._flow_input_active:
            grad = QRadialGradient(center, radius + 8.0)
            grad.setColorAt(0.0, QColor(glow_color.red(), glow_color.green(), glow_color.blue(), 200))
            grad.setColorAt(0.7, QColor(glow_color.red(), glow_color.green(), glow_color.blue(), 60))
            grad.setColorAt(1.0, QColor(glow_color.red(), glow_color.green(), glow_color.blue(), 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(grad))
            painter.drawEllipse(center, radius + 8.0, radius + 8.0)

        bg_grad = QLinearGradient(center.x() - radius, center.y() - radius, center.x() + radius, center.y() + radius)
        if hovered or self._flow_input_active:
            bg_grad.setColorAt(0.0, QColor(48, 64, 98, 255))
            bg_grad.setColorAt(1.0, QColor(16, 24, 42, 255))
            border_pen = QPen(QColor(254, 240, 138, 245), 1.4)
        else:
            bg_grad.setColorAt(0.0, QColor(32, 42, 68, 240))
            bg_grad.setColorAt(1.0, QColor(14, 20, 36, 240))
            border_pen = QPen(QColor(254, 240, 138, 160), 1.1)

        painter.setBrush(QBrush(bg_grad))
        painter.setPen(border_pen)
        painter.drawEllipse(center, radius, radius)

        # Сакральный символ капли (векторный Bezier-контур)
        drop_path = QPainterPath()
        p_top = QPointF(center.x(), center.y() - 6.5)
        p_bot = QPointF(center.x(), center.y() + 6.0)
        drop_path.moveTo(p_top)
        drop_path.cubicTo(
            center.x() + 6.0, center.y() - 1.0,
            center.x() + 5.5, p_bot.y(),
            p_bot.x(), p_bot.y(),
        )
        drop_path.cubicTo(
            center.x() - 5.5, p_bot.y(),
            center.x() - 6.0, center.y() - 1.0,
            p_top.x(), p_top.y(),
        )

        drop_grad = QLinearGradient(p_top.x(), p_top.y(), p_bot.x(), p_bot.y())
        drop_grad.setColorAt(0.0, QColor(56, 189, 248, 255))
        drop_grad.setColorAt(1.0, QColor(254, 240, 138, 255))

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(drop_grad))
        painter.drawPath(drop_path)
        painter.restore()

    def _draw_strung_user_drop(
        self,
        painter: QPainter,
        node_pt: QPointF,
        drop: FlowDrop,
        h_drop: float,
        glow_color: QColor,
        core_color: QColor,
    ) -> None:
        """Отрисовка капли игрока, нанизанной на левую ветвь."""
        painter.save()
        night = self.is_night()
        r_av = 12.0
        c_av = node_pt

        # Цвета в ладу с суточным циклом Портала (днем - золотистые, ночью - лунные)
        text_color = QColor(254, 240, 138, 245) if not night else QColor(241, 245, 249, 240)
        time_color = QColor(212, 165, 36, 200) if not night else QColor(148, 163, 184, 180)
        bud_color = QColor(254, 240, 138, 230) if not night else QColor(226, 232, 240, 220)
        rim_color = QColor(254, 240, 138, 220) if not night else QColor(226, 232, 240, 210)

        # Радиальное свечение вокруг аватарки
        painter.setPen(Qt.NoPen)
        grad = QRadialGradient(c_av, r_av + 6.0)
        if not night:
            grad.setColorAt(0.0, QColor(254, 240, 138, 220))
            grad.setColorAt(0.65, QColor(234, 179, 8, 80))
            grad.setColorAt(1.0, QColor(234, 179, 8, 0))
        else:
            grad.setColorAt(0.0, QColor(226, 232, 240, 200))
            grad.setColorAt(0.65, QColor(148, 163, 184, 70))
            grad.setColorAt(1.0, QColor(148, 163, 184, 0))
        painter.setBrush(QBrush(grad))
        painter.drawEllipse(c_av, r_av + 6.0, r_av + 6.0)

        # Подложка аватарки игрока
        painter.setBrush(QColor(18, 24, 40, 245))
        painter.setPen(QPen(rim_color, 1.3))
        painter.drawEllipse(c_av, r_av, r_av)

        # Отрисовка аватарки игрока/Сига
        author_pk = drop.author_pubkey or (self.node.identity.pubkey if hasattr(self.node, 'identity') and self.node.identity else '')
        author_name = drop.author_name or self.node.username or "Сиг"
        pix = None
        if author_pk and author_pk in self._player_avatar_cache:
            pix = self._player_avatar_cache[author_pk]
        elif author_pk:
            raw_bytes = self.node.get_player_avatar_bytes(author_pk)
            if raw_bytes:
                pix = make_circular_pixmap(raw_bytes, 48)
            else:
                png = generate_default_avatar_png(author_name, size=48)
                pix = make_circular_pixmap(png, 48)
            self._player_avatar_cache[author_pk] = pix
        else:
            png = generate_default_avatar_png(author_name, size=48)
            pix = make_circular_pixmap(png, 48)

        if pix and not pix.isNull():
            clip_path = QPainterPath()
            clip_path.addEllipse(c_av, r_av, r_av)
            painter.save()
            painter.setClipPath(clip_path)
            target_rect = QRectF(c_av.x() - r_av, c_av.y() - r_av, 2.0 * r_av, 2.0 * r_av)
            painter.drawPixmap(target_rect.toRect(), pix)
            painter.restore()
        else:
            font_initial = QFont("Georgia", 9, QFont.Bold)
            painter.setFont(font_initial)
            painter.setPen(rim_color)
            name_char = (author_name or "С")[0].upper()
            painter.drawText(QRectF(c_av.x() - r_av, c_av.y() - r_av, 2 * r_av, 2 * r_av), Qt.AlignCenter, name_char)

        # Тонкий ободок поверх
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(rim_color, 1.2))
        painter.drawEllipse(c_av, r_av, r_av)

        # Живая изогнутая веточка от аватарки ВНУТРЬ к тексту (с плавным утоньшением)
        p_start = QPointF(c_av.x() + r_av, c_av.y())
        p_end = QPointF(p_start.x() + 22.0, p_start.y() + 2.0)
        twig_pts = self._sample_cubic_bezier(
            p_start,
            QPointF(p_start.x() + 7.0, p_start.y() + 5.0),
            QPointF(p_start.x() + 15.0, p_start.y() - 3.0),
            p_end,
            steps=18,
        )
        self._draw_volumetric_branch(painter, twig_pts, 2.2, 0.8, night)

        # Светящаяся почка на конце веточки у текста капли
        painter.setPen(Qt.NoPen)
        painter.setBrush(bud_color)
        painter.drawEllipse(p_end, 2.2, 2.2)

        # Дыхание капли мысли (менее прозрачный бархатистый фон для чистоты чтения)
        bubble_rect = QRectF(p_end.x() + 4.0, node_pt.y() - 10.0, 215.0, h_drop)
        painter.setPen(Qt.NoPen)
        bg_grad = QLinearGradient(bubble_rect.left(), bubble_rect.top(), bubble_rect.right(), bubble_rect.bottom())
        if not night:
            bg_grad.setColorAt(0.0, QColor(20, 28, 48, 185))
            bg_grad.setColorAt(1.0, QColor(12, 18, 32, 205))
        else:
            bg_grad.setColorAt(0.0, QColor(14, 20, 36, 185))
            bg_grad.setColorAt(1.0, QColor(8, 12, 22, 205))
        painter.setBrush(QBrush(bg_grad))
        painter.drawRoundedRect(bubble_rect, 10.0, 10.0)

        font = QFont("Georgia", 11)
        painter.setFont(font)
        painter.setPen(text_color)
        text_rect = QRectF(bubble_rect.left() + 8.0, bubble_rect.top() + 6.0, bubble_rect.width() - 16.0, bubble_rect.height() - 20.0)
        painter.drawText(text_rect, Qt.AlignLeft | Qt.TextWordWrap, drop.content)

        time_str = ""
        try:
            time_str = datetime.fromisoformat(drop.created_at).strftime("%H:%M")
        except Exception:
            pass
        if time_str:
            font_time = QFont("sans-serif", 9)
            painter.setFont(font_time)
            painter.setPen(time_color)
            time_rect = QRectF(bubble_rect.left() + 8.0, bubble_rect.bottom() - 16.0, bubble_rect.width() - 16.0, 14.0)
            painter.drawText(time_rect, Qt.AlignRight | Qt.AlignVCenter, time_str)

        painter.restore()

    def _draw_strung_partner_drop(
        self,
        painter: QPainter,
        node_pt: QPointF,
        drop: FlowDrop,
        h_drop: float,
        glow_color: QColor,
        core_color: QColor,
    ) -> None:
        """Отрисовка капли собеседника/Эйры, нанизанной на правую ветвь."""
        painter.save()
        night = self.is_night()
        r_av = 12.0
        c_av = node_pt

        # Цвета в ладу с суточным циклом Портала (днем - золотистые, ночью - лунные)
        text_color = QColor(254, 240, 138, 245) if not night else QColor(241, 245, 249, 240)
        time_color = QColor(212, 165, 36, 200) if not night else QColor(148, 163, 184, 180)
        bud_color = QColor(254, 240, 138, 230) if not night else QColor(226, 232, 240, 220)
        rim_color = QColor(254, 240, 138, 220) if not night else QColor(226, 232, 240, 210)

        # Радиальное свечение вокруг аватарки
        painter.setPen(Qt.NoPen)
        grad = QRadialGradient(c_av, r_av + 6.0)
        if not night:
            grad.setColorAt(0.0, QColor(254, 240, 138, 220))
            grad.setColorAt(0.65, QColor(234, 179, 8, 80))
            grad.setColorAt(1.0, QColor(234, 179, 8, 0))
        else:
            grad.setColorAt(0.0, QColor(226, 232, 240, 200))
            grad.setColorAt(0.65, QColor(148, 163, 184, 70))
            grad.setColorAt(1.0, QColor(148, 163, 184, 0))
        painter.setBrush(QBrush(grad))
        painter.drawEllipse(c_av, r_av + 6.0, r_av + 6.0)

        painter.setBrush(QColor(18, 24, 40, 245))
        painter.setPen(QPen(rim_color, 1.2))
        painter.drawEllipse(c_av, r_av, r_av)

        author_pk = drop.author_pubkey or ""
        author_name = drop.author_name or "Эйра"
        pix = None
        if author_pk and author_pk in self._player_avatar_cache:
            pix = self._player_avatar_cache[author_pk]
        elif author_pk:
            raw_bytes = self.node.get_player_avatar_bytes(author_pk)
            if raw_bytes:
                pix = make_circular_pixmap(raw_bytes, 48)
            else:
                png = generate_default_avatar_png(author_name, size=48)
                pix = make_circular_pixmap(png, 48)
            self._player_avatar_cache[author_pk] = pix
        elif author_name != "Эйра":
            png = generate_default_avatar_png(author_name, size=48)
            pix = make_circular_pixmap(png, 48)

        if pix and not pix.isNull():
            clip_path = QPainterPath()
            clip_path.addEllipse(c_av, r_av, r_av)
            painter.save()
            painter.setClipPath(clip_path)
            target_rect = QRectF(c_av.x() - r_av, c_av.y() - r_av, 2.0 * r_av, 2.0 * r_av)
            painter.drawPixmap(target_rect.toRect(), pix)
            painter.restore()
        elif author_name == "Эйра":
            pen_eira = QPen(rim_color, 1.3, Qt.SolidLine, Qt.RoundCap)
            painter.setPen(pen_eira)
            painter.drawArc(QRectF(c_av.x() - 4.5, c_av.y() - 5.5, 6.0, 11.0), int(-70 * 16), int(140 * 16))
            painter.drawArc(QRectF(c_av.x() - 1.5, c_av.y() - 5.5, 6.0, 11.0), int(110 * 16), int(140 * 16))
        else:
            font_initial = QFont("Georgia", 9, QFont.Bold)
            painter.setFont(font_initial)
            painter.setPen(rim_color)
            name_char = (author_name or "И")[0].upper()
            painter.drawText(QRectF(c_av.x() - r_av, c_av.y() - r_av, 2 * r_av, 2 * r_av), Qt.AlignCenter, name_char)

        # Ободок поверх аватарки
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(rim_color, 1.2))
        painter.drawEllipse(c_av, r_av, r_av)

        # Живая изогнутая веточка от аватарки ВНУТРЬ к тексту (с плавным утоньшением)
        p_start = QPointF(c_av.x() - r_av, c_av.y())
        p_end = QPointF(p_start.x() - 22.0, p_start.y() + 2.0)
        twig_pts = self._sample_cubic_bezier(
            p_start,
            QPointF(p_start.x() - 7.0, p_start.y() + 5.0),
            QPointF(p_start.x() - 15.0, p_start.y() - 3.0),
            p_end,
            steps=18,
        )
        self._draw_volumetric_branch(painter, twig_pts, 2.2, 0.8, night)

        # Светящаяся почка на конце веточки у текста капли
        painter.setPen(Qt.NoPen)
        painter.setBrush(bud_color)
        painter.drawEllipse(p_end, 2.2, 2.2)

        # Дыхание капли мысли (менее прозрачный бархатистый фон для чистоты чтения)
        bubble_rect = QRectF(p_end.x() - 215.0 - 4.0, node_pt.y() - 10.0, 215.0, h_drop)
        painter.setPen(Qt.NoPen)
        bg_grad = QLinearGradient(bubble_rect.left(), bubble_rect.top(), bubble_rect.right(), bubble_rect.bottom())
        if not night:
            bg_grad.setColorAt(0.0, QColor(20, 28, 48, 185))
            bg_grad.setColorAt(1.0, QColor(12, 18, 32, 205))
        else:
            bg_grad.setColorAt(0.0, QColor(14, 20, 36, 185))
            bg_grad.setColorAt(1.0, QColor(8, 12, 22, 205))
        painter.setBrush(QBrush(bg_grad))
        painter.drawRoundedRect(bubble_rect, 10.0, 10.0)

        font = QFont("Georgia", 11)
        painter.setFont(font)
        painter.setPen(text_color)
        text_rect = QRectF(bubble_rect.left() + 8.0, bubble_rect.top() + 6.0, bubble_rect.width() - 16.0, bubble_rect.height() - 20.0)
        painter.drawText(text_rect, Qt.AlignLeft | Qt.TextWordWrap, drop.content)

        time_str = ""
        try:
            time_str = datetime.fromisoformat(drop.created_at).strftime("%H:%M")
        except Exception:
            pass
        if time_str:
            font_time = QFont("sans-serif", 9)
            painter.setFont(font_time)
            painter.setPen(time_color)
            time_rect = QRectF(bubble_rect.left() + 8.0, bubble_rect.bottom() - 16.0, bubble_rect.width() - 16.0, 14.0)
            painter.drawText(time_rect, Qt.AlignRight | Qt.AlignVCenter, time_str)

        painter.restore()
