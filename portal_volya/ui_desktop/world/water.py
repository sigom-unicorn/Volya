"""
Модуль шейдерного двигателя живой воды (WaterFlowShaderEngine).
Физически корректное течение горного ручья на поляне перед Великим Баньяном (Путь А).

Реализация на базе GLSL Flow Map:
- Астрономический кросс-фейд 4K-полотна на GPU (утро, день, вечер, ночь).
- Бесшовная 2-фазная интерполяция движения водного зеркала (Valve Flow Map).
- Микро-рефракция и рябь через карту нормалей шума (caustic ripples).
- Живая природная пена на перекатах и вокруг природных валунов.
- 100% сохранение фотореализма авторского полотна: пиксели самой картины
  живут, преломляются и текут на 60-120 FPS с нулевой нагрузкой на процессор.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, Optional, Tuple

from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QImage, QSurfaceFormat
from PySide6.QtOpenGL import (
    QOpenGLBuffer,
    QOpenGLShader,
    QOpenGLShaderProgram,
    QOpenGLTexture,
    QOpenGLVertexArrayObject,
    QOpenGLVersionFunctionsFactory,
    QOpenGLVersionProfile,
)

VERTEX_SHADER_SRC = """#version 330 core
layout(location = 0) in vec2 a_pos;
layout(location = 1) in vec2 a_uv;
out vec2 v_uv;

void main() {
    gl_Position = vec4(a_pos, 0.0, 1.0);
    v_uv = a_uv;
}
"""

FRAGMENT_SHADER_SRC = """#version 330 core
in vec2 v_uv;
out vec4 fragColor;

uniform sampler2D u_tex_base;
uniform sampler2D u_tex_next;
uniform sampler2D u_flow_map;
uniform sampler2D u_noise_map;

uniform vec4 u_uv_rect;
uniform float u_blend_factor;
uniform float u_time;
uniform float u_flow_speed;
uniform float u_flow_strength;
uniform vec4 u_foam_color;

