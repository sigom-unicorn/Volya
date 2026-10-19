"""
Небесный двигатель живого мира (CelestialEngine).
Суточный ритм планеты: астрономическое время, фазовое смешение 4K-картин,
мерцание ночных созвездий, падающие метеоры и координаты светил для атмосферных лучей.
"""

from __future__ import annotations

from datetime import datetime, timezone
import math
import random
from typing import List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QRadialGradient


class Star:
    """Звезда на ночном небосводе (в открытых участках неба)."""

    def __init__(self, u: float, v: float, size: float, flicker_freq: float, phase: float, base_alpha: int) -> None:
        self.u = u                      # Нормализованная координата X [0.0 .. 1.0]
        self.v = v                      # Нормализованная координата Y [0.0 .. 0.45]
        self.size = size                # Размер точки (1.0 - 2.6 px)
        self.flicker_freq = flicker_freq
        self.phase = phase
        self.base_alpha = base_alpha


class ShootingStar:
    """Метеор / падающая звезда на ночном небе."""

    def __init__(self, start_x: float, start_y: float, length: float, angle_rad: float, speed: float) -> None:
        self.x = start_x
        self.y = start_y
        self.length = length
        self.angle = angle_rad
        self.speed = speed
        self.progress = 0.0             # 0.0 -> 1.0
        self.is_active = True

    def update(self, dt: float) -> None:
        self.progress += dt * self.speed
        if self.progress >= 1.0:
            self.is_active = False


# Точный профиль верхней кромки кроны Великого Баньяна и горного рельефа:
# (norm_x, y_center_sun) — выверен по 4K-картинам, чтобы светила шли прямо по верху кроны, едва касаясь её
CANOPY_SKY_PROFILE = [
    (0.04, 0.510),  # Самый левый край — заход за горы заката
    (0.12, 0.420),  # Склон западной горы
    (0.20, 0.220),  # Левая ветвь Баньяна
    (0.28, 0.130),  # Левое плечо кроны
    (0.38, 0.045),  # Плавный подъем к вершине
    (0.50, 0.012),  # Зенит — солнце и луна сидят на макушке кроны
    (0.62, 0.042),  # Правое плечо кроны
    (0.72, 0.065),  # Длинная горизонтальная ветвь Баньяна справа
    (0.82, 0.190),  # Окончание правой ветви
    (0.90, 0.400),  # Склон восточной горы
    (0.96, 0.510),  # Самый правый край — восход из-за гор рассвета
]


def _get_canopy_sky_y(norm_x: float) -> float:
    """Вычисляет высоту y по плавному косинусному профилю кромки кроны Баньяна."""
    if norm_x <= CANOPY_SKY_PROFILE[0][0]:
        return CANOPY_SKY_PROFILE[0][1]
    if norm_x >= CANOPY_SKY_PROFILE[-1][0]:
        return CANOPY_SKY_PROFILE[-1][1]
    for i in range(len(CANOPY_SKY_PROFILE) - 1):
        x0, y0 = CANOPY_SKY_PROFILE[i]
        x1, y1 = CANOPY_SKY_PROFILE[i + 1]
        if x0 <= norm_x <= x1:
            t = (norm_x - x0) / (x1 - x0)
            st = (1.0 - math.cos(math.pi * t)) * 0.5
            return y0 + (y1 - y0) * st
    return 0.02


