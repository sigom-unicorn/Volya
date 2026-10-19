"""
Атмосферный двигатель живого мира (AtmosphereEngine).
Реалистичные перистые и кучевые облака (процедурный альфа-рендеринг с мягким гауссовым размытием),
солнечные лучи (God Rays) и парящая лесная пыльца на ветру.
"""

from __future__ import annotations

import math
import random
from typing import List, Tuple

from PIL import Image, ImageDraw, ImageFilter
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPixmap,
    QRadialGradient,
)


def _generate_cloud_pixmap(seed: int, width: int = 500, height: int = 240, puffs: int = 70) -> QPixmap:
    """Генерирует мягкий процедурный спрайт кучевого облака с гауссовым размытием."""
    im = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)
    rnd = random.Random(seed)

    # Кластеры мягких перекрывающихся кругов
    for _ in range(puffs):
        cx = rnd.gauss(width * 0.5, width * 0.20)
        cy = rnd.gauss(height * 0.52, height * 0.16)
        r = rnd.uniform(22.0, 52.0)
        alpha = rnd.randint(22, 50)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 255, 255, alpha))

    # Смягчение плоского низа, характерного для кучевых облаков
    draw.rectangle([0, int(height * 0.78), width, height], fill=(0, 0, 0, 0))

    # Гауссово размытие для естественных диффузных краев
    im = im.filter(ImageFilter.GaussianBlur(16))

    # Конвертируем PIL RGBA в QPixmap
    data = im.tobytes("raw", "RGBA")
    qimg = QImage(data, width, height, QImage.Format_RGBA8888)
    return QPixmap.fromImage(qimg)


class CloudEntity:
    """Дрейфующее облако с индивидуальной скоростью и масштабом."""

    def __init__(self, u: float, v: float, scale: float, speed: float, sprite_idx: int) -> None:
        self.u = u                      # Нормализованная координата X [-0.4 .. 1.4]
        self.v = v                      # Нормализованная координата Y [0.0 .. 0.35]
        self.scale = scale              # Масштаб (0.65 .. 1.4)
        self.speed = speed              # Скорость дрейфа
        self.sprite_idx = sprite_idx    # Индекс текстуры облака

    def update(self, dt: float) -> None:
        self.u += self.speed * dt
        if self.u > 1.35:
            self.u = -0.40
            self.v = random.uniform(0.02, 0.30)


class FloatingSpore:
    """Лесная спора или частица золотистой пыльцы, парящая на ветру."""

    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y
        self.size = random.uniform(1.2, 2.8)
        self.speed_x = random.uniform(14.0, 32.0)
        self.speed_y = random.uniform(-6.0, 6.0)
        self.phase = random.uniform(0.0, math.tau)
        self.freq = random.uniform(0.8, 2.2)

    def update(self, dt: float, width: float, height: float) -> None:
        self.phase += dt * self.freq
        self.x += (self.speed_x + math.sin(self.phase) * 10.0) * dt
        self.y += (self.speed_y + math.cos(self.phase * 0.7) * 8.0) * dt

        if self.x > width + 20:
            self.x = -20
            self.y = random.uniform(height * 0.2, height * 0.9)
        elif self.x < -20:
            self.x = width + 20
        if self.y > height + 20:
            self.y = height * 0.2
        elif self.y < height * 0.1:
            self.y = height * 0.85


class DriftingLeaf:
    """Опадающий и порхающий на горном ветру листочек Баньяна."""

    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y
        self.vx = random.uniform(20.0, 48.0)       # Дрейф по ветру
        self.vy = random.uniform(18.0, 38.0)       # Плавное планирование вниз
        self.size = random.uniform(4.5, 9.5)       # Размер листочка
        self.angle = random.uniform(0.0, math.tau)
        self.angular_vel = random.uniform(-2.8, 2.8)
        self.flutter_phase = random.uniform(0.0, math.tau)
        self.flutter_freq = random.uniform(1.8, 3.6)
        self.is_alive = True
        # 0: зелёный лист баньяна, 1: золотистый лепесток цветка
        self.kind = 0 if random.random() < 0.75 else 1

    def update(self, dt: float, width: float, height: float) -> None:
        self.flutter_phase += dt * self.flutter_freq
        self.angle += self.angular_vel * dt
        flutter_x = math.sin(self.flutter_phase) * 16.0
        flutter_y = math.cos(self.flutter_phase * 0.75) * 8.0

        self.x += (self.vx + flutter_x) * dt
        self.y += (self.vy + flutter_y) * dt

        if self.y > height + 25 or self.x > width + 35 or self.x < -35:
            self.is_alive = False