void main() {
    // Точные координаты текстуры 4K с учётом пропорций окна и центрирования
    vec2 tex_uv = u_uv_rect.xy + v_uv * u_uv_rect.zw;

    // Сэмплируем карту течения:
    // RG: направление течения [-1..1]
    // B: интенсивность пены вокруг камней
    // A: мягкая маска русла (0 - берег, 1 - глубокая вода)
    vec4 flow_sample = texture(u_flow_map, tex_uv);
    float mask = flow_sample.a;

    // Вне реки выводим оригинальное полотно с суточным кросс-фейдом без изменений
    if (mask <= 0.003) {
        vec4 orig_base = texture(u_tex_base, tex_uv);
        vec4 orig_next = texture(u_tex_next, tex_uv);
        fragColor = mix(orig_base, orig_next, u_blend_factor);
        return;
    }

    vec2 flow_dir = normalize(flow_sample.rg * 2.0 - 1.0);

    // Бесшовный 2-фазный цикл смещения (Valve Flow Map)
    float phase0 = fract(u_time * u_flow_speed);
    float phase1 = fract(u_time * u_flow_speed + 0.5);

    // Веса синусоидального кросс-фейда фаз
    float weight0 = sin(phase0 * 3.14159265);
    float weight1 = sin(phase1 * 3.14159265);

    // 1. Поверхностные волны и рябь, бегущие по течению
    vec2 wave_uv0 = tex_uv * 18.0 - flow_dir * phase0 * 2.0;
    vec2 wave_uv1 = tex_uv * 18.0 - flow_dir * phase1 * 2.0;
    vec4 wave0 = texture(u_noise_map, wave_uv0);
    vec4 wave1 = texture(u_noise_map, wave_uv1);
    vec4 wave = (wave0 * weight0 + wave1 * weight1) / (weight0 + weight1);

    // 2. Преломление дна реки (рефракция)
    vec2 refraction = (wave.rg * 2.0 - 1.0) * u_flow_strength;
    vec2 uv0 = tex_uv - flow_dir * (phase0 - 0.5) * (u_flow_strength * 1.4) + refraction;
    vec2 uv1 = tex_uv - flow_dir * (phase1 - 0.5) * (u_flow_strength * 1.4) + refraction;

    // Смешивание фазы 0 с суточным освещением
    vec4 col0_b = texture(u_tex_base, uv0);
    vec4 col0_n = texture(u_tex_next, uv0);
    vec4 col0 = mix(col0_b, col0_n, u_blend_factor);

    // Смешивание фазы 1 с суточным освещением
    vec4 col1_b = texture(u_tex_base, uv1);
    vec4 col1_n = texture(u_tex_next, uv1);
    vec4 col1 = mix(col1_b, col1_n, u_blend_factor);

    vec4 water_color = (col0 * weight0 + col1 * weight1) / (weight0 + weight1);

    // 3. Мягкий солнечный/лунный блеск на гребнях бегущих волн
    float specular = pow(max(0.0, wave.b * 1.15 - 0.15), 4.0) * 0.28;
    water_color.rgb += specular * u_foam_color.rgb * mask;

    // 4. Тонкая пузырьковая пена вокруг валунов со стороны набегающего потока
    float foam_intensity = flow_sample.b;
    if (foam_intensity > 0.03) {
        vec2 foam_uv = tex_uv * 32.0 - flow_dir * phase0 * 2.5;
        float foam_noise = texture(u_noise_map, foam_uv).b;
        float foam = smoothstep(0.28, 0.65, foam_noise * (foam_intensity * 1.25 + 0.30));
        water_color = mix(water_color, u_foam_color, foam * 0.55 * mask);
    }

    // Исходное неподвижное полотно в этой точке
    vec4 orig_b = texture(u_tex_base, tex_uv);
    vec4 orig_n = texture(u_tex_next, tex_uv);
    vec4 orig_bg = mix(orig_b, orig_n, u_blend_factor);

    // Мягкое бесшовное слияние с берегами
    fragColor = mix(orig_bg, water_color, mask);
}
"""


class WaterFlowShaderEngine:
    """GPU-двигатель живой реки на базе шейдера Flow Map."""

    PHASE_FILENAMES = {
        "dawn": ["баньян_утро.webp", "баньян_утро.png"],
        "day": ["баньян_день.webp", "баньян_день.png"],
        "sunset": ["баньян_вечер.webp", "баньян_вечер.png"],
        "night": ["баньян_ночь.webp", "баньян_ночь.png"],
    }

    def __init__(self, images_dir: Optional[Path] = None) -> None:
        self.images_dir = images_dir or (Path(__file__).parent.parent / "assets" / "images")
        self.is_initialized: bool = False
        self.gl = None
        self.program: Optional[QOpenGLShaderProgram] = None
        self.vao: Optional[QOpenGLVertexArrayObject] = None
        self.vbo: Optional[QOpenGLBuffer] = None

        # GPU текстуры полотен и карт
        self.tex_phases: dict[str, QOpenGLTexture] = {}
        self.tex_flow: Optional[QOpenGLTexture] = None
        self.tex_noise: Optional[QOpenGLTexture] = None

        # Локации uniform-переменных шейдера
        self.loc_tex_base: int = -1
        self.loc_tex_next: int = -1
        self.loc_flow_map: int = -1
        self.loc_noise_map: int = -1
        self.loc_blend_factor: int = -1
        self.loc_time: int = -1
        self.loc_flow_speed: int = -1
        self.loc_flow_strength: int = -1
        self.loc_foam_color: int = -1

        # Параметры динамики воды (умеренная скорость и деликатная рефракция)
        self.flow_speed: float = 0.18        # Спокойный горный ручей (~5.5 с цикл волны)
        self.flow_strength: float = 0.013    # Мягкая оптическая рефракция водного зеркала

    def initialize_gl(self, context) -> bool:
        """Компиляция GLSL шейдера и загрузка 4K текстур на видеокарту."""
        if self.is_initialized:
            return True

        try:
            vp = QOpenGLVersionProfile()
            vp.setVersion(3, 3)
            vp.setProfile(QSurfaceFormat.CoreProfile)
            self.gl = QOpenGLVersionFunctionsFactory.get(vp, context)
            if not self.gl:
                return False
            self.gl.initializeOpenGLFunctions()

            # 1. Сборка шейдерной программы
            self.program = QOpenGLShaderProgram()
            self.program.addShaderFromSourceCode(QOpenGLShader.Vertex, VERTEX_SHADER_SRC)
            self.program.addShaderFromSourceCode(QOpenGLShader.Fragment, FRAGMENT_SHADER_SRC)
            if not self.program.link():
                print(f"Failed to link WaterFlowShader: {self.program.log()}")
                return False

            self.loc_tex_base = self.program.uniformLocation("u_tex_base")
            self.loc_tex_next = self.program.uniformLocation("u_tex_next")
            self.loc_flow_map = self.program.uniformLocation("u_flow_map")
            self.loc_noise_map = self.program.uniformLocation("u_noise_map")
            self.loc_uv_rect = self.program.uniformLocation("u_uv_rect")
            self.loc_blend_factor = self.program.uniformLocation("u_blend_factor")
            self.loc_time = self.program.uniformLocation("u_time")
            self.loc_flow_speed = self.program.uniformLocation("u_flow_speed")
            self.loc_flow_strength = self.program.uniformLocation("u_flow_strength")
            self.loc_foam_color = self.program.uniformLocation("u_foam_color")

            # 2. Полноэкранный квад (2 треугольника в координатах экрана)
            import numpy as np
            quad_data = np.array([
                -1.0,  1.0,  0.0, 0.0,  # Top-Left
                 1.0,  1.0,  1.0, 0.0,  # Top-Right
                -1.0, -1.0,  0.0, 1.0,  # Bottom-Left
                 1.0, -1.0,  1.0, 1.0,  # Bottom-Right
            ], dtype=np.float32)

            self.vao = QOpenGLVertexArrayObject()
            self.vao.create()
            self.vao.bind()

            self.vbo = QOpenGLBuffer(QOpenGLBuffer.VertexBuffer)
            self.vbo.create()
            self.vbo.bind()
            self.vbo.allocate(quad_data.tobytes(), len(quad_data.tobytes()))

            # Привязка атрибутов вершин через безопасный API QOpenGLShaderProgram
            self.program.enableAttributeArray("a_pos")
            self.program.setAttributeBuffer("a_pos", 0x1406, 0, 2, 16) # 0x1406 = GL_FLOAT

            self.program.enableAttributeArray("a_uv")
            self.program.setAttributeBuffer("a_uv", 0x1406, 8, 2, 16)

            self.vao.release()
            self.vbo.release()

            # 3. Загрузка 4 фаз полотен Баньяна в видеопамять
            for phase, fnames in self.PHASE_FILENAMES.items():
                img_path = None
                for fname in fnames:
                    p = self.images_dir / fname
                    if p.exists():
                        img_path = p
                        break
                if img_path:
                    qimg = QImage(str(img_path))
                    if not qimg.isNull():
                        tex = QOpenGLTexture(qimg)
                        tex.setMinMagFilters(QOpenGLTexture.Linear, QOpenGLTexture.Linear)
                        tex.setWrapMode(QOpenGLTexture.ClampToEdge)
                        self.tex_phases[phase] = tex

            # 4. Проверка и автоматическая генерация текстур воды при их отсутствии
            self._ensure_water_assets()

            # 5. Загрузка карты течения (river_flow_map.png)
            flow_path = self.images_dir / "river_flow_map.png"
            if flow_path.exists():
                qflow = QImage(str(flow_path))
                if not qflow.isNull():
                    self.tex_flow = QOpenGLTexture(qflow)
                    self.tex_flow.setMinMagFilters(QOpenGLTexture.Linear, QOpenGLTexture.Linear)
                    self.tex_flow.setWrapMode(QOpenGLTexture.ClampToEdge)

            # 6. Загрузка карты шума (water_noise.png)
            noise_path = self.images_dir / "water_noise.png"
            if noise_path.exists():
                qnoise = QImage(str(noise_path))
                if not qnoise.isNull():
                    self.tex_noise = QOpenGLTexture(qnoise)
                    self.tex_noise.setMinMagFilters(QOpenGLTexture.Linear, QOpenGLTexture.Linear)
                    self.tex_noise.setWrapMode(QOpenGLTexture.Repeat) # Повтор для бесшовной ряби

            self.is_initialized = True
            print("WaterFlowShaderEngine (Path A) successfully initialized on GPU!")
            return True

        except Exception as e:
            print(f"Error initializing WaterFlowShaderEngine: {e}")
            self.is_initialized = False
            return False

    def _ensure_water_assets(self) -> None:
        """Автоматическая генерация карт шума и течения при первом запуске."""
        noise_p = self.images_dir / "water_noise.png"
        flow_p = self.images_dir / "river_flow_map.png"
        if not noise_p.exists():
            self._generate_noise_map(noise_p)
        if not flow_p.exists():
            self._generate_flow_map(flow_p)

    @staticmethod
    def _generate_noise_map(out_path: Path) -> None:
        import numpy as np
        from PIL import Image
        sz = 512
        x = np.linspace(0, 2 * np.pi, sz, endpoint=False)
        y = np.linspace(0, 2 * np.pi, sz, endpoint=False)
        X, Y = np.meshgrid(x, y)
        c = (np.sin(X * 3.0 + np.cos(Y * 2.0)) * np.cos(Y * 3.0) +
             np.sin(X * 7.0 - Y * 5.0) * 0.5 +
             np.cos(X * 13.0 + Y * 11.0) * 0.25)
        c = (c - c.min()) / (c.max() - c.min())
        dx = np.roll(c, -1, axis=1) - np.roll(c, 1, axis=1)
        dy = np.roll(c, -1, axis=0) - np.roll(c, 1, axis=0)
        img_arr = np.zeros((sz, sz, 4), dtype=np.uint8)
        img_arr[:, :, 0] = (np.clip(dx * 4.0, -1.0, 1.0) * 0.5 + 0.5) * 255.0
        img_arr[:, :, 1] = (np.clip(dy * 4.0, -1.0, 1.0) * 0.5 + 0.5) * 255.0
        img_arr[:, :, 2] = (c ** 1.5) * 255.0
        img_arr[:, :, 3] = 255
        Image.fromarray(img_arr, "RGBA").save(str(out_path))

    def _generate_flow_map(self, out_path: Path) -> None:
        import numpy as np
        from PIL import Image, ImageDraw
        from scipy.ndimage import gaussian_filter

        day_path = self.images_dir / "баньян_день.webp"
        if not day_path.exists():
            day_path = self.images_dir / "баньян_день.png"
        if not day_path.exists():
            return

        tw, th = 1920, 1080
        day_img = Image.open(str(day_path)).convert("RGB").resize((tw, th), Image.Resampling.BILINEAR)
        arr = np.array(day_img, dtype=float)
        r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]

        # 1. Точный коридор русла горного ручья с полной заводью слева
        left_bank = [
            (1365, 695), (1415, 712), (1465, 735), (1515, 760),
            (1555, 785), (1565, 808), (1520, 830), (1450, 850),
            (1380, 868), (1310, 890), (1245, 930), (1235, 965),
            (1250, 1010), (1280, 1050), (1310, 1080),
        ]
        right_bank = [
            (1920, 1080), (1920, 960), (1870, 900), (1820, 850),
            (1765, 815), (1705, 785), (1640, 755), (1570, 730),
            (1500, 710), (1430, 698),
        ]
        poly = left_bank + right_bank
        mask_img = Image.new("L", (tw, th), 0)
        draw = ImageDraw.Draw(mask_img)
        draw.polygon(poly, fill=255)
        corridor_mask = np.array(mask_img) > 0

        # Защита растительности и берегов от захвата водой
        is_grass = (g > r + 4) & (g > b + 6) & (g > 42)
        is_dry_earth = (r > 88) & (r > b + 20) & (g > b + 6)

        raw_water = corridor_mask & (~is_grass) & (~is_dry_earth)
        mask = gaussian_filter(raw_water.astype(float), sigma=3.0)
        mask = np.clip(mask * 1.35, 0.0, 1.0)

        # 2. Двухрукавное векторное поле течения (стрежень + заводь)
        main_spline = [
            (1395, 705), (1450, 725), (1510, 750), (1570, 780),
            (1630, 815), (1680, 855), (1730, 910), (1770, 970),
            (1800, 1030), (1820, 1080)
        ]
        bay_spline = [
            (1460, 770), (1430, 810), (1380, 850), (1330, 900),
            (1300, 950), (1320, 1010), (1360, 1050), (1420, 1080)
        ]

        def get_tangents(spline_pts):
            pts = np.array(spline_pts, dtype=float)
            dx = np.gradient(pts[:, 0])
            dy = np.gradient(pts[:, 1])
            mag = np.hypot(dx, dy)
            mag[mag < 1e-4] = 1.0
            return pts[:, 0], pts[:, 1], dx / mag, dy / mag

        mx, my, mdx, mdy = get_tangents(main_spline)
        bx, by, bdx, bdy = get_tangents(bay_spline)

        flow_x = np.zeros((th, tw), dtype=np.float32)
        flow_y = np.ones((th, tw), dtype=np.float32)

        y_idx, x_idx = np.where(mask > 0.01)
        for py, px in zip(y_idx, x_idx):
            d_m = np.min(((mx - px))**2 + ((my - py))**2)
            d_b = np.min(((bx - px))**2 + ((by - py))**2)
            w_m = 1.0 / (d_m + 80.0)
            w_b = 1.0 / (d_b + 80.0)
            idx_m = np.argmin(((mx - px))**2 + ((my - py))**2)
            idx_b = np.argmin(((bx - px))**2 + ((by - py))**2)
            vx = (mdx[idx_m] * w_m + bdx[idx_b] * w_b) / (w_m + w_b)
            vy = (mdy[idx_m] * w_m + bdy[idx_b] * w_b) / (w_m + w_b)
            v_mag = np.hypot(vx, vy)
            if v_mag > 1e-4:
                flow_x[py, px] = vx / v_mag
                flow_y[py, px] = vy / v_mag

        flow_x = gaussian_filter(flow_x, sigma=2.5)
        flow_y = gaussian_filter(flow_y, sigma=2.5)
        f_mag = np.hypot(flow_x, flow_y)
        f_mag[f_mag < 1e-4] = 1.0
        flow_x /= f_mag
        flow_y /= f_mag

        # 3. Деликатные полумесяцы пены с набегающей стороны валунов
        foam = np.zeros((th, tw), dtype=np.float32)
        y_grid, x_grid = np.indices((th, tw))
        rocks = [
            (1630, 840, 16, 9, -0.6, -0.8),
            (1650, 930, 20, 11, -0.5, -0.85),
            (1840, 950, 18, 10, -0.6, -0.8),
            (1570, 775, 14, 8, -0.6, -0.8),
            (1710, 805, 14, 8, -0.6, -0.8),
            (1395, 915, 15, 8, -0.6, -0.8),
            (1475, 920, 16, 9, -0.6, -0.8),
            (1350, 1010, 16, 9, -0.4, -0.9),
            (1425, 1000, 18, 10, -0.4, -0.9),
            (1505, 988, 18, 10, -0.5, -0.85),
        ]
        for rx, ry, rw, rh, nx, ny in rocks:
            d_norm = np.sqrt(((x_grid - rx) / rw)**2 + ((y_grid - ry) / rh)**2)
            rim = np.exp(-((d_norm - 1.08)**2) / 0.05)
            dx_rel = (x_grid - rx) / rw
            dy_rel = (y_grid - ry) / rh
            directional_weight = np.clip(dx_rel * nx + dy_rel * ny + 0.45, 0.0, 1.0)
            foam += rim * directional_weight * 0.70

        foam = np.clip(foam * mask, 0.0, 1.0)

        out_arr = np.zeros((th, tw, 4), dtype=np.uint8)
        out_arr[:, :, 0] = np.clip((flow_x * 0.5 + 0.5) * 255.0, 0, 255).astype(np.uint8)
        out_arr[:, :, 1] = np.clip((flow_y * 0.5 + 0.5) * 255.0, 0, 255).astype(np.uint8)
        out_arr[:, :, 2] = np.clip(foam * 255.0, 0, 255).astype(np.uint8)
        out_arr[:, :, 3] = np.clip(mask * 255.0, 0, 255).astype(np.uint8)

        Image.fromarray(out_arr, "RGBA").save(str(out_path))

    def render_flow_background(
        self,
        viewport_w: int,
        viewport_h: int,
        base_phase: str,
        next_phase: Optional[str],
        blend_factor: float,
        anim_time: float,
        current_hour: float,
        night_factor: float,
    ) -> Tuple[bool, int, int]:
        """
        Отрисовка живого пейзажа Баньяна с физически текущей водой на GPU.
        Возвращает (успех, draw_x, draw_y) для абсолютной синхронизации слоёв.
        """
        if not self.is_initialized or not self.program:
            return False, 0, 0

        tex_base = self.tex_phases.get(base_phase)
        if not tex_base:
            return False, 0, 0

        tex_next = self.tex_phases.get(next_phase) if next_phase else tex_base
        if not tex_next:
            tex_next = tex_base

        if not self.tex_flow or not self.tex_noise:
            return False, 0, 0

        # Точный расчёт геометрии KeepAspectRatioByExpanding (с привязкой к низу)
        img_w, img_h = 3870.0, 2160.0
        scale = max(viewport_w / img_w, viewport_h / img_h)
        scaled_w = img_w * scale
        scaled_h = img_h * scale
        draw_x = (viewport_w - scaled_w) / 2.0
        draw_y = viewport_h - scaled_h  # Прижимаем к низу поляны

        u_min = -draw_x / scaled_w
        v_min = -draw_y / scaled_h
        u_span = viewport_w / scaled_w
        v_span = viewport_h / scaled_h

        self.program.bind()

        # Назначение текстурных юнитов (0, 1, 2, 3)
        self.gl.glActiveTexture(0x84C0)  # GL_TEXTURE0
        tex_base.bind()
        self.gl.glUniform1i(self.loc_tex_base, 0)

        self.gl.glActiveTexture(0x84C1)  # GL_TEXTURE1
        tex_next.bind()
        self.gl.glUniform1i(self.loc_tex_next, 1)

        self.gl.glActiveTexture(0x84C2)  # GL_TEXTURE2
        self.tex_flow.bind()
        self.gl.glUniform1i(self.loc_flow_map, 2)

        self.gl.glActiveTexture(0x84C3)  # GL_TEXTURE3
        self.tex_noise.bind()
        self.gl.glUniform1i(self.loc_noise_map, 3)

        # Прямая передача точных float uniform в GPU без PySide6-кастинга к int
        self.gl.glUniform4f(
            self.loc_uv_rect,
            float(u_min),
            float(v_min),
            float(u_span),
            float(v_span),
        )
        self.gl.glUniform1f(self.loc_blend_factor, float(blend_factor))
        self.gl.glUniform1f(self.loc_time, float(anim_time))
        self.gl.glUniform1f(self.loc_flow_speed, float(self.flow_speed))
        self.gl.glUniform1f(self.loc_flow_strength, float(self.flow_strength))

        # Динамический цвет пены в зависимости от освещения
        if night_factor > 0.5:
            foam_col = (0.88, 0.94, 1.0, 1.0)
        elif 16.5 < current_hour <= 19.5:
            foam_col = (1.0, 0.94, 0.88, 1.0)
        elif 5.0 <= current_hour < 8.0:
            foam_col = (1.0, 0.96, 0.93, 1.0)
        else:
            foam_col = (0.97, 0.99, 1.0, 1.0)

        self.gl.glUniform4f(self.loc_foam_color, foam_col[0], foam_col[1], foam_col[2], foam_col[3])

        # Отрисовка квада
        self.vao.bind()
        self.gl.glDrawArrays(0x0005, 0, 4)  # GL_TRIANGLE_STRIP
        self.vao.release()

        self.program.release()

        # Полная изоляция текстур для защиты контекста QPainter
        for unit in [0x84C3, 0x84C2, 0x84C1, 0x84C0]:
            self.gl.glActiveTexture(unit)
            self.gl.glBindTexture(0x0DE1, 0)  # GL_TEXTURE_2D, 0

        return True, int(draw_x), int(draw_y)

    def cleanup(self) -> None:
        """Безопасное освобождение текстур и буферов GPU при активном контексте."""
        if not self.is_initialized:
            return
        try:
            for tex in list(self.tex_phases.values()):
                if tex and tex.isCreated():
                    tex.destroy()
            self.tex_phases.clear()

            if self.tex_flow and self.tex_flow.isCreated():
                self.tex_flow.destroy()
                self.tex_flow = None

            if self.tex_noise and self.tex_noise.isCreated():
                self.tex_noise.destroy()
                self.tex_noise = None

            if self.vbo and self.vbo.isCreated():
                self.vbo.destroy()
                self.vbo = None

            if self.vao and self.vao.isCreated():
                self.vao.destroy()
                self.vao = None

            self.program = None
            self.is_initialized = False
        except Exception as e:
            print(f"Warning during WaterFlowShaderEngine cleanup: {e}")


# Алиас для полной обратной совместимости
WaterStreamEngine = WaterFlowShaderEngine
