"""
Обитатели живого мира (CreaturesEngine).
Парящие птицы в поднебесье, биолюминесцентные светлячки (искры совести) у корней Древа,
благородный лесной олень на поляне и вольные странники на дальней тропе.
"""

from __future__ import annotations

import math
import random
from typing import List

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QRadialGradient


class Bird:
    """Парящая птица в поднебесье (ласточка / стриж / сокол)."""

    def __init__(self, x: float, y: float, speed_x: float, speed_y: float, scale: float = 1.0) -> None:
        self.x = x
        self.y = y
        self.speed_x = speed_x
        self.speed_y = speed_y
        self.scale = scale
        self.wing_phase = random.uniform(0.0, math.tau)
        self.wing_freq = random.uniform(4.5, 7.0)

    def update(self, dt: float, width: float, height: float) -> None:
        self.x += self.speed_x * dt
        self.y += self.speed_y * dt + math.sin(self.wing_phase * 0.5) * 4.0 * dt
        self.wing_phase += self.wing_freq * dt

        # Если улетела за правый край, возвращаем слева в высоком небе
        if self.x > width + 80:
            self.x = -70
            self.y = random.uniform(height * 0.04, height * 0.32)
            self.speed_x = random.uniform(42.0, 78.0)

    def draw(self, painter: QPainter) -> None:
        """Отрисовка силуэта птицы с взмахом крыльев."""
        sc = self.scale
        wing_span = 14.0 * sc
        flap = math.sin(self.wing_phase) * 6.5 * sc

        path = QPainterPath()
        path.moveTo(self.x - wing_span, self.y - flap)
        path.quadTo(self.x - wing_span * 0.45, self.y - flap * 0.5 - 2 * sc, self.x, self.y)
        path.quadTo(self.x + wing_span * 0.45, self.y - flap * 0.5 - 2 * sc, self.x + wing_span, self.y - flap)

        painter.save()
        pen = QPen(QColor(25, 20, 35, 180))
        pen.setWidthF(1.8 * sc)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
        painter.restore()


class Firefly:
    """Светлячок (искра совести) — биолюминесцентная частица у корней Древа."""

    def __init__(self, u: float, v: float) -> None:
        self.u = u                      # Нормализованная координата X [0.05 .. 0.95]
        self.v = v                      # Нормализованная координата Y [0.55 .. 0.96]
        self.speed_u = random.uniform(-0.012, 0.012)
        self.speed_v = random.uniform(-0.010, 0.010)
        self.phase = random.uniform(0.0, math.tau)
        self.pulse_freq = random.uniform(1.2, 3.2)
        self.radius = random.uniform(3.5, 6.5)
        self.color_type = random.choice(["gold", "emerald", "cyan"])

    def update(self, dt: float) -> None:
        self.phase += self.pulse_freq * dt
        self.u += (self.speed_u + math.sin(self.phase * 0.7) * 0.014) * dt
        self.v += (self.speed_v + math.cos(self.phase * 0.9) * 0.011) * dt

        # Ограничиваем поляной и корнями
        self.u = max(0.02, min(0.98, self.u))
        self.v = max(0.55, min(0.96, self.v))


