"""
Живой Холст Поляны (LivingWorldCanvas).
Высокопроизводительный бесшовный рендеринг живого мира перед Великим Баньяном на PySide6.
Опирается на четыре мастер-полотна 4K (утро, день, вечер, ночь) с непрерывным астрономическим
смешиванием суток и динамическими слоями живой природы (светила, облака, река, обитатели).
"""

from __future__ import annotations

import os
from pathlib import Path
import time
from typing import Dict, Optional, Tuple

from PySide6.QtCore import QPoint, QRect, QRectF, Qt
from PySide6.QtGui import QPainter, QPixmap

from portal_volya.ui_desktop.world.atmosphere import AtmosphereEngine
from portal_volya.ui_desktop.world.celestial import CelestialEngine
from portal_volya.ui_desktop.world.creatures import CreaturesEngine
from portal_volya.ui_desktop.world.water import WaterStreamEngine


class LivingWorldCanvas:
    """Компонент живого мира поляны для полноэкранного нативного рендеринга."""

    PHASE_FILENAMES = {
        "dawn": "баньян_утро.png",
        "day": "баньян_день.png",
        "sunset": "баньян_вечер.png",
        "night": "баньян_ночь.png",
    }

    FALLBACK_FILENAMES = {
        "dawn": "banyan_4k_dawn.png",
        "day": "banyan_4k_day.png",
        "sunset": "banyan_4k_sunset.png",
        "night": "banyan_4k_night.png",
    }

    def __init__(self, images_dir: Optional[Path] = None) -> None:
        self.celestial = CelestialEngine()
        self.atmosphere = AtmosphereEngine()
        self.water = WaterStreamEngine()
        self.creatures = CreaturesEngine()

        self.last_tick_time = time.perf_counter()

        # Поиск директории с 4K картинами
        if images_dir is None:
            # 1. Основная папка ui/images
            images_dir = Path(__file__).parent.parent.parent / "ui" / "images"

        fallback_dir = Path(__file__).parent.parent / "assets" / "images"

        # Загрузка мастер-текстур четырёх фаз
        self._master_pixmaps: dict[str, QPixmap] = {}
        for phase, fname in self.PHASE_FILENAMES.items():
            path = images_dir / fname
            if not path.exists():
                path = fallback_dir / self.FALLBACK_FILENAMES[phase]
            if path.exists():
                self._master_pixmaps[phase] = QPixmap(str(path))
            else:
                self._master_pixmaps[phase] = QPixmap()

        # Кэш масштабированных под текущее разрешение экрана текстур
        self._cached_viewport: Tuple[int, int] = (0, 0)
        self._scaled_pixmaps: dict[str, QPixmap] = {}

        # Поэтапные переключатели слоёв живого мира (по шагам плана)
        self.enable_celestial: bool = False   # Этап 2: Солнце, Луна, звёзды, метеоры
        self.enable_atmosphere: bool = False  # Этап 2: Облака, лучи, пыльца
        self.enable_water: bool = False       # Этап 3: Ручей, струи, блики, лепестки
        self.enable_creatures: bool = False   # Этап 4: Птицы, олени, странники, светлячки

    def _ensure_viewport_cache(self, width: int, height: int) -> None:
        """Предварительное масштабирование четырёх фаз при изменении размера окна."""
        if self._cached_viewport == (width, height) and self._scaled_pixmaps:
            return

        self._scaled_pixmaps.clear()
        for phase, master in self._master_pixmaps.items():
            if master.isNull():
                continue
            # Масштабируем с заполнением экрана и сохранением пропорций 16:9
            scaled = master.scaled(
                width,
                height,
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation,
            )
            self._scaled_pixmaps[phase] = scaled

        self._cached_viewport = (width, height)

    def update(self) -> None:
        """Обновление физики и анимаций живого мира."""
        now = time.perf_counter()
        dt = now - self.last_tick_time
        dt = min(0.1, max(0.001, dt))
        self.last_tick_time = now

        self.celestial.update(dt)
        w, h = 1920.0, 1080.0
        if self.enable_atmosphere:
            self.atmosphere.update(dt, w, h)
        if self.enable_water:
            self.water.update(dt)
        if self.enable_creatures:
            self.creatures.update(dt, w, h)

    def render(self, painter: QPainter, width: int, height: int) -> None:
        """Отрисовка всех слоёв живого мира в строгом порядке глубины."""
        self._ensure_viewport_cache(width, height)

        current_hour = self.celestial.current_hour
        base_phase, next_phase, blend_factor, night_factor = self.celestial.get_phase_blending()

        # =============================================================
        # ЭТАП 1: Бесшовный фотореалистичный 4K-ландшафт Великого Баньяна
        # =============================================================
        base_pixmap = self._scaled_pixmaps.get(base_phase)
        if base_pixmap and not base_pixmap.isNull():
            draw_x = (width - base_pixmap.width()) // 2
            draw_y = height - base_pixmap.height() # Прижимаем к низу поляны

            painter.save()
            painter.setOpacity(1.0)
            painter.drawPixmap(draw_x, draw_y, base_pixmap)

            # Плавное наложение перетекающей фазы суток
            if next_phase and blend_factor > 0.001:
                next_pixmap = self._scaled_pixmaps.get(next_phase)
                if next_pixmap and not next_pixmap.isNull():
                    painter.setOpacity(blend_factor)
                    painter.drawPixmap(draw_x, draw_y, next_pixmap)
            painter.restore()

        # =============================================================
        # ЭТАП 2: Небо, Светила и Атмосфера (включается на Этапе 2)
        # =============================================================
        if self.enable_celestial:
            self.celestial.render_stars_and_meteors(painter, width, height, night_factor)

        if self.enable_atmosphere:
            self.atmosphere.render_clouds(painter, width, height, current_hour)
            sun_x, sun_y, sun_elev = self.celestial.get_sun_position(width, height)
            self.atmosphere.render_god_rays(painter, width, height, current_hour, sun_x, sun_y, sun_elev)

        # =============================================================
        # ЭТАП 3: Живой Ручей (включается на Этапе 3)
        # =============================================================
        if self.enable_water:
            self.water.render_stream(painter, width, height, current_hour, night_factor)

        # =============================================================
        # ЭТАП 4: Обитатели и Дыхание леса (включается на Этапе 4)
        # =============================================================
        if self.enable_creatures:
            self.creatures.render_birds(painter)
            self.creatures.render_wildlife_and_wanderers(painter, height)
            self.creatures.render_fireflies(painter, width, height, night_factor)

        if self.enable_atmosphere:
            self.atmosphere.render_spores(painter, width, height, current_hour)

