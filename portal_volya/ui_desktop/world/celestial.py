"""
Небесный двигатель живого мира (CelestialEngine).
Суточный ритм планеты: астрономическое время, фазовое смешение 4K-картин,
мерцание ночных созвездий, падающие метеоры и координаты светил для атмосферных лучей.
"""

from __future__ import annotations

from datetime import datetime
import math
import random
from typing import List, Optional, Tuple

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QRadialGradient


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
            night_factor = 1.0 - f * 0.75 # с 1.0 до 0.25
            return ("night", "dawn", f, night_factor)
        elif 6.25 <= h < 8.0:
            # Переход: Рассвет -> Ясный день
            f = (h - 6.25) / (8.0 - 6.25)
            night_factor = 0.25 * (1.0 - f) # с 0.25 до 0.0
            return ("dawn", "day", f, night_factor)
        elif 8.0 <= h < 16.5:
            # Полный ясный день
            return ("day", None, 0.0, 0.0)
        elif 16.5 <= h < 18.75:
            # Переход: День -> Закат
            f = (h - 16.5) / (18.75 - 16.5)
            night_factor = 0.15 * f # с 0.0 до 0.15
            return ("day", "sunset", f, night_factor)
        elif 18.75 <= h < 21.5:
            # Переход: Закат -> Ночь
            f = (h - 18.75) / (21.5 - 18.75)
            night_factor = 0.15 + 0.85 * f # с 0.15 до 1.0
            return ("sunset", "night", f, night_factor)
        else: # 21.5 <= h < 24.0
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
            angle = random.uniform(0.5, 0.85) # вправо-вниз
        else:
            start_x = random.uniform(0.72, 0.95)
            angle = random.uniform(2.3, 2.65) # влево-вниз

        start_y = random.uniform(0.04, 0.22)
        length = random.uniform(130.0, 230.0)
        speed = random.uniform(1.3, 2.2)
        self.shooting_stars.append(ShootingStar(start_x, start_y, length, angle, speed))

    def get_sun_position(self, width: float, height: float) -> Tuple[float, float, float]:
        """
        Координаты Солнца (x, y) и высота над горизонтом (0.0..1.0).
        Согласовано с 4K-картинами:
        Восход (рассвет) — на востоке СПРАВА за горами (x ~ 0.86, y ~ 0.40).
        Полдень (зенит) — в верхней точке над кроной (x ~ 0.50, y ~ 0.12).
        Закат — на западе СЛЕВА за горизонтом (x ~ 0.10, y ~ 0.48).
        """
        h = self.current_hour
        if 5.0 <= h <= 20.0:
            progress = (h - 5.0) / 15.0 # 0.0 .. 1.0 (восход -> закат)
            # Солнце движется справа налево (с востока на запад)
            x = width * (0.86 - 0.76 * progress)
            sin_p = math.sin(math.pi * progress)
            y = height * (0.46 - 0.34 * sin_p)
            elevation = sin_p
            return x, y, elevation
        return width * 0.5, height * 1.5, 0.0

    def get_moon_position(self, width: float, height: float) -> Tuple[float, float, float]:
        """Координаты Луны (x, y) и высота (0.0..1.0)."""
        h = self.current_hour
        moon_h = (h - 19.0) % 24.0
        if moon_h <= 11.5:
            progress = moon_h / 11.5
            sin_p = math.sin(math.pi * progress)
            x = width * (0.16 + 0.68 * progress)
            y = height * (0.40 - 0.24 * sin_p)
            return x, y, sin_p
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
