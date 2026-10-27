"""
Генератор аватарок по умолчанию и обработчик пользовательских аватаров для «Воли».

1. generate_default_avatar_png: Процедурный генератор аватара из 9 золотых нитей (прямые и дуги)
   внутри священного круглого медальона на основе ключа и имени игрока.
2. process_custom_avatar_png: Квадратная обрезка и масштабирование загруженного изображения в PNG.
"""

from __future__ import annotations

import hashlib
import io
import math
import random
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QBuffer, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)


# Гармоничные фоновые палитры ноосферного пространства для круглого медальона
BG_MEDALLION_PALETTES = [
    # 0. Янтарная полночь (глубокий теплый обсидиан)
    {"bg_center": "#18120a", "bg_edge": "#0a0704", "rim": "#d4af37"},
    # 1. Хвойный изумруд (глубокий нефрит)
    {"bg_center": "#0e1614", "bg_edge": "#040908", "rim": "#d4af37"},
    # 2. Полуночный сапфир (глубокий кобальт)
    {"bg_center": "#0e131d", "bg_edge": "#05070c", "rim": "#d4af37"},
    # 3. Аметистовый кон (ночной пурпур)
    {"bg_center": "#150e1c", "bg_edge": "#07040a", "rim": "#d4af37"},
    # 4. Космический обсидиан (глубокий антрацит)
    {"bg_center": "#141414", "bg_edge": "#050505", "rim": "#d4af37"},
    # 5. Золотая заря (темная бронза)
    {"bg_center": "#1a150c", "bg_edge": "#090703", "rim": "#d4af37"},
]

# Для обратной совместимости
PIXEL_PALETTES = BG_MEDALLION_PALETTES
SACRED_PALETTES = BG_MEDALLION_PALETTES


def _intersect_segment_bezier(
    p1: QPointF, p2: QPointF, pa: QPointF, pb: QPointF, ctrl: QPointF
) -> list[tuple[float, QPointF]]:
    """
    Вычисляет точки пересечения отрезка p1->p2 с квадратичной кривой Безье (pa, ctrl, pb).
    Возвращает список кортежей (t, QPointF), где t in (0, 1] — параметр вдоль p1->p2.
    """
    v0 = (pa.x(), pa.y())
    v1 = (2 * (ctrl.x() - pa.x()), 2 * (ctrl.y() - pa.y()))
    v2 = (pb.x() - 2 * ctrl.x() + pa.x(), pb.y() - 2 * ctrl.y() + pa.y())

    dx = p2.x() - p1.x()
    dy = p2.y() - p1.y()
    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq < 1e-9:
        return []

    nx = -dy
    ny = dx

    a = nx * v2[0] + ny * v2[1]
    b = nx * v1[0] + ny * v1[1]
    c = nx * (v0[0] - p1.x()) + ny * (v0[1] - p1.y())

    roots: list[float] = []
    if abs(a) < 1e-9:
        if abs(b) > 1e-9:
            s = -c / b
            if 0.0 <= s <= 1.0:
                roots.append(s)
    else:
        disc = b * b - 4 * a * c
        if disc >= 0:
            sq = math.sqrt(disc)
            s1 = (-b - sq) / (2 * a)
            s2 = (-b + sq) / (2 * a)
            for s in (s1, s2):
                if 0.0 <= s <= 1.0:
                    roots.append(s)

    intersections: list[tuple[float, QPointF]] = []
    for s in roots:
        px = v0[0] + v1[0] * s + v2[0] * s * s
        py = v0[1] + v1[1] * s + v2[1] * s * s
        t = ((px - p1.x()) * dx + (py - p1.y()) * dy) / seg_len_sq
        if 0.02 < t <= 1.0:
            intersections.append((t, QPointF(px, py)))

    return intersections


