"""
Сакральные объемные серпы месяца (3D Shaded Crescents) Вселенной «Воля».
Физический шейдинг поверхности (Heightfield + Blinn-Phong) с направленным солнечным/лунным светом:
- Направленный свет от солнца (сверху-слева)
- Скульптурный гребень с зеркальным бликом (specular)
- Мягкий бархатный drop shadow и ambient halo
- Ретина-качество (2x суперсэмплинг)
- Кэширование скомпонованных QPixmap для мгновенного рендеринга (60 FPS)
"""

from __future__ import annotations

import math
from typing import Dict, Optional, Tuple

import numpy as np
from PIL import Image, ImageFilter
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap

_crescent_cache: Dict[Tuple, Tuple[QPixmap, float, float]] = {}


def get_shaded_crescent_pixmap(
    r_mid: float,
    t_max: float,
    start_deg: float,
    span_deg: float,
    night: bool = False,
    is_active: bool = True,
    hovered: bool = False,
    scale: float = 2.0,
) -> Tuple[QPixmap, float, float]:
    """Генерация и кэширование 3D серпа месяца с физическим шейдингом, объемом и светотенью."""
    key = (
        round(r_mid, 1),
        round(t_max, 1),
        round(start_deg, 1),
        round(span_deg, 1),
        night,
        is_active,
        hovered,
    )
    if key in _crescent_cache:
        return _crescent_cache[key]

    pad = int(24 * scale)
    r_total = (r_mid + t_max) * scale
    size = int(math.ceil((r_total + pad) * 2))
    w = h = size
    cx = cy = size / 2.0

    ys, xs = np.mgrid[0:h, 0:w]
    dx = xs - cx
    dy = ys - cy
    dist = np.sqrt(dx**2 + dy**2)
    ang_deg = np.degrees(np.arctan2(dy, dx))

    mid_deg = start_deg + span_deg / 2.0
    half_span = span_deg / 2.0
    diff = (ang_deg - mid_deg + 180.0) % 360.0 - 180.0
    in_ang = np.abs(diff) <= half_span

    phi = diff
    factor = np.maximum(0.0, np.cos((np.pi / 2.0) * (phi / half_span))) ** 0.82

    t_max_s = t_max * scale
    r_mid_s = r_mid * scale
    r_inner = r_mid_s - (t_max_s * 0.45) * factor
    r_outer = r_mid_s + (t_max_s * 0.55) * factor
    thick = r_outer - r_inner

    edge_w = 1.0 * scale
    dist_in = dist - r_inner
    dist_out = r_outer - dist
    mask_rad = np.clip(dist_in / edge_w, 0.0, 1.0) * np.clip(dist_out / edge_w, 0.0, 1.0)

    ang_edge = 2.5
    ang_diff_start = half_span - np.abs(diff)
    mask_ang = np.clip(ang_diff_start / ang_edge, 0.0, 1.0)
    alpha = np.where(in_ang, mask_rad * mask_ang, 0.0)

    u = np.clip((dist - r_inner) / np.maximum(1e-4, thick), 0.0, 1.0)
    u_r = 0.58
    z_profile = np.where(
        u < u_r,
        np.maximum(0.0, np.sin((np.pi / 2.0) * (u / u_r))) ** 0.88,
        np.maximum(0.0, np.cos((np.pi / 2.0) * ((u - u_r) / (1.0 - u_r)))) ** 0.88,
    )
    z = np.where(alpha > 0.005, z_profile * (thick * 0.45), 0.0)

    gy, gx = np.gradient(z)
    nx = -gx
    ny = -gy
    nz = np.ones_like(z) * (1.1 * scale)
    norm = np.sqrt(nx**2 + ny**2 + nz**2)
    nx /= norm
    ny /= norm
    nz /= norm

    # Направленный свет от солнца сверху-слева (азимут 135°, высота 45°)
    l_vec = np.array([-0.5, -0.5, 0.707])
    l_vec /= np.linalg.norm(l_vec)
    v_vec = np.array([0.0, 0.0, 1.0])
    h_vec = l_vec + v_vec
    h_vec /= np.linalg.norm(h_vec)

    n_dot_l = np.maximum(0.0, nx * l_vec[0] + ny * l_vec[1] + nz * l_vec[2])
    n_dot_h = np.maximum(0.0, nx * h_vec[0] + ny * h_vec[1] + nz * h_vec[2])
    curve_pos = np.clip((diff + half_span) / (2.0 * half_span), 0.0, 1.0)

    if night:
        # Лунное серебро
        amb_col = np.array([40.0, 52.0, 75.0])
        mid_col = np.array([168.0, 192.0, 222.0])
        hi_col = np.array([245.0, 250.0, 255.0])
        spec_col = np.array([255.0, 255.0, 255.0])
        ambient = 0.22
        spec_p = 30.0
    else:
        # Сакральное золото
        amb_col = np.array([135.0, 72.0, 15.0])
        mid_col = np.array([238.0, 188.0, 68.0])
        hi_col = np.array([255.0, 246.0, 194.0])
        spec_col = np.array([255.0, 255.0, 255.0])
        ambient = 0.25
        spec_p = 22.0

    diffuse = ambient + (1.0 - ambient) * n_dot_l
    curve_mod = 1.08 - 0.26 * curve_pos
    diffuse = np.clip(diffuse * curve_mod, 0.0, 1.0)

    spec_mask = np.exp(-((u - u_r) / 0.18) ** 2)
    specular = (n_dot_h**spec_p) * (1.1 - 0.45 * curve_pos) * spec_mask

    c_diff = np.zeros((h, w, 3), dtype=np.float32)
    for i in range(3):
        c_diff[:, :, i] = np.where(
            diffuse < 0.5,
            amb_col[i] + (mid_col[i] - amb_col[i]) * (diffuse / 0.5),
            mid_col[i] + (hi_col[i] - mid_col[i]) * ((diffuse - 0.5) / 0.5),
        )
        c_diff[:, :, i] = np.clip(c_diff[:, :, i] + specular * spec_col[i] * 1.25, 0.0, 255.0)

    state_alpha = 1.0 if is_active else 0.65
    if hovered:
        state_alpha = min(1.0, state_alpha * 1.1)
    final_alpha = alpha * state_alpha

    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    for i in range(3):
        rgba[:, :, i] = np.clip(c_diff[:, :, i], 0, 255).astype(np.uint8)
    rgba[:, :, 3] = np.clip(final_alpha * 255.0, 0, 255).astype(np.uint8)

    pil_cr = Image.fromarray(rgba, "RGBA")
    pil_alpha = pil_cr.split()[3]

    # 1. Мягкая бархатная тень под серпом (смещение +2, +3.5)
    sh_alpha = pil_alpha.filter(ImageFilter.GaussianBlur(radius=3 * scale))
    sh_arr = np.array(sh_alpha)
    sh_rgba = np.zeros((h, w, 4), dtype=np.uint8)
    sh_rgba[:, :, 0] = 10
    sh_rgba[:, :, 1] = 18
    sh_rgba[:, :, 2] = 30
    sh_rgba[:, :, 3] = (sh_arr * 0.45 * state_alpha).astype(np.uint8)

    # 2. Мягкий золотой / лунный ореол вокруг серпа
    halo_alpha = pil_alpha.filter(ImageFilter.GaussianBlur(radius=5 * scale))
    h_arr = np.array(halo_alpha)
    h_rgba = np.zeros((h, w, 4), dtype=np.uint8)
    if night:
        h_rgba[:, :, 0] = 180
        h_rgba[:, :, 1] = 210
        h_rgba[:, :, 2] = 255
    else:
        h_rgba[:, :, 0] = 255
        h_rgba[:, :, 1] = 215
        h_rgba[:, :, 2] = 60
    h_rgba[:, :, 3] = (h_arr * 0.45 * state_alpha).astype(np.uint8)

    # Композитинг слоев в единый буфер
    comp_pil = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    comp_pil = Image.alpha_composite(comp_pil, Image.fromarray(h_rgba, "RGBA"))
    sh_shift = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sh_shift.paste(Image.fromarray(sh_rgba, "RGBA"), (int(2 * scale), int(3.5 * scale)))
    comp_pil = Image.alpha_composite(comp_pil, sh_shift)
    comp_pil = Image.alpha_composite(comp_pil, pil_cr)

    q_img = QImage(comp_pil.tobytes("raw", "RGBA"), w, h, QImage.Format_RGBA8888)
    target_w = int(w / scale)
    target_h = int(h / scale)
    q_pix = QPixmap.fromImage(q_img).scaled(
        target_w, target_h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation
    )
    res = (q_pix, cx / scale, cy / scale)
    _crescent_cache[key] = res
    return res


def draw_volumetric_crescent(
    painter: QPainter,
    center: QPointF,
    r_mid: float,
    start_deg: float,
    span_deg: float,
    t_out: float = 5.0,
    t_in: float = 4.5,
    glow_color: Optional[QColor] = None,
    core_color: Optional[QColor] = None,
    night: bool = False,
    is_active: bool = True,
    hovered: bool = False,
) -> None:
    """Отрисовка 3D серпа месяца с физическим шейдингом, объемом и светотенью."""
    t_max = t_out + t_in
    pix, ocx, ocy = get_shaded_crescent_pixmap(
        r_mid=r_mid,
        t_max=t_max,
        start_deg=start_deg,
        span_deg=span_deg,
        night=night,
        is_active=is_active,
        hovered=hovered,
    )
    painter.drawPixmap(QPointF(center.x() - ocx, center.y() - ocy), pix)
