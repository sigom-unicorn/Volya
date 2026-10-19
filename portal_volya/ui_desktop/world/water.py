"""
Водный двигатель живого мира (WaterStreamEngine).
Живой лесной ручей на поляне перед Великим Баньяном.
Гармонично накладывается на природную реку 4K-картин:
живая рябь, струи течения, мерцающие солнечные и лунные блики на перекатах,
плывущие лепестки и нежная утренняя речная дымка.
"""

from __future__ import annotations

import math
import random
from typing import List, Tuple

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen


class FloatingPetal:
    """Плывущий по течению осенний лист или лепесток лотоса."""

    def __init__(self, t: float = 0.0) -> None:
        self.t = t                      # Прогресс вдоль ручья [0.0 .. 1.0]
        self.speed = random.uniform(0.045, 0.080)
        self.wobble_phase = random.uniform(0.0, math.tau)
        self.lane_offset = random.uniform(-0.35, 0.35)
        self.color = random.choice([
            QColor(245, 160, 50, 220),  # Золотой лист
            QColor(220, 85, 60, 210),   # Багряный кленовый
            QColor(250, 215, 80, 225),  # Янтарный
            QColor(245, 195, 215, 205), # Лепесток кувшинки / лотоса
        ])

    def update(self, dt: float) -> None:
        self.t += dt * self.speed
        if self.t > 1.05:
            self.t = 0.0
            self.lane_offset = random.uniform(-0.35, 0.35)
            self.wobble_phase = random.uniform(0.0, math.tau)


class RiverGlint:
    """Мерцающий блик солнца/луны на гребне переката."""

    def __init__(self, t: float, lane: float, size: float, freq: float) -> None:
        self.t = t
        self.lane = lane
        self.size = size
        self.freq = freq
        self.phase = random.uniform(0.0, math.tau)


