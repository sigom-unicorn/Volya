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
)
from PySide6.QtWidgets import QWidget

from portal_volya.core.models import Quest, TreeTier
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


class QuestTreeHUD(QWidget):
    """
    Парящий оверлей навигатора Древа Квестов.
    Располагается поверх живого полотна Баньяна и не перекрывает клики по пустому миру.
    """

    quest_selected = Signal(str)  # quest_id

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

        # Выбран ли квест (до первого выбора спираль не видна, после выбора дуга, нить и выбранный квест видны постоянно)
        self.has_selected_quest: bool = False
        self.active_quest_id: str = "quest-volya-root"
        self.active_quest_title: str = "Воля"
        self._active_quest_pixmap: Optional[QPixmap] = None

        # Кэш аватарок квестов
        self._quest_pixmaps: Dict[str, QPixmap] = {}

        # Список узлов открытого дерева
        self.tree_nodes: List[QuestTreeNode] = []

        # Состояния интерактива
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

        # Таймер плавной анимации (60 FPS)
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._on_anim_tick)
        self._anim_timer.start(16)

        # Таймер закрытия при уходе курсора
        self._auto_close_timer = QTimer(self)
        self._auto_close_timer.setSingleShot(True)
        self._auto_close_timer.timeout.connect(self._on_auto_close_timeout)

        self.refresh_quests()

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

    def get_quest_pixmap(self, quest: Quest, size: int = 128) -> QPixmap:
        """Получение или процедурная генерация священного аватара квеста."""
        if quest.id in self._quest_pixmaps:
            return self._quest_pixmaps[quest.id]

        # Проверяем, есть ли сохраненный аватар в RocksDB
        avatar_bytes = None
        try:
            avatar_bytes = self.node.dag_store.get_blob(quest.id)
        except Exception:
            avatar_bytes = None

        if not avatar_bytes:
            # Генерируем уникальный узор из 9 золотых нитей по сиду квеста
            avatar_bytes = generate_default_avatar_png(quest.title, f"{quest.id}:{quest.title}", size=size)

        pix = make_circular_pixmap(avatar_bytes, size=size)
        self._quest_pixmaps[quest.id] = pix
        return pix

    def set_active_quest(self, quest_id: str) -> None:
        """Установка активного выбранного квеста."""
        self.active_quest_id = quest_id
        if quest_id == "quest-volya-root":
            self.active_quest_title = "Воля"
            self._active_quest_pixmap = None
        else:
            q = self.node.dag_store.get_quest(quest_id)
            if q:
                self.active_quest_title = q.title
                self._active_quest_pixmap = self.get_quest_pixmap(q, size=128)
            else:
                self.active_quest_title = "Воля"
                self._active_quest_pixmap = None
        self.quest_selected.emit(quest_id)
        self.update()

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

        # Если событие не в интерактивной зоне — пропускаем родителю
        if not (self._arc_hovered or self._spiral_hovered or self._hovered_bead or self._tree_open):
            event.ignore()
        else:
            super().mouseMoveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.LeftButton:
            event.ignore()
            return

        pt = event.position()

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

        # По щелчку мыши ничего пока не должно происходить у выбранного квеста при закрытом дереве
        event.ignore()

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
        # Если квест выбран — видна постоянно. До выбора — при наведении или открытии
        if self.has_selected_quest or self._arc_visible or self._avatar_hovered or self._arc_hovered or self._tree_open:
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

        painter.end()

    def _draw_avatar_arc(self, painter: QPainter, glow_color: QColor, core_color: QColor) -> None:
        """Отрисовка светящейся дуги справа от аватарки игрока."""
        arc_box = QRectF(
            self.avatar_center.x() - self.arc_radius,
            self.avatar_center.y() - self.arc_radius,
            2 * self.arc_radius,
            2 * self.arc_radius,
        )
        start_angle = int(-45 * 16)
        span_angle = int(90 * 16)

        alpha = 240 if self._arc_hovered else (150 if self._avatar_hovered else 90)

        # Внешнее свечение
        glow_pen = QPen(QColor(glow_color.red(), glow_color.green(), glow_color.blue(), int(alpha * 0.45)), 4.5)
        glow_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(glow_pen)
        painter.drawArc(arc_box, start_angle, span_angle)

        # Ядро дуги
        core_pen = QPen(QColor(core_color.red(), core_color.green(), core_color.blue(), alpha), 1.8)
        core_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(core_pen)
        painter.drawArc(arc_box, start_angle, span_angle)

    def _draw_bridge_thread(self, painter: QPainter, glow_color: QColor, core_color: QColor) -> None:
        """Протягивание нити от центра дуги к левому входу двойной спирали."""
        p_start = QPointF(self.avatar_center.x() + self.arc_radius, self.avatar_center.y())
        p_target = QPointF(self.spiral_center.x() - self.spiral_radius, self.spiral_center.y())

        # Если квест уже выбран, или идёт анимация перелёта — нить натянута полностью
        if self.has_selected_quest or self._gliding_node or self._pending_selection_node:
            t = 1.0
        else:
            # Прогресс протягивания первой фазы (0.0 -> 0.22)
            t = min(1.0, self._unfold_progress / 0.22) if self._unfold_progress > 0 else 0.0
            if self._arc_hovered and t < 0.2:
                t = 0.2

        cur_end = QPointF(p_start.x() + (p_target.x() - p_start.x()) * t, p_start.y())

        glow_pen = QPen(QColor(glow_color.red(), glow_color.green(), glow_color.blue(), 70), 3.5)
        glow_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(glow_pen)
        painter.drawLine(p_start, cur_end)

        core_pen = QPen(QColor(core_color.red(), core_color.green(), core_color.blue(), 230), 1.5)
        core_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(core_pen)
        painter.drawLine(p_start, cur_end)

        # Искорка на конце движущейся нити
        if t < 1.0 and t > 0.01:
            painter.setPen(Qt.NoPen)
            painter.setBrush(core_color)
            painter.drawEllipse(cur_end, 2.4, 2.4)

    def _draw_spiral_or_selected_quest(
        self, painter: QPainter, glow_color: QColor, core_color: QColor
    ) -> None:
        """
        Отрисовка двойной спирали (Исток «Воля») или аватарки выбранного квеста.
        На месте спирали (264, 72) диаметром 64px элемент присутствует постоянно после выбора.
        До первого выбора спираль не видна в спокойном состоянии.
        """
        cx = self.spiral_center.x()
        cy = self.spiral_center.y()
        R = self.spiral_radius  # 32px (диаметр 64px)

        # 1. Если дерево закрыто и квест ещё не выбран — спираль не рисуется
        if not self.has_selected_quest and not self._tree_open and self._unfold_progress <= 0.0 and not self._gliding_node:
            return

        # 2. Если выбран квест (не «Воля») и дерево не открыто
        if (
            self.has_selected_quest
            and self.active_quest_id != "quest-volya-root"
            and self._active_quest_pixmap
            and not self._tree_open
            and not self._gliding_node
        ):
            self._draw_bead_disc(
                painter,
                self.spiral_center,
                64.0,
                self._active_quest_pixmap,
                glow_color,
                core_color,
                hovered=self._spiral_hovered,
            )
            return

        # 3. Иначе — рисуется двойная спираль созидания!
        # Фаза отрисовки спирали: unfold_progress 0.20 -> 0.55
        spiral_t = 1.0
        if self._tree_open or self._unfold_progress < 1.0:
            if self._unfold_progress <= 0.20:
                spiral_t = 0.0
            else:
                spiral_t = min(1.0, (self._unfold_progress - 0.20) / 0.35)

        # В спокойном состоянии выбранной «Воли» спираль видна постоянно на 100%
        if not self._tree_open and self.has_selected_quest and self.active_quest_id == "quest-volya-root":
            spiral_t = 1.0

        if spiral_t <= 0.0:
            return

        # 1. Ветвь 1: от входа (cx - R, cy) скручивается в центр (cx, cy)
        a1 = R / (4.0 * math.pi)
        steps = 80
        pts1: List[QPointF] = []
        max_i1 = int(steps * spiral_t)

        for i in range(max_i1 + 1):
            t_frac = i / steps
            th = 4.0 * math.pi * (1.0 - t_frac)
            ang = th + math.pi
            r = a1 * th
            pts1.append(QPointF(cx + r * math.cos(ang), cy + r * math.sin(ang)))

        # 2. Ветвь 2: из центра (cx, cy) раскручивается наружу к нижней точке (cx, cy + R)
        a2 = R / (4.5 * math.pi)
        pts2: List[QPointF] = []
        max_i2 = int(steps * spiral_t)

        for i in range(max_i2 + 1):
            t_frac = i / steps
            th = 4.5 * math.pi * t_frac
            r = a2 * th
            pts2.append(QPointF(cx + r * math.cos(th), cy + r * math.sin(th)))

        # Подсветка спирали при наведении
        halo_alpha = 140 if self._spiral_hovered else 75
        core_alpha = 255 if self._spiral_hovered else 225

        glow_pen = QPen(QColor(glow_color.red(), glow_color.green(), glow_color.blue(), halo_alpha), 3.8)
        glow_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(glow_pen)
        for i in range(len(pts1) - 1):
            painter.drawLine(pts1[i], pts1[i + 1])
        for i in range(len(pts2) - 1):
            painter.drawLine(pts2[i], pts2[i + 1])

        core_pen = QPen(QColor(core_color.red(), core_color.green(), core_color.blue(), core_alpha), 1.6)
        core_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(core_pen)
        for i in range(len(pts1) - 1):
            painter.drawLine(pts1[i], pts1[i + 1])
        for i in range(len(pts2) - 1):
            painter.drawLine(pts2[i], pts2[i + 1])

        # Центральная золотая точка-семя
        painter.setPen(Qt.NoPen)
        painter.setBrush(core_color)
        painter.drawEllipse(self.spiral_center, 2.6, 2.6)

    def _draw_tree_stem_and_branches(
        self, painter: QPainter, stem_color: QColor, glow_color: QColor
    ) -> None:
        """Отрисовка ниспадающего стебля Древа и плавных ветвей к бусинкам."""
        stem_x = self.spiral_center.x()
        stem_top_y = self.spiral_center.y() + self.spiral_radius  # 104.0

        # Стебель заканчивается ровно на самом нижнем ответвлении без лишнего отростка вниз
        stem_nodes = [n for n in self.tree_nodes if abs(n.parent_pos.x() - stem_x) < 1.0]
        if stem_nodes:
            max_y = max(n.parent_pos.y() for n in stem_nodes)
        else:
            max_y = stem_top_y

        # Фаза разворачивания стебля: 0.50 -> 0.75
        stem_t = min(1.0, max(0.0, (self._unfold_progress - 0.50) / 0.25))
        current_stem_bottom = stem_top_y + (max_y - stem_top_y) * stem_t

        # 1. Основной стебель вниз (только до нижнего ответвления)
        if current_stem_bottom > stem_top_y:
            stem_glow = QPen(QColor(glow_color.red(), glow_color.green(), glow_color.blue(), 50), 3.2)
            stem_glow.setCapStyle(Qt.RoundCap)
            stem_core = QPen(stem_color, 1.6)
            stem_core.setCapStyle(Qt.RoundCap)
            painter.setPen(stem_glow)
            painter.drawLine(QPointF(stem_x, stem_top_y), QPointF(stem_x, current_stem_bottom))
            painter.setPen(stem_core)
            painter.drawLine(QPointF(stem_x, stem_top_y), QPointF(stem_x, current_stem_bottom))

        # 2. Ветви к узлам (фаза: 0.70 -> 1.0)
        branch_t = min(1.0, max(0.0, (self._unfold_progress - 0.70) / 0.30))
        if branch_t <= 0.0:
            return

        for node in self.tree_nodes:
            if node == self._gliding_node:
                continue

            p_start = node.parent_pos
            p_end = node.target_pos

            # Плавная кривая ветви
            cur_p = QPointF(
                p_start.x() + (p_end.x() - p_start.x()) * branch_t,
                p_start.y() + (p_end.y() - p_start.y()) * branch_t,
            )

            branch_glow = QPen(QColor(glow_color.red(), glow_color.green(), glow_color.blue(), 45), 3.0)
            branch_core = QPen(stem_color, 1.4)

            painter.setPen(branch_glow)
            painter.drawLine(p_start, cur_p)
            painter.setPen(branch_core)
            painter.drawLine(p_start, cur_p)

            # Узелок в месте отхождения ветви
            painter.setPen(Qt.NoPen)
            painter.setBrush(stem_color)
            painter.drawEllipse(p_start, 2.0, 2.0)

    def _draw_quest_beads(self, painter: QPainter, glow_color: QColor, core_color: QColor) -> None:
        """Отрисовка круглых бусинок квестов со священными аватарками."""
        # Фаза распускания бусинок: 0.80 -> 1.0
        beads_t = min(1.0, max(0.0, (self._unfold_progress - 0.80) / 0.20))
        if beads_t <= 0.0:
            return

        for node in self.tree_nodes:
            if node == self._gliding_node or node == self._pending_selection_node:
                continue

            # Бусинка вырастает из точки ветви
            size = node.current_size * beads_t
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