def _segments_intersect(
    p1: QPointF, p2: QPointF, q1: QPointF, q2: QPointF
) -> bool:
    """
    Проверяет, пересекаются ли два отрезка p1->p2 и q1->q2 во внутренних точках.
    """
    dx1 = p2.x() - p1.x()
    dy1 = p2.y() - p1.y()
    dx2 = q2.x() - q1.x()
    dy2 = q2.y() - q1.y()

    denom = dx1 * dy2 - dy1 * dx2
    if abs(denom) < 1e-9:
        return False  # Отрезки параллельны или лежат на одной прямой

    t = ((q1.x() - p1.x()) * dy2 - (q1.y() - p1.y()) * dx2) / denom
    u = ((q1.x() - p1.x()) * dy1 - (q1.y() - p1.y()) * dx1) / denom

    return (0.01 < t < 0.99) and (0.01 < u < 0.99)


def generate_default_avatar_png(username: str, pubkey: str, size: int = 256) -> bytes:
    """
    Генерация уникального процедурного аватара из 9 золотых нитей (смесь прямых и дуг).
    Все линии строго одного золотого цвета и одинаковой толщины.
    Дуги начинаются и заканчиваются строго на окружности аватарки.
    Прямые нити начинаются на окружности и заканчиваются в месте пересечения с дуговой, если пересекаются
    (или доходят до окружности, если пересечения нет).
    Прямые нити гарантированно НЕ пересекаются друг с другом.
    Детерминированно строится на основе SHA-256 хэша ключа и имени игрока.
    """
    clean_name = username.strip() or "Вольный Игрок"
    seed_str = f"{pubkey}:{clean_name}"
    digest = hashlib.sha256(seed_str.encode("utf-8")).digest()
    rng = random.Random(digest)

    scale = max(0.1, size / 256.0)

    image = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

    cx, cy = size / 2.0, size / 2.0
    center = QPointF(cx, cy)
    radius = (size / 2.0) - (4.0 * scale)

    # 1. Фоновый круглый медальон (космический радиальный градиент)
    rad_grad = QRadialGradient(center, radius)
    rad_grad.setColorAt(0.0, QColor("#18140e"))
    rad_grad.setColorAt(0.7, QColor("#0a0805"))
    rad_grad.setColorAt(1.0, QColor("#020202"))

    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(rad_grad))
    painter.drawEllipse(center, radius, radius)

    # 2. Единый золотой цвет и единая толщина всех линий
    gold_color = QColor("#d4af37")
    line_width = 1.6 * scale

    # Внешняя золотая окружность аватарки
    rim_pen = QPen(gold_color, 2.0 * scale)
    painter.setPen(rim_pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawEllipse(center, radius, radius)

    # 3. Точка строго на окружности
    def point_on_circle(ang: float) -> QPointF:
        return QPointF(cx + radius * math.cos(ang), cy + radius * math.sin(ang))

    # 4. Ровно 9 нитей: случайная смесь прямых линий и дуг
    num_threads = 9
    num_arcs = rng.choice([4, 5])
    num_straight = num_threads - num_arcs

    # Сначала генерируем дуговые нити (от окружности к окружности)
    arc_data: list[tuple[QPointF, QPointF, QPointF, QPainterPath]] = []
    for _ in range(num_arcs):
        ang1 = rng.uniform(0, 2 * math.pi)
        sep = rng.uniform(math.pi * 0.25, math.pi * 1.75)
        ang2 = (ang1 + sep) % (2 * math.pi)

        pa = point_on_circle(ang1)
        pb = point_on_circle(ang2)

        mx = (pa.x() + pb.x()) / 2.0
        my = (pa.y() + pb.y()) / 2.0
        dx = pb.x() - pa.x()
        dy = pb.y() - pa.y()
        chord_len = math.hypot(dx, dy)

        nx = -dy / (chord_len + 1e-5)
        ny = dx / (chord_len + 1e-5)

        to_cx = cx - mx
        to_cy = cy - my
        dist_to_center = math.hypot(to_cx, to_cy)

        if dist_to_center > 1.0:
            dir_x = to_cx / dist_to_center
            dir_y = to_cy / dist_to_center
            bend_depth = rng.uniform(0.35, 1.2) * (chord_len * 0.45)
            side = 1.0 if rng.random() < 0.75 else -0.4
            ctrl = QPointF(mx + dir_x * bend_depth * side, my + dir_y * bend_depth * side)
        else:
            bend = rng.uniform(0.3, 0.7) * radius * rng.choice([-1, 1])
            ctrl = QPointF(cx + nx * bend, cy + ny * bend)

        path = QPainterPath()
        path.moveTo(pa)
        path.quadTo(ctrl, pb)
        arc_data.append((pa, pb, ctrl, path))

    # Затем генерируем прямые нити:
    # 1. Начинаются на окружности аватарки.
    # 2. Заканчиваются в месте первого пересечения с дуговой нитью (если пересекаются).
    # 3. Гарантированно НЕ пересекаются с другими прямыми нитями.
    straight_paths: list[QPainterPath] = []
    placed_segments: list[tuple[QPointF, QPointF]] = []

    for _ in range(num_straight):
        best_candidate: Optional[tuple[QPointF, QPointF]] = None

        for _ in range(100):
            ang1 = rng.uniform(0, 2 * math.pi)
            sep = rng.uniform(math.pi * 0.25, math.pi * 1.75)
            ang2 = (ang1 + sep) % (2 * math.pi)

            p1 = point_on_circle(ang1)
            p2 = point_on_circle(ang2)

            min_t = 1.0
            end_pt = p2

            for pa, pb, ctrl, _ in arc_data:
                hits = _intersect_segment_bezier(p1, p2, pa, pb, ctrl)
                for t_val, pt in hits:
                    if t_val < min_t:
                        min_t = t_val
                        end_pt = pt

            # Проверяем, не пересекается ли отрезок p1->end_pt с уже размещенными прямыми нитями
            crosses_existing = False
            for q1, q2 in placed_segments:
                if _segments_intersect(p1, end_pt, q1, q2):
                    crosses_existing = True
                    break

            if not crosses_existing:
                best_candidate = (p1, end_pt)
                break

        if best_candidate is not None:
            p1, end_pt = best_candidate
            placed_segments.append((p1, end_pt))
            path = QPainterPath()
            path.moveTo(p1)
            path.lineTo(end_pt)
            straight_paths.append(path)

    all_paths = [ad[3] for ad in arc_data] + straight_paths

    # 5. Отрисовка всех нитей строго единого золотого цвета и одинаковой толщины
    glow_pen = QPen(QColor(212, 175, 55, 60), line_width + (2.0 * scale))
    glow_pen.setCapStyle(Qt.RoundCap)
    painter.setPen(glow_pen)
    for p in all_paths:
        painter.drawPath(p)

    core_pen = QPen(gold_color, line_width)
    core_pen.setCapStyle(Qt.RoundCap)
    painter.setPen(core_pen)
    for p in all_paths:
        painter.drawPath(p)

    painter.end()
    return image_to_png_bytes(image)


def process_custom_avatar_png(source_data: bytes | str | Path, size: int = 256) -> bytes:
    """
    Загрузка пользовательского изображения, квадратная обрезка из центра
    и масштабирование до заданного размера в формате PNG.
    """
    image = QImage()
    if isinstance(source_data, (str, Path)):
        image.load(str(source_data))
    else:
        image.loadFromData(source_data)

    if image.isNull():
        raise ValueError("Не удалось распознать изображение аватара.")

    # Квадратный кроп по центру
    w, h = image.width(), image.height()
    min_dim = min(w, h)
    crop_x = (w - min_dim) // 2
    crop_y = (h - min_dim) // 2
    cropped = image.copy(crop_x, crop_y, min_dim, min_dim)

    # Плавное масштабирование
    scaled = cropped.scaled(
        size,
        size,
        Qt.IgnoreAspectRatio,
        Qt.SmoothTransformation,
    )

    return image_to_png_bytes(scaled)


def image_to_png_bytes(image: QImage) -> bytes:
    """Конвертация QImage в байты формата PNG."""
    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "PNG")
    data = bytes(buffer.data())
    buffer.close()
    return data