class WaterStreamEngine:
    """Моделирование динамики лесной реки, гармонирующей с 4K-ландшафтом."""

    def __init__(self) -> None:
        self.anim_time: float = 0.0
        self.petals: list[FloatingPetal] = [
            FloatingPetal(t=0.08),
            FloatingPetal(t=0.32),
            FloatingPetal(t=0.58),
            FloatingPetal(t=0.79),
            FloatingPetal(t=0.94),
        ]

        # 36 детерминированных позиций мерцающих бликов на перекатах среди камней
        rnd = random.Random(777)
        self.glints: list[RiverGlint] = []
        for _ in range(36):
            self.glints.append(
                RiverGlint(
                    t=rnd.uniform(0.05, 0.98),
                    lane=rnd.uniform(-0.38, 0.38),
                    size=rnd.uniform(1.8, 4.2),
                    freq=rnd.uniform(2.5, 6.0),
                )
            )

    def update(self, dt: float) -> None:
        self.anim_time += dt
        for p in self.petals:
            p.update(dt)

    def _get_stream_point(self, t: float, width: float, height: float) -> Tuple[float, float, float]:
        """
        Точная кубическая траектория природной реки на 4K-картинах Великого Баньяна.
        Исток реки виден у горизонта справа от ствола (0.69*w, 0.655*h),
        река огибает поляну, течёт через валуны и пороги,
        расширяясь к нижнему правому углу (0.97*w, 1.02*h).
        """
        # Кубический сплайн, точно повторяющий изгибы реки на картине
        cx = width * (0.69 + 0.35 * t - 0.28 * (t ** 2) + 0.20 * (t ** 3))
        cy = height * (0.655 + 0.17 * t + 0.155 * (t ** 2))
        # Ширина водной глади в перспективе
        sw = width * (0.028 + 0.095 * (t ** 1.2))
        return cx, cy, sw

    def _sample_stream(self, width: float, height: float, steps: int = 45) -> list[Tuple[float, float, float, float, float]]:
        """Возвращает список точек траектории: (cx, cy, nx, ny, sw)."""
        data: list[Tuple[float, float, float, float, float]] = []
        for i in range(steps + 1):
            t = i / float(steps)
            cx, cy, sw = self._get_stream_point(t, width, height)

            dt = 0.015
            x_next, y_next, _ = self._get_stream_point(min(1.0, t + dt), width, height)
            x_prev, y_prev, _ = self._get_stream_point(max(0.0, t - dt), width, height)

            dx = x_next - x_prev
            dy = y_next - y_prev
            seg_len = math.hypot(dx, dy)
            if seg_len < 0.001:
                nx, ny = 0.0, 1.0
            else:
                # Вектор нормали поперёк течения
                nx = -dy / seg_len
                ny = dx / seg_len

            data.append((cx, cy, nx, ny, sw))
        return data

    def render_stream(self, painter: QPainter, width: int, height: int, current_hour: float, night_factor: float) -> None:
        """
        Деликатная отрисовка живой воды поверх 4K полотна:
        динамические струи течения, блики на порогах, плывущие лепестки и речная дымка.
        """
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        stream_data = self._sample_stream(width, height, steps=45)
        t_flow = self.anim_time * 2.2

        # Цвета динамики воды в зависимости от времени суток
        if night_factor > 0.5:
            # Ночь: лунные серебряные блики, мерцание холодного сапфира
            c_shimmer = QColor(220, 240, 255, 190)
            c_streak = QColor(140, 180, 230, 40)
            mist_alpha = int(45 * night_factor)
            mist_color = QColor(160, 190, 230, mist_alpha)
        elif 16.5 < current_hour <= 19.5:
            # Закат: янтарно-золотистые блики, коралловые струи
            factor = (current_hour - 16.5) / 3.0
            c_shimmer = QColor(255, 230, 160, 220)
            c_streak = QColor(255, 180, 120, 55)
            mist_alpha = int(40 * factor)
            mist_color = QColor(240, 190, 160, mist_alpha)
        elif 5.0 <= current_hour < 8.0:
            # Рассвет: жемчужно-розовые переливы, утренний туман над водой
            dawn_factor = (8.0 - current_hour) / 3.0
            c_shimmer = QColor(255, 240, 225, 205)
            c_streak = QColor(240, 195, 210, 50)
            mist_alpha = int(60 * dawn_factor)
            mist_color = QColor(245, 225, 230, mist_alpha)
        else:
            # День: кристально-солнечные искры, бирюзовая рябь
            c_shimmer = QColor(255, 255, 255, 215)
            c_streak = QColor(220, 245, 255, 50)
            mist_color = QColor(255, 255, 255, 0)

        # -------------------------------------------------------------
        # 1. Стелющаяся утренняя/вечерняя речная дымка (Mist over water)
        # -------------------------------------------------------------
        if mist_color.alpha() > 5:
            mist_path = QPainterPath()
            l_mist: list[QPointF] = []
            r_mist: list[QPointF] = []

            for i, (cx, cy, nx, ny, sw) in enumerate(stream_data):
                t = i / float(len(stream_data) - 1)
                mist_w = sw * (0.8 + 0.3 * math.sin(t * 8.0 + self.anim_time * 0.5))
                # Небольшой подъём тумана вверх
                mist_y_offset = -sw * 0.25
                l_mist.append(QPointF(cx - nx * mist_w, cy + mist_y_offset - ny * mist_w * 0.3))
                r_mist.append(QPointF(cx + nx * mist_w, cy + mist_y_offset + ny * mist_w * 0.3))

            mist_path.moveTo(l_mist[0])
            for pt in l_mist[1:]:
                mist_path.lineTo(pt)
            for pt in reversed(r_mist):
                mist_path.lineTo(pt)
            mist_path.closeSubpath()

            painter.setPen(Qt.NoPen)
            painter.setBrush(mist_color)
            painter.drawPath(mist_path)

        # -------------------------------------------------------------
        # 2. Живые продольные струи течения (Current Streaks)
        # -------------------------------------------------------------
        pen_streak = QPen(c_streak)
        pen_streak.setCapStyle(Qt.RoundCap)

        for lane_idx, lane_offset in enumerate([-0.25, 0.0, 0.25]):
            streak_path = QPainterPath()
            pen_streak.setWidthF(1.2 + 1.2 * (lane_idx == 1))
            painter.setPen(pen_streak)
            painter.setBrush(Qt.NoBrush)

            started = False
            for i, (cx, cy, nx, ny, sw) in enumerate(stream_data):
                t = i / float(len(stream_data) - 1)
                wave = math.sin(t * 18.0 - t_flow + lane_idx * 1.5) * (sw * 0.08)
                sx = cx + nx * (lane_offset * sw * 0.5 + wave)
                sy = cy + ny * (lane_offset * sw * 0.5 + wave)

                if not started:
                    streak_path.moveTo(sx, sy)
                    started = True
                else:
                    streak_path.lineTo(sx, sy)

            painter.drawPath(streak_path)

        # -------------------------------------------------------------
        # 3. Мерцающие солнечные/лунные блики на речных порогах
        # -------------------------------------------------------------
        painter.setPen(Qt.NoPen)
        for glint in self.glints:
            cx, cy, sw = self._get_stream_point(glint.t, width, height)
            pulse = math.sin(self.anim_time * glint.freq + glint.phase)
            if pulse > 0.3:
                alpha = int(c_shimmer.alpha() * ((pulse - 0.3) / 0.7))
                gx = cx + glint.lane * sw
                gy = cy + math.sin(glint.t * 12.0) * (sw * 0.1)

                r_x = glint.size * (0.8 + 1.2 * glint.t) * (0.8 + 0.4 * pulse)
                r_y = r_x * 0.35 # Сплюснутый по горизонтали блик на воде

                painter.setBrush(QColor(c_shimmer.red(), c_shimmer.green(), c_shimmer.blue(), alpha))
                painter.drawEllipse(QPointF(gx, gy), r_x, r_y)

        # -------------------------------------------------------------
        # 4. Плывущие лепестки и золотые листья по реке
        # -------------------------------------------------------------
        for pet in self.petals:
            cx, cy, sw = self._get_stream_point(pet.t, width, height)
            wobble = math.sin(self.anim_time * 2.8 + pet.wobble_phase) * (sw * 0.15)
            px = cx + pet.lane_offset * (sw * 0.6) + wobble
            py = cy + math.cos(self.anim_time * 2.2 + pet.wobble_phase) * (sw * 0.06)

            p_size = 2.4 + 4.2 * (pet.t ** 0.8)

            # Тень под листом в воде
            painter.setBrush(QColor(0, 0, 0, 35))
            painter.drawEllipse(QPointF(px + 1.0, py + 1.2), p_size * 1.1, p_size * 0.55)

            # Сам плывущий лист/лепесток
            painter.save()
            painter.translate(px, py)
            rot = math.sin(self.anim_time * 1.8 + pet.wobble_phase) * 25.0
            painter.rotate(rot)
            painter.setBrush(pet.color)
            painter.drawEllipse(QPointF(0, 0), p_size, p_size * 0.55)
            painter.restore()

        painter.restore()
