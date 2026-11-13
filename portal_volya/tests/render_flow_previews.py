"""
Скрипт создания скриншотов сакральных дуг выбора/создания потоков и центрального свитка капель
на живом фоне ночной обители Баньяна.
"""

import sys
import tempfile
from pathlib import Path
from PySide6.QtCore import QPointF, QRect, Qt
from PySide6.QtGui import QImage, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

from portal_volya.core.models import FlowKind
from portal_volya.node import VolyaNode
from portal_volya.ui_desktop.flow_stream_view import QuestFlowStreamView
from portal_volya.ui_desktop.quest_tree import QuestTreeHUD


def capture_screenshots():
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)

    out_dir = Path("C:/Users/Polina/.gemini/antigravity/brain/59257bed-fee3-4f38-9fc3-8af41e5264b6")
    bg_dir = Path("portal_volya/ui_desktop/assets/images")
    bg_night_path = bg_dir / "баньян_ночь.webp"
    if not bg_night_path.exists():
        bg_night_path = bg_dir / "баньян_ночь.png"

    night_pixmap = QPixmap(str(bg_night_path)) if bg_night_path.exists() else None

    def create_canvas_image(w=1000, h=700):
        img = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
        p = QPainter(img)
        if night_pixmap and not night_pixmap.isNull():
            scaled = night_pixmap.scaled(w, h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            p.drawPixmap(0, 0, scaled, 0, 0, w, h)
        else:
            p.fillRect(0, 0, w, h, Qt.darkBlue)
        p.end()
        return img

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        node = VolyaNode(node_dir=tmp_dir, default_username="Сиг")

        hud = QuestTreeHUD(node)
        hud.resize(1000, 700)
        hud.has_selected_quest = True
        hud.set_active_quest("quest-volya-root")
        hud.show()

        # 1. Скриншот: Обе дуги одновременно (наведение на выбранный квест)
        hud._flow_menu_mode = "both"
        hud.update()
        img_both = create_canvas_image(1000, 700)
        hud.render(img_both)
        img_both.save(str(out_dir / "preview_flows_dual_arcs.png"))

        # 2. Скриншот: Правая дуга (выбор потока, раскрыта ветвь бесед и диалогов)
        hud._flow_menu_mode = "select"
        hud._sel_flow_kind = FlowKind.CONVERSATION
        hud.update()
        img_sel = create_canvas_image(1000, 700)
        hud.render(img_sel)
        img_sel.save(str(out_dir / "preview_flows_selection_branch.png"))

        # Zoom на ветку выбора потока
        zoom_rect = QRect(210, 20, 480, 260)
        img_sel_zoom = img_sel.copy(zoom_rect)
        img_sel_zoom.save(str(out_dir / "preview_flows_selection_branch_zoom.png"))

        # 3. Скриншот: Нижняя дуга (активизация сектора «Диалог», ввод названия, кнопка '>' внутри поля ввода)
        hud._flow_menu_mode = "create"
        hud._create_flow_kind = FlowKind.DIALOGUE
        hud._create_step = "title"
        hud.flow_title_input.setText("Имя диалога...")
        hud.flow_title_input.setGeometry(int(264.0 - 95.0), 170, 190, 28)
        hud.flow_next_btn.move(hud.flow_title_input.width() - 25, (hud.flow_title_input.height() - 22) // 2)
        hud.flow_next_btn.show()
        hud.flow_title_input.setVisible(True)
        hud.update()
        img_title = create_canvas_image(1000, 700)
        hud.render(img_title)
        zoom_title_rect = QRect(140, 40, 300, 200)
        img_title_zoom = img_title.copy(zoom_title_rect)
        img_title_zoom.save(str(out_dir / "preview_flows_creation_title_zoom.png"))

        # 4. Скриншот: Нижняя дуга (переход к игрокам, ветвь вправо и вниз к списку)
        hud._create_flow_kind = FlowKind.CONVERSATION
        hud._create_step = "players"
        hud.flow_title_input.setText("Беседа сотворцов о ладах")
        hud.refresh_flows_and_players()
        if hud._quest_players_cache:
            hud._selected_participants = {hud._quest_players_cache[0].pubkey}
        hud.update()
        img_create = create_canvas_image(1000, 700)
        hud.render(img_create)
        img_create.save(str(out_dir / "preview_flows_creation_players.png"))

        zoom_create_rect = QRect(140, 40, 360, 420)
        img_create_zoom = img_create.copy(zoom_create_rect)
        img_create_zoom.save(str(out_dir / "preview_flows_creation_players_zoom.png"))

        # 5. Скриншот: Живой Поток капель прямо на живом полотне Баньяна (без окон!)
        hud._flow_menu_mode = "none"
        flows = node.get_quest_flows("quest-volya-root")
        target_flow = flows[0]

        try:
            node.post_flow_drop(
                quest_id="quest-volya-root",
                flow_id=target_flow.id,
                content="Мир дому нашему! Как ладится сотворчество в квесте «Воля»?",
            )
            node.post_flow_drop(
                quest_id="quest-volya-root",
                flow_id=target_flow.id,
                content="Всё ладится в совести и согласии. Древо распускает свои ветви.",
            )
        except Exception:
            pass

        hud.open_flow(target_flow.id)

        # Добавляем ответную каплю от Эйры, чтобы наглядно показать правую ветвь собеседников:
        from portal_volya.core.models import DropKind, FlowDrop
        eira_drop = FlowDrop(
            id="drop-eira-sample",
            quest_id="quest-volya-root",
            flow_id=target_flow.id,
            flow_kind=target_flow.kind,
            kind=DropKind.TEXT,
            author_pubkey="eira-companion-pk",
            author_name="Эйра",
            recipients=[],
            content="Здравствуй, Сиг! Лад в квесте «Воля» крепнет. Древо отзывается на каждое искреннее намерение.",
            created_at="14:15",
            signature="sig-eira",
        )
        hud._active_flow_drops.append(eira_drop)

        # Открываем поле ввода капли на левой ветви
        hud._flow_input_active = True
        hud.flow_drop_input.setFixedWidth(215)
        hud._position_flow_input()
        hud.flow_drop_input.setText("Совесть — это компас душевного пути...")
        hud.flow_drop_input.setCursorPosition(0)
        hud.flow_drop_input.setVisible(True)
        hud.update()

        img_stream = create_canvas_image(1000, 700)
        hud.render(img_stream)
        img_stream.save(str(out_dir / "preview_central_stream_view.png"))

        zoom_stream_rect = QRect(180, 20, 680, 580)
        img_stream_zoom = img_stream.copy(zoom_stream_rect)
        img_stream_zoom.save(str(out_dir / "preview_living_stream_zoom.png"))

        node.close()
        print("ALL_SCREENSHOTS_CAPTURED_WITH_BACKGROUND")


if __name__ == "__main__":
    capture_screenshots()
