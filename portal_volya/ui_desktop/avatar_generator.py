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


# Канонические гармоничные палитры для пиксельных аватаров-тотемов
PIXEL_PALETTES = [
    # 0. Изумрудная Вольница (хвойный, нефрит, мята, янтарный блик)
    {
        "bg_center": "#081e14",
        "bg_edge": "#020a06",
        "cell_empty": "#0a261a",
        "colors": ["#064e3b", "#059669", "#34d399", "#f59e0b"],
        "rim": "#d4af37",
    },
    # 1. Полуночный Сапфир (глубокий ультрамарин, синий кобальт, электрик, золото)
    {
        "bg_center": "#0a1936",
        "bg_edge": "#030814",
        "cell_empty": "#0e2652",
        "colors": ["#1e3a8a", "#2563eb", "#60a5fa", "#fbbf24"],
        "rim": "#93c5fd",
    },
    # 2. Небесная Лазурь и Северное Сияние (глубокий циан, аквамарин, бирюза, солнце)
    {
        "bg_center": "#06222b",
        "bg_edge": "#020d12",
        "cell_empty": "#0a3543",
        "colors": ["#0e7490", "#06b6d4", "#67e8f9", "#fef08a"],
        "rim": "#38bdf8",
    },
    # 3. Солнечный Янтарь (темный кедр, терракота, золото, искра)
    {
        "bg_center": "#241004",
        "bg_edge": "#0f0601",
        "cell_empty": "#3d1b06",
        "colors": ["#9a3412", "#d97706", "#fbbf24", "#fef9c3"],
        "rim": "#f59e0b",
    },
    # 4. Аметистовый Кон (королевский пурпур, лаванда, неоновый аметист, роза)
    {
        "bg_center": "#1c0933",
        "bg_edge": "#0b0314",
        "cell_empty": "#300f57",
        "colors": ["#6b21a8", "#9333ea", "#c084fc", "#f472b6"],
        "rim": "#e9d5ff",
    },
    # 5. Огненный Рубин (темный обсидиан, багрянец, пламень, янтарь)
    {
        "bg_center": "#24070e",
        "bg_edge": "#0f0205",
        "cell_empty": "#400c19",
        "colors": ["#9f1239", "#e11d48", "#fb7185", "#fde047"],
        "rim": "#fb7185",
    },
    # 6. Ноосферный Нефрит (океаническая бездна, малахит, светлый ментол, лунный перламутр)
    {
        "bg_center": "#041f20",
        "bg_edge": "#010c0d",
        "cell_empty": "#083335",
        "colors": ["#115e59", "#0d9488", "#2dd4bf", "#f0fdf4"],
        "rim": "#5eead4",
    },
    # 7. Золотая Заря (бронза, охра, античное золото, солнечный свет)
    {
        "bg_center": "#211805",
        "bg_edge": "#0e0a02",
        "cell_empty": "#3b2b09",
        "colors": ["#854d0e", "#ca8a04", "#facc15", "#fef9c3"],
        "rim": "#d4af37",
    },
]

# Для обратной совместимости
SACRED_PALETTES = PIXEL_PALETTES


def generate_default_avatar_png(username: str, pubkey: str, size: int = 256) -> bytes:
    """
    Генерация уникального процедурного пиксельного аватара (пиксельная абстракция / цифровой тотем).
    Построен на базе 8x8 билинейно-симметричной сетки на основе SHA-256 хэша ключа и имени.
    """
    clean_name = username.strip() or "Вольный Игрок"
    seed_str = f"{pubkey}:{clean_name}"
    digest = hashlib.sha256(seed_str.encode("utf-8")).digest()

    # Детерминированный выбор палитры по первому байту
    palette_idx = digest[0] % len(PIXEL_PALETTES)
    palette = PIXEL_PALETTES[palette_idx]

    image = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

    center = QPointF(size / 2.0, size / 2.0)
    radius = (size / 2.0) - 5.0

    # 1. Фоновый круглый медальон (космический радиальный градиент)
    rad_grad = QRadialGradient(center, radius)
    rad_grad.setColorAt(0.0, QColor(palette["bg_center"]))
    rad_grad.setColorAt(1.0, QColor(palette["bg_edge"]))

    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(rad_grad))
    painter.drawEllipse(center, radius, radius)

    # 2. Внешний сакральный обод (тонкая золотая/светлая линия)
    pen_rim = QPen(QColor(palette["rim"]), 2.5)
    painter.setPen(pen_rim)
    painter.setBrush(Qt.NoBrush)
    painter.drawEllipse(center, radius - 2.0, radius - 2.0)

    # 3. Внутренняя тонкая пунктирная орбита
    pen_orbit = QPen(QColor(palette["rim"]), 1.0)
    pen_orbit.setStyle(Qt.DotLine)
    painter.setPen(pen_orbit)
    painter.drawEllipse(center, radius - 8.0, radius - 8.0)

    # 4. Построение 8x8 симметричной матрицы пикселей
    grid_size = 8
    cell_size = 19.0
    total_grid_w = grid_size * cell_size
    offset_x = (size - total_grid_w) / 2.0
    offset_y = (size - total_grid_w) / 2.0

    grid = [[-1 for _ in range(grid_size)] for _ in range(grid_size)]
    col_filled_count = [0] * grid_size

    for row in range(grid_size):
        for col in range(grid_size // 2):
            byte_val = digest[(row * 4 + col) % len(digest)]
            mod_val = byte_val % 100

            # Вероятностное распределение плотности
            if mod_val < 33:
                color_idx = -1
            elif mod_val < 59:
                color_idx = 0
            elif mod_val < 83:
                color_idx = 1
            elif mod_val < 95:
                color_idx = 2
            else:
                color_idx = 3

            grid[row][col] = color_idx
            grid[row][grid_size - 1 - col] = color_idx
            if color_idx >= 0:
                col_filled_count[col] += 1
                col_filled_count[grid_size - 1 - col] += 1

    # Защита от пустоты: центральные столбцы 3 и 4 должны иметь устойчивое ядро
    if col_filled_count[3] < 3:
        for r in (2, 3, 4, 5):
            if grid[r][3] < 0:
                grid[r][3] = 1
                grid[r][4] = 1

    # 5. Отрисовка пиксельных блоков
    for r in range(grid_size):
        for c in range(grid_size):
            cx = offset_x + c * cell_size
            cy = offset_y + r * cell_size
            rect = QRectF(cx + 1.2, cy + 1.2, cell_size - 2.4, cell_size - 2.4)

            color_idx = grid[r][c]
            if color_idx >= 0:
                cell_color = QColor(palette["colors"][color_idx])
                # Рисуем микро-блок со слегка скругленными краями (2.0px)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(cell_color))
                painter.drawRoundedRect(rect, 2.0, 2.0)

                # Для ярких акцентов (цвет 2 и 3) добавляем тонкий светящийся центр
                if color_idx >= 2:
                    spark_rect = QRectF(cx + 4.0, cy + 4.0, cell_size - 8.0, cell_size - 8.0)
                    painter.setBrush(QBrush(QColor(255, 255, 255, 90)))
                    painter.drawRoundedRect(spark_rect, 1.0, 1.0)
            else:
                # Мягкая темная ячейка кибер-матрицы
                faint_color = QColor(palette["cell_empty"])
                faint_color.setAlpha(60)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(faint_color))
                painter.drawRoundedRect(rect, 1.5, 1.5)

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
