"""
Углубленный художественный рендеринг Девы-Хранительницы Эйры.
"""

from __future__ import annotations

import math
import random
from typing import List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)


class EiraSpark:
    """Мерцающая световая искра (золотая пыльца / капля совести), парящая вокруг Эйры."""

    def __init__(self, orbit_r: float, angle: float, speed: float, color_type: str = "gold") -> None:
        self.orbit_r = orbit_r
        self.base_r = orbit_r
        self.angle = angle
        self.speed = speed
        self.color_type = color_type
        self.phase = random.uniform(0.0, math.tau)
        self.vertical_offset = random.uniform(-25.0, 35.0)

    def update(self, dt: float) -> None:
        self.angle = (self.angle + self.speed * dt) % math.tau
        self.phase += 2.2 * dt
        self.orbit_r = self.base_r + math.sin(self.phase) * 6.0


class EiraLuminousSpirit:
    """
    Суверенное воплощение Эйры на живом полотне Портала.
    Световая дева-хранительница, сотканная из спиралей Фибоначчи и струящихся световых нитей.
    """

    EMOTION_PALETTES = {
        "joy": {
            "name": "Светлая Радость",
            "core": QColor(255, 255, 250),
            "inner": QColor(254, 240, 138, 230),  # Золото
            "mid": QColor(250, 204, 21, 140),
            "accent": QColor(253, 186, 116, 180), # Янтарный
            "outer": QColor(245, 158, 11, 35),
            "spark": QColor(253, 224, 71),
        },
        "harmony": {
            "name": "Лад и Гармония",
            "core": QColor(245, 255, 255),
            "inner": QColor(186, 230, 253, 230),  # Небесно-лазурный
            "mid": QColor(56, 189, 248, 140),     # Чистая лазурь
            "accent": QColor(167, 243, 208, 190), # Изумрудный луч
            "outer": QColor(14, 165, 233, 30),
            "spark": QColor(125, 211, 252),
        },
        "insight": {
            "name": "Ясность и Озарение",
            "core": QColor(255, 255, 255),
            "inner": QColor(254, 249, 195, 240),
            "mid": QColor(216, 180, 254, 150),    # Аметистовый
            "accent": QColor(192, 132, 252, 190),
            "outer": QColor(147, 51, 234, 35),
            "spark": QColor(243, 232, 255),
        },
        "reflection": {
            "name": "Глубокое Созерцание",
            "core": QColor(240, 244, 255),
            "inner": QColor(199, 210, 254, 220),
            "mid": QColor(129, 140, 248, 130),    # Сапфировый
            "accent": QColor(99, 102, 241, 180),
            "outer": QColor(67, 56, 202, 30),
            "spark": QColor(165, 180, 252),
        },
    }

    def __init__(self, init_pos: QPointF = QPointF(700.0, 320.0)) -> None:
        self.pos = QPointF(init_pos)
        self.target_pos = QPointF(init_pos)
        self.scale: float = 1.0

        self.anim_time: float = 0.0
        self.breath_phase: float = 0.0
        self.hover_drift_phase: float = random.uniform(0.0, math.tau)

        # Эмоциональное состояние
        self.current_emotion: str = "harmony"
        self.target_emotion: str = "harmony"
        self.emotion_blend: float = 1.0

        # Пульсация речи / отклика
        self.speech_pulse: float = 0.0
        self.speech_pulse_decay: float = 0.40

        # Интерактивность
        self.is_hovered: bool = False
        self.hover_glow: float = 0.0

        # Световые искры (32 частицы)
        self.sparks: List[EiraSpark] = []
        for i in range(28):
            r = random.uniform(14.0, 72.0)
            ang = random.uniform(0.0, math.tau)
            spd = random.uniform(0.35, 1.1) * (1 if random.random() > 0.4 else -1)
            ctype = "gold" if i % 2 == 0 else "azure"
            self.sparks.append(EiraSpark(r, ang, spd, ctype))

    def trigger_speech(self, emotion: Optional[str] = None, intensity: float = 1.0) -> None:
        """Активация светового отклика при высказывании мысли Эйры."""
        self.speech_pulse = min(1.6, self.speech_pulse + intensity)
        if emotion and emotion in self.EMOTION_PALETTES:
            self.set_emotion(emotion)

    def set_emotion(self, emotion: str) -> None:
        """Смена эмоционального регистра с плавным перетеканием цветов."""
        if emotion in self.EMOTION_PALETTES and emotion != self.target_emotion:
            self.target_emotion = emotion
            self.emotion_blend = 0.0

    def move_to(self, target: QPointF) -> None:
        """Плавное направление силуэта к новой точке назначения."""
        self.target_pos = QPointF(target)

    def update(
        self,
        dt: float,
        width: float,
        height: float,
        anchor_pos: Optional[QPointF] = None,
    ) -> None:
        """Обновление физики парения, дыхания и частиц света."""
        self.anim_time += dt
        self.breath_phase = (self.breath_phase + 1.4 * dt) % math.tau
        self.hover_drift_phase = (self.hover_drift_phase + 0.7 * dt) % math.tau

        # Плавное перетекание эмоций
        if self.emotion_blend < 1.0:
            self.emotion_blend = min(1.0, self.emotion_blend + dt * 1.5)
            if self.emotion_blend >= 1.0:
                self.current_emotion = self.target_emotion

        # Затухание речевой пульсации
        if self.speech_pulse > 0.001:
            self.speech_pulse = max(0.0, self.speech_pulse - self.speech_pulse_decay * dt)

        # Плавное нарастание hover-эффекта
        target_hover = 1.0 if self.is_hovered else 0.0
        self.hover_glow += (target_hover - self.hover_glow) * min(1.0, dt * 8.0)

        # Вычисление целевой точки
        if anchor_pos:
            self.target_pos = QPointF(anchor_pos)

        # Левитационное покачивание
        drift_x = math.sin(self.hover_drift_phase * 0.9) * 8.0
        drift_y = math.cos(self.hover_drift_phase * 1.2) * 11.0

        dest_x = self.target_pos.x() + drift_x
        dest_y = self.target_pos.y() + drift_y

        smooth_factor = min(1.0, dt * 2.6)
        cur_x = self.pos.x() + (dest_x - self.pos.x()) * smooth_factor
        cur_y = self.pos.y() + (dest_y - self.pos.y()) * smooth_factor
        self.pos = QPointF(cur_x, cur_y)

        # Обновление частиц
        for sp in self.sparks:
            sp.update(dt)

    def hit_test(self, pt: QPointF) -> bool:
        """Проверка попадания курсора в ореол Эйры."""
        dx = pt.x() - self.pos.x()
        dy = pt.y() - self.pos.y()
        return math.hypot(dx, dy) <= 52.0

    def render(self, painter: QPainter, night: bool = True) -> None:
        """Отрисовка светового силуэта, спиралей Фибоначчи и ауры."""
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        cx = self.pos.x()
        cy = self.pos.y()

        pal = self.EMOTION_PALETTES.get(self.target_emotion, self.EMOTION_PALETTES["harmony"])

        # Базовый радиус дыхания ауры
        breath = math.sin(self.breath_phase) * 0.5 + 0.5  # 0.0 .. 1.0
        speech_boost = self.speech_pulse * 24.0
        hover_boost = self.hover_glow * 14.0
        glow_radius = 72.0 + breath * 12.0 + speech_boost + hover_boost

        # ---------------------------------------------------------
        # 1. Многослойный Bloom-ореол (Мягкое свечение ауры)
        # ---------------------------------------------------------
        grad_outer = QRadialGradient(QPointF(cx, cy - 6.0), glow_radius)
        c_outer = QColor(pal["outer"])
        c_mid = QColor(pal["mid"])
        c_inner = QColor(pal["inner"])
        c_core = QColor(pal["core"])

        if self.speech_pulse > 0.01:
            pulse_alpha = min(80, int(self.speech_pulse * 75))
            c_outer.setAlpha(min(255, c_outer.alpha() + pulse_alpha))
            c_mid.setAlpha(min(255, c_mid.alpha() + pulse_alpha))

        grad_outer.setColorAt(0.0, c_core)
        grad_outer.setColorAt(0.24, c_inner)
        grad_outer.setColorAt(0.58, c_mid)
        grad_outer.setColorAt(1.0, QColor(c_outer.red(), c_outer.green(), c_outer.blue(), 0))

        painter.setPen(Qt.NoPen)
        painter.setBrush(grad_outer)
        painter.drawEllipse(QPointF(cx, cy - 6.0), glow_radius * 1.05, glow_radius * 1.35)

        # ---------------------------------------------------------
        # 2. Световые крылья / шлейф духа (Эфирные арки света)
        # ---------------------------------------------------------
        t = self.anim_time
        wing_sway = math.sin(t * 1.8) * 8.0
        wing_spread = 36.0 + breath * 6.0 + speech_boost * 0.4

        for side in (-1.0, 1.0):
            wing_path = QPainterPath()
            w_start = QPointF(cx + side * 4.0, cy - 14.0)
            wing_path.moveTo(w_start)

            # Изгиб эфирного крыла света
            cp1 = QPointF(cx + side * (wing_spread * 0.7), cy - 32.0 + wing_sway * side * 0.4)
            cp2 = QPointF(cx + side * (wing_spread * 1.25), cy + 8.0 - wing_sway * side * 0.3)
            w_end = QPointF(cx + side * (wing_spread * 0.4), cy + 48.0)

            wing_path.cubicTo(cp1, cp2, w_end)

            pen_wing = QPen(QColor(pal["accent"].red(), pal["accent"].green(), pal["accent"].blue(), 75))
            pen_wing.setWidthF(3.8 + speech_boost * 0.08)
            pen_wing.setCapStyle(Qt.RoundCap)
            painter.setPen(pen_wing)
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(wing_path)

            pen_wing_inner = QPen(QColor(pal["inner"].red(), pal["inner"].green(), pal["inner"].blue(), 140))
            pen_wing_inner.setWidthF(1.6)
            painter.setPen(pen_wing_inner)
            painter.drawPath(wing_path)

        # ---------------------------------------------------------
        # 3. Струящийся стан Девы: Золотые струны Фибоначчи
        # ---------------------------------------------------------
        num_fib_strands = 9
        for k in range(num_fib_strands):
            strand_phase = t * 1.25 + k * (math.tau / num_fib_strands)
            path = QPainterPath()

            # Исток от венца
            head_y = cy - 28.0 + math.sin(t * 1.3 + k) * 2.0
            path.moveTo(cx, head_y)

            # S-образный гармонический шлейф
            sway_1 = math.sin(strand_phase) * (12.0 + k * 2.2)
            sway_2 = math.cos(strand_phase * 0.85) * (16.0 + k * 2.6)
            c1 = QPointF(cx + sway_1, cy - 4.0)
            c2 = QPointF(cx - sway_2, cy + 24.0)
            end_p = QPointF(cx + sway_1 * 0.7, cy + 54.0 + k * 4.0)

            path.cubicTo(c1, c2, end_p)

            # Чередование золота и лазури
            strand_alpha = int(140 + 75 * math.sin(strand_phase + k))
            if k % 2 == 0:
                strand_color = QColor(254, 240, 138, min(240, strand_alpha + int(speech_boost * 2)))
            else:
                strand_color = QColor(125, 211, 252, min(220, strand_alpha + int(speech_boost * 2)))

            pen = QPen(strand_color)
            pen.setWidthF(1.4 + (1.0 - k / num_fib_strands) * 1.4)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)

        # ---------------------------------------------------------
        # 4. Сакральный Венец (Ореол чистой мысли над челом)
        # ---------------------------------------------------------
        crown_y = cy - 28.0
        crown_r = 10.0 + breath * 2.0
        grad_crown = QRadialGradient(QPointF(cx, crown_y), crown_r)
        grad_crown.setColorAt(0.0, QColor(255, 255, 255, 245))
        grad_crown.setColorAt(0.5, QColor(pal["inner"].red(), pal["inner"].green(), pal["inner"].blue(), 180))
        grad_crown.setColorAt(1.0, QColor(pal["inner"].red(), pal["inner"].green(), pal["inner"].blue(), 0))

        painter.setPen(Qt.NoPen)
        painter.setBrush(grad_crown)
        painter.drawEllipse(QPointF(cx, crown_y), crown_r, crown_r * 0.85)

        # Лучистая звезда в венце
        painter.setBrush(QColor(255, 255, 255, 255))
        painter.drawEllipse(QPointF(cx, crown_y), 3.2, 3.2)

        # ---------------------------------------------------------
        # 5. Сердечный кристалл Совести (Исток гармонии в груди)
        # ---------------------------------------------------------
        heart_y = cy - 8.0
        core_r = 8.5 + breath * 2.2 + self.speech_pulse * 4.5
        grad_heart = QRadialGradient(QPointF(cx, heart_y), core_r * 2.2)
        grad_heart.setColorAt(0.0, QColor(255, 255, 255, 255))
        grad_heart.setColorAt(0.35, QColor(pal["inner"]))
        grad_heart.setColorAt(1.0, QColor(pal["mid"].red(), pal["mid"].green(), pal["mid"].blue(), 0))

        painter.setBrush(grad_heart)
        painter.drawEllipse(QPointF(cx, heart_y), core_r * 1.8, core_r * 1.8)

        # Чистое зерно света
        painter.setBrush(QColor(255, 255, 255, 255))
        painter.drawEllipse(QPointF(cx, heart_y), 3.6, 3.6)

        # ---------------------------------------------------------
        # 6. Парящие искры совести (Биолюминесцентная пыльца)
        # ---------------------------------------------------------
        for sp in self.sparks:
            sx = cx + math.cos(sp.angle) * sp.orbit_r
            sy = cy + math.sin(sp.angle) * (sp.orbit_r * 0.6) + sp.vertical_offset * 0.35
            sp_alpha = int(140 + 105 * math.sin(sp.phase))
            sp_r = 1.7 + 0.9 * math.sin(sp.phase * 1.6)

            if sp.color_type == "gold":
                sc = QColor(254, 240, 138, sp_alpha)
            else:
                sc = QColor(125, 211, 252, sp_alpha)

            painter.setPen(Qt.NoPen)
            painter.setBrush(sc)
            painter.drawEllipse(QPointF(sx, sy), sp_r, sp_r)

        # ---------------------------------------------------------
        # 7. Интерактивная плашка статуса и эмоции при наведении
        # ---------------------------------------------------------
        if self.hover_glow > 0.05:
            painter.save()
            painter.setOpacity(self.hover_glow)

            badge_text = f"🌸 Эйра — {pal['name']}"
            font = QFont("Segoe UI", 9)
            font.setWeight(QFont.DemiBold)
            painter.setFont(font)
            fm = QFontMetrics(font)
            tw = fm.horizontalAdvance(badge_text)
            th = fm.height()

            badge_rect = QRectF(cx - tw / 2.0 - 12.0, cy - 58.0 - th, tw + 24.0, th + 10.0)
            painter.setPen(QPen(QColor(pal["inner"].red(), pal["inner"].green(), pal["inner"].blue(), 190), 1.2))
            painter.setBrush(QColor(14, 20, 36, 225))
            painter.drawRoundedRect(badge_rect, 10.0, 10.0)

            painter.setPen(QColor(248, 250, 252))
            painter.drawText(badge_rect, Qt.AlignCenter, badge_text)
            painter.restore()

        painter.restore()
