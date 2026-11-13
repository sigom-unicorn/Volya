"""
Тесты интерактивного UI выбора, создания и отображения Потоков сотворчества.
"""

import gc
from pathlib import Path
import tempfile
import pytest

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QMouseEvent, QPixmap
from PySide6.QtWidgets import QApplication

from portal_volya.core.models import FlowKind, QuestFlow
from portal_volya.node import VolyaNode
from portal_volya.ui_desktop.flow_stream_view import QuestFlowStreamView
from portal_volya.ui_desktop.quest_tree import QuestTreeHUD


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    return app


def test_quest_tree_dual_arc_flow_menu(qapp):
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        node = VolyaNode(node_dir=tmp_dir, default_username="Сиг")
        hud = QuestTreeHUD(node)
        hud.resize(1200, 800)
        hud.show()

        # Выбираем квест «Воля»
        hud.has_selected_quest = True
        hud.set_active_quest("quest-volya-root")

        # 1. Наведение на выбранный квест -> раскрываются ОБЕ дуги
        pt_quest = QPointF(264.0, 72.0)
        move_ev1 = QMouseEvent(QMouseEvent.Type.MouseMove, pt_quest, Qt.NoButton, Qt.NoButton, Qt.NoModifier)
        hud.mouseMoveEvent(move_ev1)
        assert hud._flow_menu_mode == "both"

        # 2. Движение вправо к правой дуге (Выбор потока) -> нижняя дуга исчезает
        pt_right = QPointF(306.6, 54.8) # диск Диалога
        move_ev2 = QMouseEvent(QMouseEvent.Type.MouseMove, pt_right, Qt.NoButton, Qt.NoButton, Qt.NoModifier)
        hud.mouseMoveEvent(move_ev2)
        assert hud._flow_menu_mode == "select"
        assert hud._sel_flow_kind == FlowKind.DIALOGUE

        # 3. Клик по потоку в списке -> выбор потока
        flows = hud._quest_flows_cache
        assert len(flows) >= 1

        selected_flows = []
        hud.flow_selected.connect(lambda fid: selected_flows.append(fid))

        # Выбираем Беседу на правой дуге
        pt_conv = QPointF(306.6, 89.2)
        move_ev3 = QMouseEvent(QMouseEvent.Type.MouseMove, pt_conv, Qt.NoButton, Qt.NoButton, Qt.NoModifier)
        hud.mouseMoveEvent(move_ev3)
        assert hud._sel_flow_kind == FlowKind.CONVERSATION

        # 4. Наведение вниз к дуге создания
        pt_bottom = QPointF(264.0, 118.0)
        hud._flow_menu_mode = "both"
        move_ev4 = QMouseEvent(QMouseEvent.Type.MouseMove, pt_bottom, Qt.NoButton, Qt.NoButton, Qt.NoModifier)
        hud.mouseMoveEvent(move_ev4)
        assert hud._flow_menu_mode == "create"
        assert hud._hovered_create_segment is not None

        # Клик по сегменту «Диалог» (слева от центра)
        pt_click_dia = QPointF(256.0, 118.0)
        hud._handle_flow_mouse_move(pt_click_dia)
        click_dia_ev = QMouseEvent(QMouseEvent.Type.MouseButtonPress, pt_click_dia, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        hud.mousePressEvent(click_dia_ev)
        assert hud._create_step == "title"
        assert hud.flow_title_input.isVisible()

        # Ввод названия и клик по '>'
        hud.flow_title_input.setText("Диалог с Эйрой о гармонии")
        pt_next = QPointF(376.0, 184.0)
        hud._handle_flow_mouse_move(pt_next)
        click_next_ev = QMouseEvent(QMouseEvent.Type.MouseButtonPress, pt_next, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        hud.mousePressEvent(click_next_ev)
        assert hud._create_step == "players"
        assert len(hud._quest_players_cache) >= 1
        assert hud._quest_players_cache[0].username == "Эйра"

        # Клик по первому игроку (Эйре) -> завершает создание диалога!
        pt_eira = QPointF(460.0, 232.0)
        hud._handle_flow_mouse_move(pt_eira)
        click_eira_ev = QMouseEvent(QMouseEvent.Type.MouseButtonPress, pt_eira, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        hud.mousePressEvent(click_eira_ev)

        assert len(selected_flows) == 1
        created_flow_id = selected_flows[0]
        created_flow = node.dag_store.get_quest_flow(created_flow_id)
        assert created_flow is not None
        assert created_flow.title == "Диалог с Эйрой о гармонии"
        assert created_flow.kind == FlowKind.DIALOGUE

        hud.deleteLater()
        node.close()
        del node
        gc.collect()


def test_quest_flow_stream_view(qapp):
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        node = VolyaNode(node_dir=tmp_dir, default_username="Сиг")
        flow = node.create_quest_flow(
            quest_id="quest-volya-root",
            kind=FlowKind.CONVERSATION,
            title="Общая беседа квеста Воля",
        )

        # Отправляем каплю
        user_drop, _ = node.post_flow_drop(
            quest_id="quest-volya-root",
            flow_id=flow.id,
            content="Первое слово в потоке сотворчества!",
        )

        view = QuestFlowStreamView(node)
        view.resize(700, 500)
        view.load_flow(flow.id)

        assert view.lbl_title.text() == "Общая беседа квеста Воля"
        assert view.drops_layout.count() >= 2 # капля + spacer

        # Отправка капли через орган ввода
        view.drop_creator.input_text.setText("Вторая капля мысли")
        view.drop_creator.btn_submit.click()

        drops_now = node.get_accessible_drops(flow.id)
        assert len(drops_now) == 2
        assert drops_now[1].content == "Вторая капля мысли"

        view.deleteLater()
        node.close()
        del node
        gc.collect()


def test_living_flow_stream_on_canvas(qapp):
    """Тест работы живого потока капель прямо на полотне мира (без окон)."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        node = VolyaNode(node_dir=tmp_dir, default_username="Сиг")
        flow = node.create_quest_flow(
            quest_id="quest-volya-root",
            kind=FlowKind.CONVERSATION,
            title="Живая беседа на полотне",
        )

        hud = QuestTreeHUD(node)
        hud.resize(1200, 800)
        hud.show()

        # Открываем поток
        hud.open_flow(flow.id)
        assert hud._active_flow_id == flow.id
        assert hud._active_flow is not None
        assert hud._active_flow.title == "Живая беседа на полотне"

        # Клик по двойной спирали -> закрывает поток
        spiral_pt = hud._flow_spiral_center
        click_sp = QMouseEvent(QMouseEvent.Type.MouseButtonPress, spiral_pt, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        hud.mousePressEvent(click_sp)
        assert hud._active_flow_id is None

        # Вновь открываем поток
        hud.open_flow(flow.id)
        assert hud._active_flow_id == flow.id

        # Клик по кнопке-капле на конце левой ветви -> раскрывает орган ввода
        btn_pt = hud._get_flow_drop_btn_center()
        assert not hud._flow_input_active
        click_btn = QMouseEvent(QMouseEvent.Type.MouseButtonPress, btn_pt, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        hud.mousePressEvent(click_btn)
        assert hud._flow_input_active
        assert hud.flow_drop_input.isVisible()

        # Вводим текст капли и нажимаем подтверждение (Enter или кнопку ✔)
        hud.flow_drop_input.setText("Живое слово без единого окна!")
        hud._submit_new_flow_drop()

        # Проверяем, что капля сохранена в DAG
        drops = node.get_accessible_drops(flow.id)
        assert len(drops) == 1
        assert drops[0].content == "Живое слово без единого окна!"
        assert not hud._flow_input_active
        assert not hud.flow_drop_input.isVisible()

        # Проверяем отрисовку и копирование текста капли в буфер обмена
        pix = QPixmap(1000, 700)
        hud.render(pix)
        assert len(hud._flow_drop_hitboxes) == 1
        drop_rect, drop_item = hud._flow_drop_hitboxes[0]
        assert drop_item.id == drops[0].id

        # Наведение мыши на каплю -> подсветка и курсор
        move_drop = QMouseEvent(QMouseEvent.Type.MouseMove, drop_rect.center(), Qt.NoButton, Qt.NoButton, Qt.NoModifier)
        hud.mouseMoveEvent(move_drop)
        assert hud._hovered_flow_drop_id == drop_item.id

        # Клик по капле -> текст копируется в буфер обмена
        click_drop = QMouseEvent(QMouseEvent.Type.MouseButtonPress, drop_rect.center(), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        hud.mousePressEvent(click_drop)
        assert QApplication.clipboard().text() == "Живое слово без единого окна!"
        assert hud._copied_drop_id == drop_item.id

        hud.deleteLater()
        node.close()
        del node
        gc.collect()
