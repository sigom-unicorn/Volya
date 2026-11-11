"""
Тесты сакрального интерфейса Древа Квестов (QuestTreeHUD):
- Иерархическое ветвление (Корневые влево, Вольницы вправо, Дома влево-вверх, Другие вправо-вниз).
- Фильтрация по квестам, где играет игрок.
- Наведение на аватарку -> дуга -> протягивание нити и разворачивание спирали.
- Выбор квеста кликом по бусинке (скольжение) и кликом по спирали (выбор «Воли»).
"""

from pathlib import Path
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QMouseEvent

from portal_volya.core.models import Kon, Quest, TreeTier
from portal_volya.node import VolyaNode
from portal_volya.ui_desktop.quest_tree import QuestTreeHUD


def test_quest_tree_layout_and_branching(temp_node_dir, qapp):
    """Проверка геометрического размещения квестов по канону Воли."""
    with VolyaNode(node_dir=temp_node_dir) as node:
        pk = node.identity.pubkey

        # Создаем Вольницу, Дом и Мастерскую
        volnitsa = node.create_quest(
            title="Вольница Ясная",
            kon=Kon(essence="Территориальная община"),
            parent_quest_id="quest-volya-root",
            tier=TreeTier.TRUNK,
            created_at="2026-11-03T12:00:00Z",
            quest_id="quest-volnitsa-yasnaya",
        )
        node.dag_store.assign_player_role(pk, volnitsa.id, "Вольный житель")

        dom = node.create_quest(
            title="Дом Сигома",
            kon=Kon(essence="Родовой дом"),
            parent_quest_id=volnitsa.id,
            tier=TreeTier.BRANCH,
            created_at="2026-11-03T12:05:00Z",
            quest_id="quest-dom-sigoma",
        )
        node.dag_store.assign_player_role(pk, dom.id, "Хозяин дома")

        workshop = node.create_quest(
            title="Гончарная Мастерская",
            kon=Kon(essence="Созидательный труд"),
            parent_quest_id=volnitsa.id,
            tier=TreeTier.BRANCH,
            created_at="2026-11-03T12:10:00Z",
            quest_id="quest-workshop-pottery",
        )
        node.dag_store.assign_player_role(pk, workshop.id, "Мастер")

        hud = QuestTreeHUD(node)
        hud.refresh_quests()

        nodes_by_id = {n.quest.id: n for n in hud.tree_nodes}
        assert "quest-portal-volya" in nodes_by_id
        assert "quest-volnitsa-yasnaya" in nodes_by_id
        assert "quest-dom-sigoma" in nodes_by_id
        assert "quest-workshop-pottery" in nodes_by_id

        portal_node = nodes_by_id["quest-portal-volya"]
        voln_node = nodes_by_id["quest-volnitsa-yasnaya"]
        dom_node = nodes_by_id["quest-dom-sigoma"]
        mast_node = nodes_by_id["quest-workshop-pottery"]

        stem_x = hud.spiral_center.x()

        # 1. Корневой квест — СЛЕВА от нити (x < stem_x)
        assert portal_node.target_pos.x() < stem_x
        assert portal_node.branch_type == "root_child"

        # 2. Вольница — СПРАВА от нити (x > stem_x)
        assert voln_node.target_pos.x() > stem_x
        assert voln_node.branch_type == "trunk"

        # 3. Дом — ВЛЕВО ВВЕРХ от Вольницы (x < voln_x, y < voln_y)
        assert dom_node.target_pos.x() < voln_node.target_pos.x()
        assert dom_node.target_pos.y() < voln_node.target_pos.y()
        assert dom_node.branch_type == "house"

        # 4. Другие квесты — ВПРАВО ВНИЗ от Вольницы (x > voln_x, y > voln_y)
        assert mast_node.target_pos.x() > voln_node.target_pos.x()
        assert mast_node.target_pos.y() > voln_node.target_pos.y()
        assert mast_node.branch_type == "other"


def test_quest_tree_hover_and_arc_unfolding(temp_node_dir, qapp):
    """Проверка появления дуги при наведении на аватарку и разворачивания дерева."""
    with VolyaNode(node_dir=temp_node_dir) as node:
        hud = QuestTreeHUD(node)
        assert hud._arc_visible is False
        assert hud._tree_open is False

        # Наведение на аватарку игрока -> дуга появляется
        hud.on_avatar_hovered(True)
        assert hud._arc_visible is True

        # Уход с аватарки
        hud.on_avatar_hovered(False)

        # Наведение курсора на дугу (справа от аватарки)
        arc_pt = QPointF(hud.avatar_center.x() + hud.arc_radius, hud.avatar_center.y())
        move_ev = QMouseEvent(
            QMouseEvent.MouseMove,
            arc_pt,
            Qt.NoButton,
            Qt.NoButton,
            Qt.NoModifier,
        )
        hud.mouseMoveEvent(move_ev)
        assert hud._arc_hovered is True
        assert hud._tree_open is True
        assert hud._unfold_target == 1.0


