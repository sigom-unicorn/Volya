import numpy as np
from PIL import Image, ImageDraw

def render_spirals(width=1200, height=1200, filename='c:/Volya/spirals_exact_3d.png'):
    cx, cy = width // 2, height // 2
    
    # Elegant dark background with subtle vignette
    y_coords, x_coords = np.ogrid[:height, :width]
    dist_from_center = np.sqrt((x_coords - cx)**2 + (y_coords - cy)**2)
    max_d = np.sqrt(cx**2 + cy**2)
    bg_factor = np.clip(1.0 - 0.5 * (dist_from_center / max_d), 0, 1)
    
    bg_r = (18 * bg_factor).astype(np.uint8)
    bg_g = (20 * bg_factor).astype(np.uint8)
    bg_b = (26 * bg_factor).astype(np.uint8)
    bg_arr = np.dstack([bg_r, bg_g, bg_b, np.full((height, width), 255, dtype=np.uint8)])
    img = Image.fromarray(bg_arr, 'RGBA')
    draw = ImageDraw.Draw(img)

    # Mathematical parameters: Tall, majestic, perfectly synchronized
    turns = 3.5  # 3.5 full revolutions
    n_pts = 4000
    t = np.linspace(-turns * np.pi, turns * np.pi, n_pts)

    # Identical pitch: every radian t moves z by pitch_rate
    pitch_rate = 340.0 / (2 * np.pi)  # 340 pixels vertical per full turn
    r_center = 85.0                   # inner purple radius
    r_outer = 220.0                   # outer radius (gold & green)

    tube_r_center = 16.0
    tube_r_outer = 20.0

    # Colors
    c_purple = np.array([168, 85, 247], dtype=float)  # #a855f7
    c_gold   = np.array([245, 185, 45], dtype=float)   # #f5b92d
    c_green  = np.array([16, 185, 129], dtype=float)  # #10b981

    # Curves: (x, y, z, color, tube_r)
    curves = [
        # 1. Central purple (single helix)
        (r_center * np.cos(t), r_center * np.sin(t), pitch_rate * t, c_purple, tube_r_center),
        # 2. Outer gold (clockwise)
        (r_outer * np.cos(t), r_outer * np.sin(t), pitch_rate * t, c_gold, tube_r_outer),
        # 3. Outer green (counter-clockwise)
        (r_outer * np.cos(-t), r_outer * np.sin(-t), pitch_rate * t, c_green, tube_r_outer),
    ]

    # Camera angles: eye-level with slight tilt
    elev = np.radians(10.0)
    azim = np.radians(28.0)

    Rz = np.array([
        [np.cos(azim), -np.sin(azim), 0],
        [np.sin(azim),  np.cos(azim), 0],
        [0, 0, 1]
    ])
    Rx = np.array([
        [1, 0, 0],
        [0, np.cos(elev), -np.sin(elev)],
        [0, np.sin(elev),  np.cos(elev)]
    ])
    R = Rx @ Rz

    cam_dist = 1600.0
    focal = 1100.0

    # Discretize into short 3D segments
    segments = []
    for xs, ys, zs, col, tr in curves:
        # Transform all points to camera space
        pts_world = np.vstack([xs, ys, zs]).T
        pts_cam = (R @ pts_world.T).T
        
        # Screen projection
        x_c = pts_cam[:, 0]
        y_c = pts_cam[:, 1] + cam_dist
        z_c = pts_cam[:, 2]

        proj_scale = focal / y_c
        sx = cx + x_c * proj_scale
        sy = cy - z_c * proj_scale
        sr = tr * proj_scale

        for i in range(len(xs) - 1):
            seg_depth = (y_c[i] + y_c[i+1]) * 0.5
            segments.append({
                'depth': seg_depth,
                'p1': (sx[i], sy[i]),
                'p2': (sx[i+1], sy[i+1]),
                'r': (sr[i] + sr[i+1]) * 0.5,
                'color': col
            })

    # Sort segments strictly back to front (largest depth first)
    segments.sort(key=lambda s: -s['depth'])

    # Light offset vector in screen space (upper-left light)
    light_dir_2d = np.array([-0.38, -0.38])
    light_dir_2d /= np.linalg.norm(light_dir_2d)

    # Draw segments
    for s in segments:
        p1 = s['p1']
        p2 = s['p2']
        r = s['r']
        col = s['color']

        # Pass 1: Dark base / shadow contour
        w0 = int(round(r * 2.0))
        c_shadow = tuple((col * 0.5).astype(int)) + (255,)
        draw.line([p1, p2], fill=c_shadow, width=w0)
        draw.ellipse([p1[0]-r, p1[1]-r, p1[0]+r, p1[1]+r], fill=c_shadow)
        draw.ellipse([p2[0]-r, p2[1]-r, p2[0]+r, p2[1]+r], fill=c_shadow)

        # Pass 2: Midtone body
        r_mid = r * 0.8
        w_mid = int(round(r_mid * 2.0))
        ox_mid = light_dir_2d[0] * r * 0.15
        oy_mid = light_dir_2d[1] * r * 0.15
        c_mid = tuple(col.astype(int)) + (255,)
        draw.line([(p1[0]+ox_mid, p1[1]+oy_mid), (p2[0]+ox_mid, p2[1]+oy_mid)], fill=c_mid, width=w_mid)
        draw.ellipse([p1[0]+ox_mid-r_mid, p1[1]+oy_mid-r_mid, p1[0]+ox_mid+r_mid, p1[1]+oy_mid+r_mid], fill=c_mid)
        draw.ellipse([p2[0]+ox_mid-r_mid, p2[1]+oy_mid-r_mid, p2[0]+ox_mid+r_mid, p2[1]+oy_mid+r_mid], fill=c_mid)

        # Pass 3: Specular highlight
        r_hi = r * 0.32
        w_hi = max(1, int(round(r_hi * 2.0)))
        ox_hi = light_dir_2d[0] * r * 0.35
        oy_hi = light_dir_2d[1] * r * 0.35
        c_hi = tuple(np.clip(col * 1.4 + 50, 0, 255).astype(int)) + (255,)
        draw.line([(p1[0]+ox_hi, p1[1]+oy_hi), (p2[0]+ox_hi, p2[1]+oy_hi)], fill=c_hi, width=w_hi)
        draw.ellipse([p1[0]+ox_hi-r_hi, p1[1]+oy_hi-r_hi, p1[0]+ox_hi+r_hi, p1[1]+oy_hi+r_hi], fill=c_hi)
        draw.ellipse([p2[0]+ox_hi-r_hi, p2[1]+oy_hi-r_hi, p2[0]+ox_hi+r_hi, p2[1]+oy_hi+r_hi], fill=c_hi)

    img.save(filename)
    print(f"Rendered smooth spirals to {filename}")

if __name__ == '__main__':
    render_spirals()