class AtmosphereEngine:
    """Управление реалистичными облаками, лучами света, живой листвой и дыханием леса."""

    def __init__(self) -> None:
        self.anim_time: float = 0.0

        # Предварительная генерация 3 уникальных мягких облачных текстур
        self.cloud_sprites: list[QPixmap] = [
            _generate_cloud_pixmap(seed=101, width=520, height=240, puffs=75),
            _generate_cloud_pixmap(seed=202, width=440, height=200, puffs=60),
            _generate_cloud_pixmap(seed=303, width=600, height=260, puffs=90),
        ]

        # 5 облаков на разных планах неба (параллакс)
        self.clouds: list[CloudEntity] = [
            CloudEntity(u=0.05, v=0.04, scale=1.35, speed=0.0035, sprite_idx=0),
            CloudEntity(u=0.45, v=0.14, scale=1.05, speed=0.0060, sprite_idx=1),
            CloudEntity(u=0.82, v=0.06, scale=1.45, speed=0.0042, sprite_idx=2),
            CloudEntity(u=0.22, v=0.22, scale=0.85, speed=0.0085, sprite_idx=1),
            CloudEntity(u=0.68, v=0.18, scale=0.95, speed=0.0070, sprite_idx=0),
        ]

        # 35 парящих золотистых спор / пыльцы дубравы
        self.spores: list[FloatingSpore] = [
            FloatingSpore(random.uniform(0, 1920), random.uniform(100, 950))
            for _ in range(35)
        ]

        # Порхающие листья и лепестки Баньяна на ветру
        self.leaves: list[DriftingLeaf] = [
            DriftingLeaf(random.uniform(400, 1500), random.uniform(150, 750))
            for _ in range(16)
        ]
        self._leaf_spawn_timer: float = 0.0

        # Кэш тонированных облаков
        self._cached_cloud_pixmaps: list[QPixmap] = []
        self._cached_cloud_hour: float = -999.0

    def update(self, dt: float, width: float, height: float) -> None:
        self.anim_time += dt
        for c in self.clouds:
            c.update(dt)
        for sp in self.spores:
            sp.update(dt, width, height)

        # Обновление и появление новых листьев из кроны Баньяна
        self._leaf_spawn_timer += dt
        if self._leaf_spawn_timer >= 0.45 and len(self.leaves) < 26:
            self._leaf_spawn_timer = 0.0
            # Спавн в границах кроны Баньяна
            spawn_x = random.uniform(width * 0.22, width * 0.78)
            spawn_y = random.uniform(height * 0.12, height * 0.42)
            self.leaves.append(DriftingLeaf(spawn_x, spawn_y))

        for leaf in self.leaves:
            leaf.update(dt, width, height)
        self.leaves = [l for l in self.leaves if l.is_alive]

    def _get_tinted_cloud_sprites(self, current_hour: float) -> list[QPixmap]:
        """Возвращает кэшированные спрайты облаков с динамической подсветкой времени суток."""
        if self._cached_cloud_pixmaps and abs(self._cached_cloud_hour - current_hour) < 0.05:
            return self._cached_cloud_pixmaps

        tinted_list: list[QPixmap] = []

        # Цвета подсветки облаков
        if 8.0 <= current_hour <= 16.5:
            # День: белые, пушистые, слегка подсвеченные солнцем
            tint = QColor(255, 255, 255, 235)
        elif 16.5 < current_hour <= 19.5:
            # Закат: тёплое янтарно-розовое пламя
            factor = (current_hour - 16.5) / 3.0
            r = int(255 - factor * 15)
            g = int(220 - factor * 60)
            b = int(160 - factor * 60)
            tint = QColor(r, g, b, 230)
        elif 5.0 <= current_hour < 8.0:
            # Рассвет: нежный персик
            dawn_factor = (8.0 - current_hour) / 3.0
            tint = QColor(255, int(210 - 20 * dawn_factor), int(190 - 20 * dawn_factor), 220)
        else:
            # Ночь: лунный серебристо-сизый оттенок
            tint = QColor(110, 135, 185, 130)

        for sprite in self.cloud_sprites:
            t_pix = QPixmap(sprite.size())
            t_pix.fill(Qt.transparent)

            p = QPainter(t_pix)
            p.drawPixmap(0, 0, sprite)
            p.setCompositionMode(QPainter.CompositionMode_SourceIn)
            p.fillRect(t_pix.rect(), tint)
            p.end()

            tinted_list.append(t_pix)

        self._cached_cloud_pixmaps = tinted_list
        self._cached_cloud_hour = current_hour
        return tinted_list

    def render_clouds(self, painter: QPainter, width: int, height: int, current_hour: float) -> None:
        """Отрисовка мягких плывущих облаков с динамической подсветкой."""
        painter.save()
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        sprites = self._get_tinted_cloud_sprites(current_hour)

        for cloud in self.clouds:
            sprite = sprites[cloud.sprite_idx]
            sw = sprite.width() * cloud.scale
            sh = sprite.height() * cloud.scale

            cx = cloud.u * width
            cy = cloud.v * height

            target_rect = QRectF(cx - sw * 0.5, cy - sh * 0.5, sw, sh)
            painter.drawPixmap(target_rect.toRect(), sprite)

        painter.restore()

    def render_god_rays(self, painter: QPainter, width: int, height: int, current_hour: float, sun_x: float, sun_y: float, sun_elev: float) -> None:
        """Отрисовка мягких солнечных лучей, пробивающихся сквозь крону."""
        if sun_elev <= 0.18:
            return

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)

        # Лучи веером исходят от Солнца
        rays_count = 7
        base_alpha = int(28 * sun_elev)
        color_start = QColor(255, 248, 220, base_alpha)
        color_end = QColor(255, 248, 220, 0)

        for i in range(rays_count):
            angle = (i - rays_count / 2) * 0.085 + math.sin(self.anim_time * 0.25 + i * 1.3) * 0.015
            ray_len = height * 1.3

            spread = 60.0 + i * 8.0
            dx = math.sin(angle) * ray_len
            dy = math.cos(angle) * ray_len

            p0 = QPointF(sun_x - 15, sun_y)
            p1 = QPointF(sun_x + 15, sun_y)
            p2 = QPointF(sun_x + dx + spread, sun_y + dy)
            p3 = QPointF(sun_x + dx - spread, sun_y + dy)

            ray_grad = QLinearGradient(QPointF(sun_x, sun_y), QPointF(sun_x + dx, sun_y + dy))
            ray_grad.setColorAt(0.0, color_start)
            ray_grad.setColorAt(0.5, QColor(255, 248, 220, int(base_alpha * 0.4)))
            ray_grad.setColorAt(1.0, color_end)

            ray_path = QPainterPath()
            ray_path.moveTo(p0)
            ray_path.lineTo(p1)
            ray_path.lineTo(p2)
            ray_path.lineTo(p3)
            ray_path.closeSubpath()

            painter.fillPath(ray_path, ray_grad)

        painter.restore()

    def render_spores(self, painter: QPainter, width: int, height: int, current_hour: float) -> None:
        """Отрисовка парящих лесных спор и пыльцы дубравы."""
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)

        if 8.0 <= current_hour <= 16.5:
            spore_color = QColor(255, 245, 195, 140)
            halo_color = QColor(255, 240, 160, 45)
        elif 16.5 < current_hour <= 19.5:
            spore_color = QColor(255, 210, 140, 155)
            halo_color = QColor(255, 180, 80, 50)
        elif 5.0 <= current_hour < 8.0:
            spore_color = QColor(255, 225, 200, 140)
            halo_color = QColor(255, 190, 170, 45)
        else:
            spore_color = QColor(190, 220, 245, 95)
            halo_color = QColor(140, 180, 230, 25)

        for sp in self.spores:
            painter.setBrush(halo_color)
            painter.drawEllipse(QPointF(sp.x, sp.y), sp.size * 2.4, sp.size * 2.4)
            painter.setBrush(spore_color)
            painter.drawEllipse(QPointF(sp.x, sp.y), sp.size, sp.size)

        painter.restore()

    def render_canopy_breath(self, painter: QPainter, width: int, height: int, current_hour: float) -> None:
        """Мягкие свето-теневые волны ветра на кроне Баньяна, создающие живое колыхание листвы."""
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)

        # Вычисление цвета и прозрачности световых переливов по времени суток
        if 8.0 <= current_hour <= 16.5:
            # Дневные блики солнца сквозь листву
            breath_col = QColor(255, 255, 225, 22)
        elif 16.5 < current_hour <= 19.5:
            # Закатные медово-розовые переливы
            breath_col = QColor(255, 205, 150, 26)
        elif 5.0 <= current_hour < 8.0:
            # Рассветные золотисто-персиковые отсветы
            breath_col = QColor(255, 228, 195, 24)
        else:
            # Ночные лунные серебристые отблески на верхушках ветвей
            breath_col = QColor(185, 220, 255, 14)

        # 6 органических фокусов кроны Баньяна для моделирования волн ветра
        canopy_nodes = [
            (0.32, 0.22, 120.0, 70.0, 0.0),
            (0.50, 0.16, 150.0, 80.0, 1.4),
            (0.68, 0.24, 130.0, 75.0, 2.7),
            (0.24, 0.38, 100.0, 60.0, 3.9),
            (0.46, 0.32, 140.0, 75.0, 0.8),
            (0.74, 0.36, 110.0, 65.0, 2.1),
        ]

        t = self.anim_time
        scale_x = width / 1920.0
        scale_y = height / 1080.0

        for u, v, rx_base, ry_base, phase in canopy_nodes:
            # Плавное колыхание ветви на горном бризе
            dx = math.sin(t * 0.85 + phase) * 7.0 * scale_x
            dy = math.cos(t * 0.65 + phase * 0.7) * 4.0 * scale_y
            pulse = 0.88 + 0.12 * math.sin(t * 1.1 + phase)

            cx = u * width + dx
            cy = v * height + dy
            rx = rx_base * scale_x * pulse
            ry = ry_base * scale_y * pulse

            grad = QRadialGradient(QPointF(cx, cy), rx)
            grad.setColorAt(0.0, breath_col)
            grad.setColorAt(0.55, QColor(breath_col.red(), breath_col.green(), breath_col.blue(), breath_col.alpha() // 2))
            grad.setColorAt(1.0, QColor(0, 0, 0, 0))

            painter.setBrush(grad)
            painter.drawEllipse(QPointF(cx, cy), rx, ry)

        painter.restore()

    def render_drifting_leaves(self, painter: QPainter, width: int, height: int, current_hour: float) -> None:
        """Отрисовка опадающих и порхающих на ветру листочков и лепестков Баньяна."""
        if not self.leaves:
            return

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)

        # Подбор оттенков листвы и лепестков по времени суток
        if 8.0 <= current_hour <= 16.5:
            col_leaf = QColor(86, 148, 62, 215)
            col_petal = QColor(245, 215, 125, 225)
        elif 16.5 < current_hour <= 19.5:
            col_leaf = QColor(145, 130, 52, 215)
            col_petal = QColor(255, 175, 95, 225)
        elif 5.0 <= current_hour < 8.0:
            col_leaf = QColor(105, 155, 75, 215)
            col_petal = QColor(255, 205, 150, 225)
        else:
            col_leaf = QColor(48, 92, 78, 160)
            col_petal = QColor(160, 195, 220, 170)

        for leaf in self.leaves:
            painter.save()
            painter.translate(leaf.x, leaf.y)
            painter.rotate(math.degrees(leaf.angle))

            color = col_petal if leaf.kind == 1 else col_leaf
            painter.setBrush(color)

            # Форма изящного листика баньяна
            s = leaf.size
            leaf_path = QPainterPath()
            leaf_path.moveTo(0, -s)
            leaf_path.quadTo(s * 0.55, 0, 0, s)
            leaf_path.quadTo(-s * 0.55, 0, 0, -s)
            painter.drawPath(leaf_path)

            painter.restore()

        painter.restore()