class CelestialEngine:
    """Вычисление суточных фаз, положения светил и динамики ночного неба."""

    def __init__(self) -> None:
        self.use_realtime: bool = True
        self.simulated_hour: float = 12.0
        self.anim_time: float = 0.0

        # Генерация звёзд в чистых областях небосвода вокруг кроны Баньяна:
        # Левое небо (u: 0.02..0.32, v: 0.02..0.45)
        # Правое небо (u: 0.70..0.98, v: 0.02..0.45)
        # Верхняя кромка (u: 0.32..0.70, v: 0.02..0.20)
        rnd = random.Random(108)
        self.stars: list[Star] = []

        # 45 звёзд слева
        for _ in range(45):
            self.stars.append(
                Star(
                    u=rnd.uniform(0.02, 0.32),
                    v=rnd.uniform(0.02, 0.44),
                    size=rnd.uniform(1.0, 2.4),
                    flicker_freq=rnd.uniform(1.8, 4.5),
                    phase=rnd.uniform(0.0, math.tau),
                    base_alpha=rnd.randint(150, 255),
                )
            )

        # 45 звёзд справа
        for _ in range(45):
            self.stars.append(
                Star(
                    u=rnd.uniform(0.70, 0.98),
                    v=rnd.uniform(0.02, 0.44),
                    size=rnd.uniform(1.0, 2.4),
                    flicker_freq=rnd.uniform(1.8, 4.5),
                    phase=rnd.uniform(0.0, math.tau),
                    base_alpha=rnd.randint(150, 255),
                )
            )

        # 25 звёзд в верхнем поднебесье
        for _ in range(25):
            self.stars.append(
                Star(
                    u=rnd.uniform(0.32, 0.70),
                    v=rnd.uniform(0.02, 0.18),
                    size=rnd.uniform(1.0, 2.0),
                    flicker_freq=rnd.uniform(1.5, 4.0),
                    phase=rnd.uniform(0.0, math.tau),
                    base_alpha=rnd.randint(140, 230),
                )
            )

        self.shooting_stars: list[ShootingStar] = []
        self._next_shooting_star_timer = rnd.uniform(6.0, 18.0)

    @property
    def current_hour(self) -> float:
        """Текущее астрономическое время (0.0 .. 24.0)."""
        if self.use_realtime:
            now = datetime.now()
            return now.hour + now.minute / 60.0 + now.second / 3600.0
        return self.simulated_hour % 24.0

    def set_hour(self, hour: float) -> None:
        """Ручная установка часа для демонстрации суток."""
        self.use_realtime = False
        self.simulated_hour = hour % 24.0

    def set_realtime(self, active: bool = True) -> None:
        """Включение привязки к реальным часам системы."""
        self.use_realtime = active

    def get_phase_blending(self) -> Tuple[str, Optional[str], float, float]:
        """
        Вычисляет параметры плавного смешивания четырёх 4K картин:
        Возвращает: (base_phase, next_phase, blend_factor, night_factor)
        - base_phase: 'night' | 'dawn' | 'day' | 'sunset'
        - next_phase: фаза перетекания или None (если чистое состояние)
        - blend_factor: вес перехода от base_phase к next_phase (0.0 .. 1.0)
        - night_factor: степень ночной темноты (0.0 .. 1.0) для звёзд и светлячков
        """
        h = self.current_hour % 24.0

        if 0.0 <= h < 4.5:
            # Чистая глубокая ночь
            return ("night", None, 0.0, 1.0)
        elif 4.5 <= h < 6.25:
            # Переход: Ночь -> Рассвет
            f = (h - 4.5) / (6.25 - 4.5)
            night_factor = 1.0 - f * 0.75  # с 1.0 до 0.25
            return ("night", "dawn", f, night_factor)
        elif 6.25 <= h < 8.0:
            # Переход: Рассвет -> Ясный день
            f = (h - 6.25) / (8.0 - 6.25)
            night_factor = 0.25 * (1.0 - f)  # с 0.25 до 0.0
            return ("dawn", "day", f, night_factor)
        elif 8.0 <= h < 16.5:
            # Полный ясный день
            return ("day", None, 0.0, 0.0)
        elif 16.5 <= h < 18.5:
            # Переход: День -> Закат
            f = (h - 16.5) / (18.5 - 16.5)
            night_factor = 0.15 * f  # с 0.0 до 0.15
            return ("day", "sunset", f, night_factor)
        elif 18.5 <= h < 21.0:
            # Переход: Закат -> Ночь
            f = (h - 18.5) / (21.0 - 18.5)
            night_factor = 0.15 + 0.85 * f  # с 0.15 до 1.0
            return ("sunset", "night", f, night_factor)
        else:  # 21.0 <= h < 24.0
            # Наступление глубокой ночи
            return ("night", None, 0.0, 1.0)

    def get_night_factor(self) -> float:
        """Степень ночной темноты (0.0 - день, 1.0 - ночь)."""
        _, _, _, night_factor = self.get_phase_blending()
        return night_factor

    def update(self, dt: float) -> None:
        """Обновление анимационного времени и метеоров."""
        self.anim_time += dt

        night_factor = self.get_night_factor()
        if night_factor > 0.15:
            self._next_shooting_star_timer -= dt
            if self._next_shooting_star_timer <= 0:
                self._spawn_shooting_star()
                self._next_shooting_star_timer = random.uniform(8.0, 24.0)

        for s in self.shooting_stars:
            s.update(dt)
        self.shooting_stars = [s for s in self.shooting_stars if s.is_active]

    def _spawn_shooting_star(self) -> None:
        """Появление падающей звезды в открытом небе."""
        # Выбираем левое или правое открытое небо
        if random.random() < 0.5:
            start_x = random.uniform(0.05, 0.28)
            angle = random.uniform(0.5, 0.85)  # вправо-вниз
        else:
            start_x = random.uniform(0.72, 0.95)
            angle = random.uniform(2.3, 2.65)  # влево-вниз

        start_y = random.uniform(0.04, 0.22)
        length = random.uniform(130.0, 230.0)
        speed = random.uniform(1.3, 2.2)
        self.shooting_stars.append(ShootingStar(start_x, start_y, length, angle, speed))

    def get_sun_position(self, width: float, height: float) -> Tuple[float, float, float]:
        """
        Координаты Солнца (x, y) и высота над горизонтом (0.0..1.0).
        Солнце скользит по верхушке кроны Баньяна, едва касаясь её:
        - Восход (05:39 .. 06:10): восходит у самого правого края над горами (x ~ 0.95, y ~ 0.51).
        - Полдень (12:00): сидит на макушке кроны по центру (x ~ 0.50, y ~ 0.012).
        - Закат (18:25 .. 18:45): садится у самого левого края за горами (x ~ 0.05, y ~ 0.51).
        """
        h = self.current_hour
        # Световой день: с 05:39 (5.65h) до 18:45 (18.75h)
        if 5.65 <= h <= 18.75:
            progress = (h - 5.65) / (18.75 - 5.65)  # 0.0 .. 1.0 (восход -> закат)
            # Движение строго с востока на запад от правого края к левому
            x_norm = 0.96 - 0.92 * progress
            y_norm = _get_canopy_sky_y(x_norm)
            elevation = math.sin(math.pi * progress)
            return width * x_norm, height * y_norm, elevation
        return width * 0.5, height * 1.5, 0.0

    def get_moon_position(self, width: float, height: float) -> Tuple[float, float, float]:
        """
        Координаты Луны (x, y) и высота (0.0..1.0).
        Луна скользит по верхушке кроны Баньяна, едва касаясь её в ночном небе.
        """
        h = self.current_hour
        # Цикл ночной видимости: с 18:45 (18.75h) до 05:39 (5.65h следующего дня) — ровно 10.9 часов
        moon_h = (h - 18.75) % 24.0
        if moon_h <= 10.9:
            progress = moon_h / 10.9  # 0.0 .. 1.0 (восход -> заход)
            x_norm = 0.96 - 0.92 * progress
            y_norm = _get_canopy_sky_y(x_norm)
            elevation = math.sin(math.pi * progress)
            return width * x_norm, height * y_norm, elevation
        return width * 0.5, height * 1.5, 0.0

    def render_stars_and_meteors(self, painter: QPainter, width: int, height: int, night_factor: float) -> None:
        """Отрисовка мерцающих звёзд и метеоров в ночном небе."""
        if night_factor <= 0.03:
            return

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)

        # 1. Живые мерцающие звёзды
        for star in self.stars:
            flicker = 0.60 + 0.40 * math.sin(self.anim_time * star.flicker_freq + star.phase)
            alpha = int(star.base_alpha * night_factor * flicker)
            if alpha <= 6:
                continue

            star_x = star.u * width
            star_y = star.v * height

            # Ядро звезды
            painter.setBrush(QColor(245, 250, 255, alpha))
            painter.drawEllipse(QPointF(star_x, star_y), star.size, star.size)

            # Ореол сияния для крупных звёзд
            if star.size > 1.8:
                halo_alpha = int(alpha * 0.32)
                painter.setBrush(QColor(190, 220, 255, halo_alpha))
                painter.drawEllipse(QPointF(star_x, star_y), star.size * 2.3, star.size * 2.3)

        # 2. Падающие звёзды (метеоры)
        for ms in self.shooting_stars:
            progress = ms.progress
            head_x = (ms.x * width) + math.cos(ms.angle) * (ms.length * progress)
            head_y = (ms.y * height) + math.sin(ms.angle) * (ms.length * progress)

            tail_len = ms.length * 0.45
            tail_x = head_x - math.cos(ms.angle) * tail_len
            tail_y = head_y - math.sin(ms.angle) * tail_len

            tail_grad = QLinearGradient(tail_x, tail_y, head_x, head_y)
            tail_grad.setColorAt(0.0, QColor(255, 255, 255, 0))
            tail_grad.setColorAt(0.7, QColor(200, 235, 255, int(180 * (1.0 - progress) * night_factor)))
            tail_grad.setColorAt(1.0, QColor(255, 255, 255, int(255 * (1.0 - progress) * night_factor)))

            pen = painter.pen()
            pen.setBrush(tail_grad)
            pen.setWidthF(1.8)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.drawLine(QPointF(tail_x, tail_y), QPointF(head_x, head_y))

        painter.restore()

    def get_lunar_phase(self) -> Tuple[float, str]:
        """
        Вычисляет реальную астрономическую фазу Луны (0.0 .. 1.0) и её название.
        0.0 / 1.0 - Новолуние
        0.25      - Первая четверть (освещена справа)
        0.50      - Полнолуние (полный диск)
        0.75      - Последняя четверть (освещена слева)
        """
        ref_new_moon = datetime(2024, 1, 11, 11, 57, tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        diff_days = (now - ref_new_moon).total_seconds() / 86400.0
        synodic_month = 29.53058867
        phase = (diff_days % synodic_month) / synodic_month

        if phase < 0.03 or phase > 0.97:
            name = "Новолуние"
        elif phase < 0.22:
            name = "Молодая Луна (растущий серп)"
        elif phase < 0.28:
            name = "Первая четверть"
        elif phase < 0.47:
            name = "Прибывающая Луна"
        elif phase < 0.53:
            name = "Полнолуние"
        elif phase < 0.72:
            name = "Убывающая Луна"
        elif phase < 0.78:
            name = "Последняя четверть"
        else:
            name = "Старая Луна (убывающий серп)"

        return phase, name

    def _build_moon_phase_path(self, cx: float, cy: float, r: float, phase: float) -> QPainterPath:
        """Построение точной геометрической маски освещённой части Луны в 2D."""
        path = QPainterPath()
        phase = phase % 1.0

        # Полнолуние — полный круг
        if 0.48 <= phase <= 0.52:
            path.addEllipse(QPointF(cx, cy), r, r)
            return path

        # Новолуние — невидимый диск
        if phase <= 0.02 or phase >= 0.98:
            return path

        if phase < 0.5:
            # Растущая Луна: освещён правый полукруг
            path.moveTo(cx, cy - r)
            path.arcTo(QRectF(cx - r, cy - r, 2 * r, 2 * r), 90, -180)

            # Терминатор от низа (cx, cy + r) к верху (cx, cy - r)
            term_x_radius = r * math.cos(math.pi * (phase / 0.5))
            if term_x_radius >= 0:
                # Растущий серп
                path.arcTo(QRectF(cx - term_x_radius, cy - r, 2 * term_x_radius, 2 * r), 270, 180)
            else:
                # Растущая горбатая
                abs_rx = abs(term_x_radius)
                path.arcTo(QRectF(cx - abs_rx, cy - r, 2 * abs_rx, 2 * r), 270, -180)
        else:
            # Убывающая Луна: освещён левый полукруг
            path.moveTo(cx, cy - r)
            path.arcTo(QRectF(cx - r, cy - r, 2 * r, 2 * r), 90, 180)

            rel_phase = (phase - 0.5) / 0.5
            term_x_radius = r * math.cos(math.pi * rel_phase)
            if term_x_radius >= 0:
                # Убывающая горбатая
                abs_rx = abs(term_x_radius)
                path.arcTo(QRectF(cx - abs_rx, cy - r, 2 * abs_rx, 2 * r), 270, 180)
            else:
                # Убывающий серп
                abs_rx = abs(term_x_radius)
                path.arcTo(QRectF(cx - abs_rx, cy - r, 2 * abs_rx, 2 * r), 270, -180)

        path.closeSubpath()
        return path

    def render_sun(self, painter: QPainter, width: int, height: int) -> None:
        """Отрисовка динамического Солнца с адаптивным спектром и мягким ореолом Bloom."""
        sun_x, sun_y, elevation = self.get_sun_position(width, height)
        if elevation <= 0.01:
            return

        h = self.current_hour
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)

        # Вычисление спектра в зависимости от фазы суток
        if h < 7.5:
            # Рассвет: тёплое персиково-золотистое ядро
            core_col = QColor(255, 240, 215, int(255 * elevation))
            inner_col = QColor(255, 180, 80, int(190 * elevation))
            outer_col = QColor(255, 100, 50, 0)
            flare_col = QColor(255, 160, 60, int(85 * elevation))
        elif h > 16.5:
            # Закат: пламенное медово-рубиновое солнце
            t = min(1.0, max(0.0, (h - 16.5) / 2.5))
            r = int(255)
            g = int(230 - 110 * t)
            b = int(160 - 130 * t)
            core_col = QColor(r, g, b, int(255 * elevation))
            inner_col = QColor(255, 120, 40, int(210 * elevation))
            outer_col = QColor(220, 50, 30, 0)
            flare_col = QColor(255, 90, 40, int(95 * elevation))
        else:
            # Зенит / ясный полдень: сияющее бело-золотое солнце
            core_col = QColor(255, 255, 245, 255)
            inner_col = QColor(255, 240, 160, int(185 * elevation))
            outer_col = QColor(255, 215, 120, 0)
            flare_col = QColor(255, 235, 170, int(75 * elevation))

        sun_radius = max(18.0, width * 0.017)

        # 1. Внешний мягкий рассеянный ореол (Atmospheric Bloom)
        bloom_rad = sun_radius * 8.5
        bloom_grad = QRadialGradient(QPointF(sun_x, sun_y), bloom_rad)
        bloom_grad.setColorAt(0.0, flare_col)
        bloom_grad.setColorAt(0.40, QColor(flare_col.red(), flare_col.green(), flare_col.blue(), flare_col.alpha() // 3))
        bloom_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(bloom_grad)
        painter.drawEllipse(QPointF(sun_x, sun_y), bloom_rad, bloom_rad)

        # 2. Яркая корона светила
        corona_rad = sun_radius * 2.8
        corona_grad = QRadialGradient(QPointF(sun_x, sun_y), corona_rad)
        corona_grad.setColorAt(0.0, inner_col)
        corona_grad.setColorAt(0.55, QColor(inner_col.red(), inner_col.green(), inner_col.blue(), inner_col.alpha() // 2))
        corona_grad.setColorAt(1.0, outer_col)
        painter.setBrush(corona_grad)
        painter.drawEllipse(QPointF(sun_x, sun_y), corona_rad, corona_rad)

        # 3. Ослепительно яркое ядро светила
        core_grad = QRadialGradient(QPointF(sun_x, sun_y), sun_radius)
        core_grad.setColorAt(0.0, core_col)
        core_grad.setColorAt(0.70, inner_col)
        core_grad.setColorAt(1.0, QColor(inner_col.red(), inner_col.green(), inner_col.blue(), 120))
        painter.setBrush(core_grad)
        painter.drawEllipse(QPointF(sun_x, sun_y), sun_radius, sun_radius)

        painter.restore()

    def render_moon(self, painter: QPainter, width: int, height: int, night_factor: float) -> None:
        """Отрисовка Луны с реальной астрономической фазой, пепельным светом и серебристой короной."""
        if night_factor <= 0.05:
            return

        moon_x, moon_y, elevation = self.get_moon_position(width, height)
        if elevation <= 0.01:
            return

        phase, _ = self.get_lunar_phase()
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)

        moon_radius = max(16.0, width * 0.015)
        moon_alpha = int(255 * night_factor * elevation)

        # 1. Серебристая лунная корона (мягкое сияние в ночном небе)
        corona_rad = moon_radius * 4.4
        corona_grad = QRadialGradient(QPointF(moon_x, moon_y), corona_rad)
        corona_grad.setColorAt(0.0, QColor(215, 235, 255, int(95 * night_factor * elevation)))
        corona_grad.setColorAt(0.40, QColor(170, 205, 245, int(35 * night_factor * elevation)))
        corona_grad.setColorAt(1.0, QColor(15, 25, 45, 0))
        painter.setBrush(corona_grad)
        painter.drawEllipse(QPointF(moon_x, moon_y), corona_rad, corona_rad)

        # 2. Пепельный свет (Earthshine) — тонкое таинственное очертание теневой стороны Луны
        painter.setBrush(QColor(18, 28, 48, int(150 * night_factor * elevation)))
        painter.drawEllipse(QPointF(moon_x, moon_y), moon_radius, moon_radius)

        # 3. Освещённая часть Луны с учётом реальной фазы
        painter.save()
        moon_path = self._build_moon_phase_path(moon_x, moon_y, moon_radius, phase)
        if not moon_path.isEmpty():
            painter.setClipPath(moon_path)

            # Жемчужный градиент лунного диска
            disk_grad = QRadialGradient(QPointF(moon_x - moon_radius * 0.2, moon_y - moon_radius * 0.2), moon_radius * 1.2)
            disk_grad.setColorAt(0.0, QColor(250, 252, 255, moon_alpha))
            disk_grad.setColorAt(0.70, QColor(222, 234, 250, moon_alpha))
            disk_grad.setColorAt(1.0, QColor(190, 210, 235, moon_alpha))
            painter.setBrush(disk_grad)
            painter.drawEllipse(QPointF(moon_x, moon_y), moon_radius, moon_radius)

            # Лунные моря (мягкие текстурные пятна)
            painter.setBrush(QColor(160, 182, 210, int(65 * night_factor * elevation)))
            painter.drawEllipse(QPointF(moon_x + moon_radius * 0.15, moon_y - moon_radius * 0.2), moon_radius * 0.35, moon_radius * 0.28)
            painter.drawEllipse(QPointF(moon_x - moon_radius * 0.2, moon_y + moon_radius * 0.15), moon_radius * 0.32, moon_radius * 0.25)
            painter.drawEllipse(QPointF(moon_x + moon_radius * 0.1, moon_y + moon_radius * 0.3), moon_radius * 0.22, moon_radius * 0.20)

        painter.restore()
        painter.restore()
