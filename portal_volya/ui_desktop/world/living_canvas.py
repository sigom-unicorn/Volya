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
from PySide6.QtGui import QImage, QPainter, QPixmap

from portal_volya.ui_desktop.world.atmosphere import AtmosphereEngine
from portal_volya.ui_desktop.world.celestial import CelestialEngine
from portal_volya.ui_desktop.world.creatures import CreaturesEngine
from portal_volya.ui_desktop.world.water import WaterStreamEngine


class LivingWorldCanvas:
    """Компонент живого мира поляны для полноэкранного нативного рендеринга."""

    PHASE_FILENAMES = {
        "dawn": ["баньян_утро.webp", "баньян_утро.png"],
        "day": ["баньян_день.webp", "баньян_день.png"],
        "sunset": ["баньян_вечер.webp", "баньян_вечер.png"],
        "night": ["баньян_ночь.webp", "баньян_ночь.png"],
    }

    FALLBACK_FILENAMES = {
        "dawn": ["banyan_4k_dawn.webp", "banyan_4k_dawn.png"],
        "day": ["banyan_4k_day.webp", "banyan_4k_day.png"],
        "sunset": ["banyan_4k_sunset.webp", "banyan_4k_sunset.png"],
        "night": ["banyan_4k_night.webp", "banyan_4k_night.png"],
    }

    def __init__(self, images_dir: Optional[Path] = None) -> None:
        self.celestial = CelestialEngine()
        self.atmosphere = AtmosphereEngine()
        self.water = WaterStreamEngine()
        self.creatures = CreaturesEngine()

        self.last_tick_time = time.perf_counter()

        # Поиск директории с 4K картинами
        if images_dir is None:
            # Основная папка ассетов живого мира десктопного портала
            images_dir = Path(__file__).parent.parent / "assets" / "images"

        fallback_dir = Path(__file__).parent.parent.parent / "ui" / "images"

        # Загрузка мастер-текстур четырёх фаз (WebP -> PNG)
        self._master_pixmaps: dict[str, QPixmap] = {}
        for phase, fnames in self.PHASE_FILENAMES.items():
            pixmap = QPixmap()
            # 1. Проверяем основную папку (ui/images)
            for fname in fnames:
                p = images_dir / fname
                if p.exists():
                    pixmap = QPixmap(str(p))
                    if not pixmap.isNull():
                        break
            # 2. Если не найдено, проверяем fallback_dir (assets/images)
            if pixmap.isNull():
                fb_fnames = self.FALLBACK_FILENAMES.get(phase, [])
                for fname in fb_fnames:
                    p = fallback_dir / fname
                    if p.exists():
                        pixmap = QPixmap(str(p))
                        if not pixmap.isNull():
                            break
            self._master_pixmaps[phase] = pixmap

        # Кэш масштабированных под текущее разрешение экрана текстур
        self._cached_viewport: Tuple[int, int] = (0, 0)
        self._scaled_pixmaps: dict[str, QPixmap] = {}

        # Маска кроны Великого Баньяна для точного затенения Луны в зените (4K)
        mask_path = images_dir / "tree_canopy_mask.webp"
        if not mask_path.exists():
            mask_path = images_dir / "tree_canopy_mask.png"

        if mask_path.exists():
            self._master_canopy_mask: QImage = QImage(str(mask_path))
        else:
            day_path = images_dir / "баньян_день.webp"
            if not day_path.exists():
                day_path = images_dir / "баньян_день.png"
            self._master_canopy_mask = self._generate_canopy_mask(str(day_path)) if day_path.exists() else QImage()

        self._scaled_canopy_mask: Optional[QImage] = None

        # Поэтапные переключатели слоёв живого мира (по шагам плана)
        self.enable_celestial: bool = True   # Этап 2: Солнце, Луна, звёзды, метеоры
        self.enable_atmosphere: bool = True  # Этап 2: Облака, лучи, листва, пыльца
        self.enable_water: bool = False       # Этап 3: Ручей, струи, блики, лепестки
        self.enable_creatures: bool = False   # Этап 4: Птицы, олени, странники, светлячки

    @staticmethod
    def _generate_canopy_mask(day_image_path: str) -> QImage:
        """Автономная генерация 4K альфа-маски кроны Баньяна из дневного полотна."""
        img = QImage(day_image_path)
        if img.isNull():
            return QImage()
        import numpy as np
        w, h = img.width(), img.height()
        arr = np.frombuffer(img.constBits(), dtype=np.uint8).reshape((h, w, 4))
        r = arr[:, :, 2].astype(float)
        g = arr[:, :, 1].astype(float)
        b = arr[:, :, 0].astype(float)
        gray = (r + g + b) / 3.0

        low_th, high_th = 100.0, 155.0
        alpha = np.zeros((h, w), dtype=np.float32)
        alpha[gray <= low_th] = 255.0
        trans_mask = (gray > low_th) & (gray < high_th)
        t = (high_th - gray[trans_mask]) / (high_th - low_th)
        alpha[trans_mask] = (t * t * (3.0 - 2.0 * t)) * 255.0

        mask_arr = np.zeros((h, w, 4), dtype=np.uint8)
        mask_arr[:, :, 3] = np.clip(alpha, 0, 255).astype(np.uint8)
        return QImage(mask_arr.data, w, h, w * 4, QImage.Format_ARGB32).copy()

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

        # Синхронное масштабирование маски кроны Баньяна (с тем же KeepAspectRatioByExpanding)
        if not self._master_canopy_mask.isNull():
            self._scaled_canopy_mask = self._master_canopy_mask.scaled(
                width,
                height,
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation,
            )

        self._cached_viewport = (width, height)

    def update(self) -> None:
        """Обновление физики и анимаций живого мира."""
        now = time.perf_counter()
        dt = now - self.last_tick_time
        dt = min(0.1, max(0.001, dt))
        self.last_tick_time = now

        self.celestial.update(dt)
        vw, vh = self._cached_viewport
        w = float(vw if vw > 0 else 1920)
        h = float(vh if vh > 0 else 1080)

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
        draw_x = 0
        draw_y = 0
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
        # ЭТАП 2: Небо, Светила и Атмосфера
        # =============================================================
        if self.enable_celestial:
            # 1. Живые мерцающие звёзды и метеоры ночного неба
            self.celestial.render_stars_and_meteors(painter, width, height, night_factor)
            # 2. Дневное Светило — Солнце (восход, зенит, закат с ореолом Bloom)
            self.celestial.render_sun(painter, width, height)
            # 3. Ночное Светило — Луна (с реальной фазой, пепельным светом и короной)
            self.celestial.render_moon(
                painter,
                width,
                height,
                night_factor,
                canopy_mask=self._scaled_canopy_mask,
                draw_offset=(draw_x, draw_y),
            )

        if self.enable_atmosphere:
            # 4. Дрейфующие полупрозрачные облака с адаптивной подсветкой
            self.atmosphere.render_clouds(painter, width, height, current_hour)
            # 5. Солнечные лучи сквозь крону (God Rays)
            sun_x, sun_y, sun_elev = self.celestial.get_sun_position(width, height)
            self.atmosphere.render_god_rays(painter, width, height, current_hour, sun_x, sun_y, sun_elev)
            # 6. Дыхание и шелест листвы Баньяна на ветру
            self.atmosphere.render_canopy_breath(painter, width, height, current_hour)
            # 7. Порхающие листочки и лепестки Баньяна
            self.atmosphere.render_drifting_leaves(painter, width, height, current_hour)
            # 8. Парящие лесные споры и золотистая пыльца
            self.atmosphere.render_spores(painter, width, height, current_hour)