class Deer:
    """Благородный лесной олень, мирно щиплющий траву на изумрудной поляне слева."""

    def __init__(self, start_x: float, v: float = 0.74, speed: float = 11.0, is_grazing: bool = False) -> None:
        self.x = start_x
        self.v = v # Относительная высота на поляне
        self.speed = speed
        self.walk_phase = random.uniform(0.0, math.tau)
        self.is_grazing = is_grazing
        self.graze_timer = random.uniform(3.5, 8.0)
        self.is_active = True
        self.scale = 0.58

    def update(self, dt: float, width: float) -> None:
        self.graze_timer -= dt
        if self.graze_timer <= 0:
            self.is_grazing = not self.is_grazing
            self.graze_timer = random.uniform(4.0, 9.0)

        if not self.is_grazing:
            self.x += self.speed * dt
            self.walk_phase += dt * 3.5
        else:
            self.walk_phase += dt * 0.8

        if self.x > width + 120:
            self.is_active = False

    def draw(self, painter: QPainter, height: float) -> None:
        """Отрисовка элегантного силуэта оленя с ветвистыми рогами."""
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(22, 18, 28, 225))

        px = self.x
        py = self.v * height
        sc = self.scale * (height / 800.0) # Адаптивный масштаб к экрану

        if not self.is_grazing:
            bob = math.sin(self.walk_phase * 2.0) * 1.5 * sc
            head_dip = 0.0
            leg_f1 = math.sin(self.walk_phase) * 6.0 * sc
            leg_f2 = -leg_f1
            leg_b1 = math.cos(self.walk_phase) * 5.0 * sc
            leg_b2 = -leg_b1
        else:
            bob = 0.0
            head_dip = 16.0 * sc
            leg_f1, leg_f2, leg_b1, leg_b2 = 0.0, 0.0, 0.0, 0.0

        # Тело оленя
        body = QPainterPath()
        body.moveTo(px - 22 * sc, py - 12 * sc + bob)
        body.quadTo(px, py - 18 * sc + bob, px + 18 * sc, py - 10 * sc + bob)
        body.quadTo(px + 22 * sc, py + 4 * sc + bob, px + 14 * sc, py + 8 * sc + bob)
        body.quadTo(px, py + 10 * sc + bob, px - 20 * sc, py + 6 * sc + bob)
        body.quadTo(px - 26 * sc, py - 4 * sc + bob, px - 22 * sc, py - 12 * sc + bob)
        painter.drawPath(body)

        # Шея и голова
        neck = QPainterPath()
        neck.moveTo(px + 14 * sc, py - 10 * sc + bob)
        neck.quadTo(px + 20 * sc, py - 26 * sc + bob + head_dip, px + 26 * sc, py - 34 * sc + bob + head_dip)
        neck.lineTo(px + 34 * sc, py - 32 * sc + bob + head_dip)
        neck.quadTo(px + 24 * sc, py - 18 * sc + bob + head_dip, px + 16 * sc, py + 2 * sc + bob)
        neck.closeSubpath()
        painter.drawPath(neck)

        # Уши
        painter.drawEllipse(QPointF(px + 23 * sc, py - 37 * sc + bob + head_dip), 3 * sc, 6 * sc)

        # Ветвистые рога
        if not self.is_grazing or head_dip < 10:
            horn_pen = QPen(QColor(22, 18, 28, 225))
            horn_pen.setWidthF(1.5 * sc)
            painter.setPen(horn_pen)
            horns = QPainterPath()
            horns.moveTo(px + 22 * sc, py - 36 * sc + bob + head_dip)
            horns.quadTo(px + 20 * sc, py - 52 * sc + bob + head_dip, px + 14 * sc, py - 62 * sc + bob + head_dip)
            horns.moveTo(px + 21 * sc, py - 44 * sc + bob + head_dip)
            horns.lineTo(px + 28 * sc, py - 54 * sc + bob + head_dip)
            horns.moveTo(px + 17 * sc, py - 52 * sc + bob + head_dip)
            horns.lineTo(px + 22 * sc, py - 60 * sc + bob + head_dip)
            horns.moveTo(px + 20 * sc, py - 36 * sc + bob + head_dip)
            horns.lineTo(px + 12 * sc, py - 48 * sc + bob + head_dip)
            painter.drawPath(horns)
            painter.setPen(Qt.NoPen)

        # Стройные ноги
        painter.setBrush(QColor(22, 18, 28, 225))
        painter.drawRect(px - 18 * sc + leg_b1, py + 4 * sc + bob, 3 * sc, 22 * sc)
        painter.drawRect(px - 12 * sc + leg_b2, py + 4 * sc + bob, 2.8 * sc, 22 * sc)
        painter.drawRect(px + 10 * sc + leg_f1, py + 6 * sc + bob, 2.8 * sc, 20 * sc)
        painter.drawRect(px + 16 * sc + leg_f2, py + 6 * sc + bob, 3 * sc, 20 * sc)

        painter.restore()


class Wanderer:
    """Вольный странник, мирно идущий по дальней тропе с посохом."""

    def __init__(self, start_x: float, v: float = 0.67, speed: float = 10.0) -> None:
        self.x = start_x
        self.v = v
        self.speed = speed
        self.walk_phase = random.uniform(0.0, math.tau)
        self.is_active = True
        self.scale = 0.48

    def update(self, dt: float, width: float) -> None:
        self.x -= self.speed * dt # Неспешный шаг справа налево
        self.walk_phase += dt * 3.2
        if self.x < -90:
            self.is_active = False

    def draw(self, painter: QPainter, height: float) -> None:
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(28, 24, 35, 210))

        px = self.x
        py = self.v * height
        sc = self.scale * (height / 800.0)
        bob = math.sin(self.walk_phase * 2.0) * 1.4 * sc

        # Капюшон странника
        painter.drawEllipse(QPointF(px, py - 42 * sc + bob), 5.5 * sc, 6.5 * sc)

        # Развевающийся плащ
        cloak = QPainterPath()
        cloak.moveTo(px - 6 * sc, py - 35 * sc + bob)
        cloak.lineTo(px + 6 * sc, py - 35 * sc + bob)
        cloak.lineTo(px + 9 * sc, py + 3 * sc + bob)
        cloak.lineTo(px - 11 * sc, py + 2 * sc + bob)
        cloak.closeSubpath()
        painter.drawPath(cloak)

        # Ноги в шаге
        leg = math.sin(self.walk_phase) * 3.5 * sc
        painter.drawRect(px - 5 * sc + leg, py + 2 * sc + bob, 2.8 * sc, 15 * sc)
        painter.drawRect(px + 2 * sc - leg, py + 2 * sc + bob, 2.8 * sc, 15 * sc)

        # Дорожный посох
        pen_staff = QPen(QColor(35, 30, 42, 230))
        pen_staff.setWidthF(1.5 * sc)
        painter.setPen(pen_staff)
        staff_x = px - 8 * sc
        painter.drawLine(QPointF(staff_x, py - 46 * sc + bob), QPointF(staff_x, py + 17 * sc))

        painter.restore()


