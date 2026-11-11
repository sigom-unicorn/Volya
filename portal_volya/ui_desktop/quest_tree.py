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

        # Кэш аватарок квестов
        self._quest_pixmaps: Dict[str, QPixmap] = {}

        # Выбран ли квест (до первого выбора логотип не виден, после выбора дуга, нить и выбранный квест видны постоянно)
        self.has_selected_quest: bool = False
        self.active_quest_id: str = "quest-volya-root"
        self.active_quest_title: str = "Воля"
        self._active_quest_pixmap: Optional[QPixmap] = self.get_volya_logo_pixmap(size=128)

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
