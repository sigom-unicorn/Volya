"""
Главное Окно «Воля» — Обитель Вольного Духа (VolyaLivingWindow).
Бесшовное живое пространство перед Великим Баньяном на PySide6 (Zero Local Web).
"""

from __future__ import annotations

import sys
from typing import Optional

from PySide6.QtCore import QPoint, QRectF, QSize, QTimer, Qt
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QIcon,
    QKeyEvent,
    QPainter,
    QPaintEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from portal_volya.ui_desktop.world.living_canvas import LivingWorldCanvas


class LivingWorldWidget(QWidget):
    """Полноэкранный холст с активным игровым циклом анимации живого мира."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.canvas = LivingWorldCanvas()

        # Настройка таймера анимации (35-40 FPS, плавно и легко для процессора)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_tick)
        self.timer.start(25) # ~40 FPS

        # Режим авто-прокрутки суток (для демонстрации смены дня и ночи)
        self.auto_cycle = False
        self.cycle_speed = 0.5 # часов в секунду

    def _on_tick(self) -> None:
        if self.auto_cycle and not self.canvas.celestial.use_realtime:
            # Продвигаем время вперёд
            self.canvas.celestial.simulated_hour = (
                self.canvas.celestial.simulated_hour + 0.025 * self.cycle_speed
            ) % 24.0

        self.canvas.update()
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        self.canvas.render(painter, self.width(), self.height())
        painter.end()


class GlassControlPill(QFrame):
    """Парящая полупрозрачная панель управления живым временем суток (Glassmorphism)."""

    def __init__(self, world_widget: LivingWorldWidget, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.world_widget = world_widget

        self.setObjectName("glassPill")
        self.setStyleSheet("""
            #glassPill {
                background: rgba(14, 20, 36, 0.65);
                border: 1px solid rgba(255, 255, 255, 0.18);
                border-radius: 16px;
            }
            QLabel {
                color: #e2e8f0;
                font-family: 'Segoe UI', 'Roboto', sans-serif;
                font-size: 13px;
            }
            QPushButton {
                background: rgba(255, 255, 255, 0.08);
                color: #f8fafc;
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 8px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: 500;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.20);
                border-color: rgba(255, 255, 255, 0.35);
            }
            QPushButton:pressed {
                background: rgba(255, 255, 255, 0.30);
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: rgba(255, 255, 255, 0.15);
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #f59e0b, stop:1 #3b82f6);
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #ffffff;
                width: 16px;
                margin-top: -5px;
                margin-bottom: -5px;
                border-radius: 8px;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(12)

        # Индикатор времени суток
        self.lbl_time = QLabel("⏳ Загрузка...")
        self.lbl_time.setFont(QFont("Segoe UI", 11, QFont.DemiBold))
        layout.addWidget(self.lbl_time)

        # Слайдер часа суток (0 .. 24)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 240) # Шаг 0.1 часа
        self.slider.setFixedWidth(180)
        self.slider.valueChanged.connect(self._on_slider_changed)
        layout.addWidget(self.slider)

        # Кнопки быстрых фаз
        btn_dawn = QPushButton("🌅 Рассвет")
        btn_dawn.clicked.connect(lambda: self._set_hour(6.2))
        layout.addWidget(btn_dawn)

        btn_noon = QPushButton("☀️ День")
        btn_noon.clicked.connect(lambda: self._set_hour(12.0))
        layout.addWidget(btn_noon)

        btn_sunset = QPushButton("🌇 Закат")
        btn_sunset.clicked.connect(lambda: self._set_hour(18.8))
        layout.addWidget(btn_sunset)

        btn_night = QPushButton("🌙 Ночь")
        btn_night.clicked.connect(lambda: self._set_hour(23.5))
        layout.addWidget(btn_night)

        self.btn_realtime = QPushButton("🕰️ Реальное время")
        self.btn_realtime.clicked.connect(self._toggle_realtime)
        layout.addWidget(self.btn_realtime)

        self.btn_cycle = QPushButton("▶️ Цикл суток")
        self.btn_cycle.clicked.connect(self._toggle_cycle)
        layout.addWidget(self.btn_cycle)

        # Таймер обновления подписи времени
        self.lbl_timer = QTimer(self)
        self.lbl_timer.timeout.connect(self._refresh_label)
        self.lbl_timer.start(250)

    def _set_hour(self, h: float) -> None:
        self.world_widget.auto_cycle = False
        self.world_widget.canvas.celestial.set_hour(h)
        self.slider.blockSignals(True)
        self.slider.setValue(int(h * 10))
        self.slider.blockSignals(False)
        self._refresh_label()

    def _on_slider_changed(self, val: int) -> None:
        self.world_widget.auto_cycle = False
        h = val / 10.0
        self.world_widget.canvas.celestial.set_hour(h)
        self._refresh_label()

    def _toggle_realtime(self) -> None:
        self.world_widget.auto_cycle = False
        self.world_widget.canvas.celestial.set_realtime(True)
        self._refresh_label()

    def _toggle_cycle(self) -> None:
        self.world_widget.auto_cycle = not self.world_widget.auto_cycle
        if self.world_widget.auto_cycle:
            self.world_widget.canvas.celestial.set_realtime(False)
            self.btn_cycle.setText("⏸️ Пауза")
        else:
            self.btn_cycle.setText("▶️ Цикл суток")

    def _refresh_label(self) -> None:
        h = self.world_widget.canvas.celestial.current_hour
        hours = int(h)
        minutes = int((h - hours) * 60)

        # Эмодзи фазы
        if 5.0 <= h < 7.5:
            phase = "🌅 Рассвет"
        elif 7.5 <= h < 17.0:
            phase = "☀️ День"
        elif 17.0 <= h < 20.5:
            phase = "🌇 Закат"
        else:
            phase = "🌙 Ночь"

        mode_str = " (Локальное)" if self.world_widget.canvas.celestial.use_realtime else ""
        self.lbl_time.setText(f"{phase} {hours:02d}:{minutes:02d}{mode_str}")

        if not self.slider.isSliderDown():
            self.slider.blockSignals(True)
            self.slider.setValue(int(h * 10))
            self.slider.blockSignals(False)


class VolyaLivingWindow(QMainWindow):
    """Главное окно суверенного портала «Воля»."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Воля — Обитель Вольного Духа у Великого Баньяна")
        self.resize(1360, 840)
        self.setMinimumSize(1024, 640)

        # Центральный живой холст
        self.world_widget = LivingWorldWidget(self)
        self.setCentralWidget(self.world_widget)

        # Парящая панель управления внизу
        self.control_pill = GlassControlPill(self.world_widget, self)
        self.control_pill.adjustSize()

        # Подсказка горячих клавиш
        self.lbl_hint = QLabel("Нажми H — скрыть/показать управление | F11 — во весь экран", self)
        self.lbl_hint.setStyleSheet("""
            color: rgba(255, 255, 255, 0.45);
            font-size: 11px;
            font-family: sans-serif;
            background: transparent;
        """)
        self.lbl_hint.adjustSize()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # Центрируем панель управления внизу экрана
        pill_w = self.control_pill.width()
        pill_h = self.control_pill.height()
        x = (self.width() - pill_w) // 2
        y = self.height() - pill_h - 24
        self.control_pill.move(x, y)

        # Подсказка в левом нижнем углу
        self.lbl_hint.move(20, self.height() - 28)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_F11:
            if self.isFullScreen():
                self.showNormal()
            else:
                self.showFullScreen()
        elif event.key() == Qt.Key_H:
            # Переключение видимости панели
            self.control_pill.setVisible(not self.control_pill.isVisible())
            self.lbl_hint.setVisible(self.control_pill.isVisible())
        else:
            super().keyPressEvent(event)
