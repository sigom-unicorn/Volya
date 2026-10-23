"""
Генератор аватарок по умолчанию и обработчик пользовательских аватаров для «Воли».

1. generate_default_avatar_png: Процедурный генератор гармоничного аватара на PySide6 (256x256).
   Детерминированная священная палитра на основе pubkey и первая буква имени в золотом ореоле.
2. process_custom_avatar_png: Квадратная обрезка и масштабирование загруженного изображения в PNG.
"""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QBuffer, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QLinearGradient,
    QPainter,
    QPen,
    QRadialGradient,
)


# Канонические гармоничные палитры для аватаров
SACRED_PALETTES = [
    # 0. Изумруд и Золото
    {"bg_center": "#1b4332", "bg_edge": "#081c15", "accent": "#d4af37", "text": "#fdfbf7"},
    # 1. Полуночный Сапфир и Золото
    {"bg_center": "#1e3a8a", "bg_edge": "#0c1821", "accent": "#f59e0b", "text": "#ffffff"},
    # 2. Небесная Лазурь и Солнце
    {"bg_center": "#0284c7", "bg_edge": "#0f172a", "accent": "#fbbf24", "text": "#ffffff"},
    # 3. Горный Янтарь и Огонь
    {"bg_center": "#b45309", "bg_edge": "#451a03", "accent": "#fcd34d", "text": "#fffbeb"},
    # 4. Аметистовый Рассвет
    {"bg_center": "#6d28d9", "bg_edge": "#1e1b4b", "accent": "#f472b6", "text": "#fdf4ff"},
    # 5. Вечерний Рубин
    {"bg_center": "#9f1239", "bg_edge": "#2e0814", "accent": "#fbbf24", "text": "#fff1f2"},
]


def generate_default_avatar_png(username: str, pubkey: str, size: int = 256) -> bytes:
    """Генерация уникального процедурного аватара по умолчанию в виде PNG-байтов."""
    clean_name = username.strip() or "Вольный Игрок"
    first_char = clean_name[0].upper()

    # Детерминированный выбор палитры по хэшу pubkey
    seed_num = int(hashlib.sha256(pubkey.encode("utf-8")).hexdigest()[:8], 16)
    palette = SACRED_PALETTES[seed_num % len(SACRED_PALETTES)]

    image = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.TextAntialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

    center = QPointF(size / 2.0, size / 2.0)
    radius = (size / 2.0) - 6.0

    # 1. Фоновый радиальный градиент
    rad_grad = QRadialGradient(center, radius)
    rad_grad.setColorAt(0.0, QColor(palette["bg_center"]))
    rad_grad.setColorAt(1.0, QColor(palette["bg_edge"]))

    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(rad_grad))
    painter.drawEllipse(center, radius, radius)

    # 2. Изящный золотой ореол (сакральный круг)
    pen_halo = QPen(QColor(palette["accent"]), 3.0)
    pen_halo.setStyle(Qt.SolidLine)
    painter.setPen(pen_halo)
    painter.setBrush(Qt.NoBrush)
    painter.drawEllipse(center, radius - 4.0, radius - 4.0)

    # Тонкая внутренняя пунктирная орбита
    pen_orbit = QPen(QColor(palette["accent"]), 1.2)
    pen_orbit.setStyle(Qt.DotLine)
    painter.setPen(pen_orbit)
    painter.drawEllipse(center, radius - 12.0, radius - 12.0)

    # 3. Символ / Первая буква имени
    painter.setPen(QColor(palette["text"]))
    font = QFont("Georgia", int(size * 0.42), QFont.Bold)
    painter.setFont(font)

    text_rect = QRectF(0, 0, size, size)
    painter.drawText(text_rect, Qt.AlignCenter, first_char)

    painter.end()

    # Сохраняем в PNG байты
    ba = image_to_png_bytes(image)
    return ba


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