def test_quest_selection_and_spiral_click(temp_node_dir, qapp):
    """Проверка выбора квеста: сначала исчезает дерево, затем бусинка перелетает к спирали."""
    with VolyaNode(node_dir=temp_node_dir) as node:
        hud = QuestTreeHUD(node)
        assert hud.has_selected_quest is False
        assert hud.spiral_center.x() == 264.0

        hud.open_tree()
        hud._unfold_progress = 1.0  # мгновенно раскрыто для теста

        selected_events = []
        hud.quest_selected.connect(lambda qid: selected_events.append(qid))

        # Находим бусинку «Портал Воли»
        portal_node = next(n for n in hud.tree_nodes if n.quest.id == "quest-portal-volya")

        # Клик по бусинке
        click_ev = QMouseEvent(
            QMouseEvent.MouseButtonPress,
            portal_node.target_pos,
            Qt.LeftButton,
            Qt.LeftButton,
            Qt.NoModifier,
        )
        hud.mousePressEvent(click_ev)

        # 1. Сначала узел помечается как ожидающий, а дерево сворачивается
        assert hud._pending_selection_node == portal_node
        assert hud._unfold_target == 0.0
        assert hud._gliding_node is None

        # Проматываем сворачивание дерева (progress -> 0.0)
        for _ in range(35):
            hud._on_anim_tick()

        # 2. После исчезновения дерева стартует скольжение бусинки
        assert hud._unfold_progress == 0.0
        assert hud._gliding_node == portal_node
        assert hud._pending_selection_node is None

        # Проматываем скольжение бусинки к спирали
        for _ in range(25):
            hud._on_anim_tick()

        assert hud._gliding_node is None
        assert hud.has_selected_quest is True
        assert hud.active_quest_id == "quest-portal-volya"
        assert hud.active_quest_title == "Портал Воли"
        assert "quest-portal-volya" in selected_events

        # 3. Клик по выбранному квесту на месте спирали при закрытом дереве -> ничего пока не происходит!
        spiral_click_ev = QMouseEvent(
            QMouseEvent.MouseButtonPress,
            hud.spiral_center,
            Qt.LeftButton,
            Qt.LeftButton,
            Qt.NoModifier,
        )
        hud.mousePressEvent(spiral_click_ev)
        assert hud._tree_open is False
        assert hud.active_quest_id == "quest-portal-volya"

        # 4. Раскрываем дерево и кликаем по спирали -> выбор квеста «Воля»
        hud.open_tree()
        assert hud._tree_open is True
        hud.mousePressEvent(spiral_click_ev)
        assert hud.active_quest_id == "quest-volya-root"
        assert hud.active_quest_title == "Воля"
        assert selected_events[-1] == "quest-volya-root"


def test_quest_tooltip_and_constant_visibility(temp_node_dir, qapp):
    """Проверка подсказки с именем выбранного квеста, отсутствия подсказки у «Воли» и видимости дуги/нити."""
    with VolyaNode(node_dir=temp_node_dir) as node:
        hud = QuestTreeHUD(node)

        # 1. До выбора квеста: спираль не видна и не реагирует на наведение
        assert hud.has_selected_quest is False
        assert hud._is_near_spiral(hud.spiral_center) is False

        # 2. Устанавливаем выбранный квест «Портал Воли»
        hud.set_active_quest("quest-portal-volya")
        hud.has_selected_quest = True

        # Спираль / выбранный элемент теперь интерактивен
        assert hud._is_near_spiral(hud.spiral_center) is True

        # При уходе курсора с аватарки дуга остаётся видимой, так как квест выбран
        hud.on_avatar_hovered(False)
        assert hud._arc_visible is True

        # При наведении на спираль в закрытом дереве подсказка показывает название выбранного квеста
        hud._spiral_hovered = True
        assert hud.active_quest_title == "Портал Воли"

        # Для квеста «Воля» подсказки нет вообще
        hud.set_active_quest("quest-volya-root")
        assert hud.active_quest_title == "Воля"


def test_volya_logo_pixmap_and_rendering(temp_node_dir, qapp):
    """Проверка загрузки канонического логотипа Вольного Древа и его использования для квеста «Воля»."""
    with VolyaNode(node_dir=temp_node_dir) as node:
        hud = QuestTreeHUD(node)

        # 1. Проверяем получение логотипа Воли из модели квеста quest.logo
        root_q = node.dag_store.get_quest("quest-volya-root")
        assert root_q is not None
        assert root_q.logo is not None
        assert node.dag_store.get_blob(root_q.logo) is not None

        pix = hud.get_volya_logo_pixmap(size=128)
        assert pix is not None
        assert not pix.isNull()
        assert pix.width() == 128
        assert pix.height() == 128

        # 2. Проверяем привязку логотипа к новому квесту
        test_logo_bytes = b"fake_png_or_jpg_data_for_test"
        blob_hash = node.dag_store.put_blob(test_logo_bytes)
        custom_quest = node.create_quest(
            title="Тестовый Квест",
            kon=Kon(essence="Тест"),
            parent_quest_id="quest-volya-root",
            tier=TreeTier.ROOT_CHILD,
            created_at="2026-11-05T12:00:00Z",
            quest_id="quest-test-logo",
            logo=blob_hash,
        )
        assert custom_quest.logo == blob_hash
        assert node.dag_store.get_quest_logo(custom_quest) == test_logo_bytes

        # 2. При выборе квеста «Воля» активный пиксмап соответствует логотипу
        hud.set_active_quest("quest-volya-root")
        assert hud._active_quest_pixmap is not None
        assert not hud._active_quest_pixmap.isNull()
        assert hud._active_quest_pixmap.width() == 128

        # 3. Проверяем отрисовку без ошибок при закрытом и открытом дереве
        from PySide6.QtGui import QImage, QPainter
        img = QImage(800, 600, QImage.Format_ARGB32_Premultiplied)
        painter = QPainter(img)

        # Спокойное состояние с выбранной «Волей»
        hud.has_selected_quest = True
        hud._tree_open = False
        hud.paintEvent(None)

        # Состояние открытого дерева
        hud._tree_open = True
        hud._unfold_progress = 1.0
        hud.paintEvent(None)
        painter.end()
