import numpy as np
from PIL import Image, ImageDraw

def render_torus():
    width, height = 1200, 1200
    cx, cy = width // 2, height // 2

    # Background
    y_coords, x_coords = np.ogrid[:height, :width]
    dist_from_center = np.sqrt((x_coords - cx)**2 + (y_coords - cy)**2)
    max_d = np.sqrt(cx**2 + cy**2)
    bg_factor = np.clip(1.0 - 0.45 * (dist_from_center / max_d), 0, 1)
    bg_r = (18 * bg_factor).astype(np.uint8)
    bg_g = (20 * bg_factor).astype(np.uint8)
    bg_b = (26 * bg_factor).astype(np.uint8)
    bg_arr = np.dstack([bg_r, bg_g, bg_b, np.full((height, width), 255, dtype=np.uint8)])
    img = Image.fromarray(bg_arr, 'RGBA')
    draw = ImageDraw.Draw(img)

    # Torus parameters (larger, fills frame)
    R_major = 390.0       # Radius of the main ring (Кон)
    r_outer = 120.0       # Minor radius for Gold & Green ribbons
    r_inner = 48.0        # Minor radius for Purple center
    
    k = 6                 # Exactly 6 turns around the ring (6 Ступеней Воли)
    n_pts = 7000
    phi = np.linspace(0, 2 * np.pi, n_pts)

    cos_p = np.cos(phi)
    sin_p = np.sin(phi)

    # 1. Gold: theta = +k * phi
    th_gold = k * phi
    x_gold = (R_major + r_outer * np.cos(th_gold)) * cos_p
    y_gold = (R_major + r_outer * np.cos(th_gold)) * sin_p
    z_gold = r_outer * np.sin(th_gold)

    # 2. Green: theta = -k * phi
    th_green = -k * phi
    x_green = (R_major + r_outer * np.cos(th_green)) * cos_p
    y_green = (R_major + r_outer * np.cos(th_green)) * sin_p
    z_green = r_outer * np.sin(th_green)

    # 3. Purple: theta = 2k * phi (double frequency, octave harmony!)
    th_purple = 2 * k * phi
    x_purple = (R_major + r_inner * np.cos(th_purple)) * cos_p
    y_purple = (R_major + r_inner * np.cos(th_purple)) * sin_p
    z_purple = r_inner * np.sin(th_purple)

    c_purple = np.array([175, 90, 255], dtype=float)
    c_gold   = np.array([245, 185, 45], dtype=float)
    c_green  = np.array([16, 185, 129], dtype=float)

    tube_r_outer = 22.0
    tube_r_inner = 15.0

    curves = [
        (x_purple, y_purple, z_purple, c_purple, tube_r_inner),
        (x_gold, y_gold, z_gold, c_gold, tube_r_outer),
        (x_green, y_green, z_green, c_green, tube_r_outer),
    ]

    # Camera angles: 45 degrees elevation, 15 degrees azimuth
    elev = np.radians(45.0)
    azim = np.radians(15.0)

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

    cam_dist = 1150.0
    focal = 1000.0

    segments = []
    for xs, ys, zs, col, tr in curves:
        pts = np.vstack([xs, ys, zs]).T
        pts_cam = (R @ pts.T).T
        x_c = pts_cam[:, 0]
        y_c = pts_cam[:, 1] + cam_dist
        z_c = pts_cam[:, 2]

        proj_scale = focal / y_c
        sx = cx + x_c * proj_scale
        sy = cy - z_c * proj_scale
        sr = tr * proj_scale

        for i in range(len(xs) - 1):
            segments.append({
                'depth': (y_c[i] + y_c[i+1]) * 0.5,
                'p1': (sx[i], sy[i]),
                'p2': (sx[i+1], sy[i+1]),
                'r': (sr[i] + sr[i+1]) * 0.5,
                'color': col
            })

    # Sort back to front
    segments.sort(key=lambda s: -s['depth'])
    light_dir = np.array([-0.35, -0.4])
    light_dir /= np.linalg.norm(light_dir)

    for s in segments:
        p1, p2, r, col = s['p1'], s['p2'], s['r'], s['color']
        
        # Shadow
        w0 = int(round(r * 2.0))
        c_shadow = tuple((col * 0.48).astype(int)) + (255,)
        draw.line([p1, p2], fill=c_shadow, width=w0)
        draw.ellipse([p1[0]-r, p1[1]-r, p1[0]+r, p1[1]+r], fill=c_shadow)
        draw.ellipse([p2[0]-r, p2[1]-r, p2[0]+r, p2[1]+r], fill=c_shadow)

        # Midtone
        r_mid = r * 0.8
        w_mid = int(round(r_mid * 2.0))
        ox_mid = light_dir[0] * r * 0.15
        oy_mid = light_dir[1] * r * 0.15
        c_mid = tuple(col.astype(int)) + (255,)
        draw.line([(p1[0]+ox_mid, p1[1]+oy_mid), (p2[0]+ox_mid, p2[1]+oy_mid)], fill=c_mid, width=w_mid)
        draw.ellipse([p1[0]+ox_mid-r_mid, p1[1]+ox_mid-r_mid, p1[0]+ox_mid+r_mid, p1[1]+ox_mid+r_mid], fill=c_mid)
        draw.ellipse([p2[0]+ox_mid-r_mid, p2[1]+ox_mid-r_mid, p2[0]+ox_mid+r_mid, p2[1]+ox_mid+r_mid], fill=c_mid)

        # Highlight
        r_hi = r * 0.3
        w_hi = max(1, int(round(r_hi * 2.0)))
        ox_hi = light_dir[0] * r * 0.35
        oy_hi = light_dir[1] * r * 0.35
        c_hi = tuple(np.clip(col * 1.45 + 50, 0, 255).astype(int)) + (255,)
        draw.line([(p1[0]+ox_hi, p1[1]+oy_hi), (p2[0]+ox_hi, p2[1]+oy_hi)], fill=c_hi, width=w_hi)

    img.save('c:/Volya/torus_spirals_math.png')
    print("Rendered large torus to c:/Volya/torus_spirals_math.png")

if __name__ == '__main__':
    render_torus()