class CreaturesEngine:
    """Управление живыми обитателями поляны: птицы, светлячки, олени и странники."""

    def __init__(self) -> None:
        self.anim_time: float = 0.0

        # Стая парящих ласточек в поднебесье
        self.birds: list[Bird] = [
            Bird(x=180, y=85,  speed_x=54.0, speed_y=-1.5, scale=1.0),
            Bird(x=130, y=110, speed_x=49.0, speed_y=-1.0, scale=0.85),
            Bird(x=95,  y=95,  speed_x=56.0, speed_y=-2.0, scale=0.92),
            Bird(x=210, y=125, speed_x=51.0, speed_y=-1.2, scale=0.78),
        ]

        # 36 биолюминесцентных светлячков
        rnd = random.Random(77)
        self.fireflies: list[Firefly] = [
            Firefly(rnd.uniform(0.06, 0.94), rnd.uniform(0.58, 0.95))
            for _ in range(36)
        ]

        # 1 олень мирно щиплет травку на изумрудной поляне слева
        self.deer: list[Deer] = [
            Deer(start_x=220.0, v=0.74, speed=10.0, is_grazing=True)
        ]
        self._next_deer_timer = random.uniform(15.0, 30.0)

        # 1 путник идет по дальней тропе
        self.wanderers: list[Wanderer] = [
            Wanderer(start_x=780.0, v=0.67, speed=9.5)
        ]
        self._next_wanderer_timer = random.uniform(25.0, 45.0)

    def update(self, dt: float, width: float, height: float) -> None:
        self.anim_time += dt

        for b in self.birds:
            b.update(dt, width, height)

        for ff in self.fireflies:
            ff.update(dt)

        self._next_deer_timer -= dt
        if self._next_deer_timer <= 0:
            self.deer.append(Deer(start_x=-60.0, v=random.uniform(0.72, 0.77), speed=random.uniform(9.0, 14.0)))
            self._next_deer_timer = random.uniform(30.0, 60.0)

        self._next_wanderer_timer -= dt
        if self._next_wanderer_timer <= 0:
            self.wanderers.append(Wanderer(start_x=width + 60.0, v=random.uniform(0.66, 0.68), speed=random.uniform(8.0, 12.0)))
            self._next_wanderer_timer = random.uniform(40.0, 80.0)

        for d in self.deer:
            d.update(dt, width)
        self.deer = [d for d in self.deer if d.is_active]

        for w in self.wanderers:
            w.update(dt, width)
        self.wanderers = [w for w in self.wanderers if w.is_active]

    def render_birds(self, painter: QPainter) -> None:
        """Отрисовка птиц в высоком небе."""
        for bird in self.birds:
            bird.draw(painter)

    def render_wildlife_and_wanderers(self, painter: QPainter, height: float) -> None:
        """Отрисовка оленей и странников на поляне."""
        for wanderer in self.wanderers:
            wanderer.draw(painter, height)
        for deer in self.deer:
            deer.draw(painter, height)

    def render_fireflies(self, painter: QPainter, width: int, height: int, night_factor: float) -> None:
        """Отрисовка светлячков (искр совести), светящихся в сумерках и ночью."""
        if night_factor <= 0.08:
            return

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)

        for ff in self.fireflies:
            pulse = 0.5 + 0.5 * math.sin(ff.phase)
            alpha = int(220 * night_factor * pulse)
            if alpha <= 8:
                continue

            fx = ff.u * width
            fy = ff.v * height

            if ff.color_type == "emerald":
                core = QColor(160, 255, 180, alpha)
                halo = QColor(60, 240, 120, int(alpha * 0.45))
            elif ff.color_type == "cyan":
                core = QColor(180, 245, 255, alpha)
                halo = QColor(60, 210, 255, int(alpha * 0.45))
            else: # gold
                core = QColor(255, 245, 170, alpha)
                halo = QColor(255, 200, 60, int(alpha * 0.45))

            grad = QRadialGradient(fx, fy, ff.radius * 2.5)
            grad.setColorAt(0.0, core)
            grad.setColorAt(0.45, halo)
            grad.setColorAt(1.0, QColor(0, 0, 0, 0))

            painter.setBrush(grad)
            painter.drawEllipse(QPointF(fx, fy), ff.radius * 2.5, ff.radius * 2.5)

            painter.setBrush(core)
            painter.drawEllipse(QPointF(fx, fy), ff.radius * 0.45, ff.radius * 0.45)

        painter.restore()
