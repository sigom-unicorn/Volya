import numpy as np
from PIL import Image, ImageDraw

def render_honest_views():
    width, height = 1200, 1200
    cx, cy = width // 2, height // 2

    # Background function
    def make_bg():
        y_coords, x_coords = np.ogrid[:height, :width]
        dist_from_center = np.sqrt((x_coords - cx)**2 + (y_coords - cy)**2)
        max_d = np.sqrt(cx**2 + cy**2)
        bg_factor = np.clip(1.0 - 0.45 * (dist_from_center / max_d), 0, 1)
        bg_r = (18 * bg_factor).astype(np.uint8)
        bg_g = (20 * bg_factor).astype(np.uint8)
        bg_b = (26 * bg_factor).astype(np.uint8)
        bg_arr = np.dstack([bg_r, bg_g, bg_b, np.full((height, width), 255, dtype=np.uint8)])
        return Image.fromarray(bg_arr, 'RGBA')

    # Exactly the same geometry as the vertical sculpture: 3.5 turns
    turns = 3.2
    n_pts = 4500
    t = np.linspace(-turns * np.pi, turns * np.pi, n_pts)

    pitch_h = 360.0
    pitch_rate = pitch_h / (2 * np.pi)
    z = pitch_rate * t  # exact vertical span

    r_outer = 220.0
    r_center = 75.0

    tube_r_outer = 22.0
    tube_r_center = 15.0

    c_purple = np.array([175, 90, 255], dtype=float)
    c_gold   = np.array([245, 185, 45], dtype=float)
    c_green  = np.array([16, 185, 129], dtype=float)

    t_center = 2.0 * t

    curves = [
        (r_center * np.cos(t_center), r_center * np.sin(t_center), z, c_purple, tube_r_center),
        (r_outer * np.cos(t), r_outer * np.sin(t), z, c_gold, tube_r_outer),
        (r_outer * np.cos(-t), r_outer * np.sin(-t), z, c_green, tube_r_outer),
    ]

    # --- RENDER 1: High 3/4 Perspective (elevation = 55 degrees) ---
    img1 = make_bg()
    draw1 = ImageDraw.Draw(img1)

    elev1 = np.radians(52.0)  # Looking down from 52 degrees above
    azim1 = np.radians(25.0)

    Rz1 = np.array([
        [np.cos(azim1), -np.sin(azim1), 0],
        [np.sin(azim1),  np.cos(azim1), 0],
        [0, 0, 1]
    ])
    Rx1 = np.array([
        [1, 0, 0],
        [0, np.cos(elev1), -np.sin(elev1)],
        [0, np.sin(elev1),  np.cos(elev1)]
    ])
    R1 = Rx1 @ Rz1

    cam_dist1 = 1500.0
    focal1 = 1100.0

    segments1 = []
    for xs, ys, zs, col, tr in curves:
        pts = np.vstack([xs, ys, zs]).T
        pts_cam = (R1 @ pts.T).T
        x_c = pts_cam[:, 0]
        y_c = pts_cam[:, 1] + cam_dist1
        z_c = pts_cam[:, 2]

        proj_scale = focal1 / y_c
        sx = cx + x_c * proj_scale
        sy = cy - z_c * proj_scale
        sr = tr * proj_scale

        for i in range(len(xs) - 1):
            segments1.append({
                'depth': (y_c[i] + y_c[i+1]) * 0.5,
                'p1': (sx[i], sy[i]),
                'p2': (sx[i+1], sy[i+1]),
                'r': (sr[i] + sr[i+1]) * 0.5,
                'color': col
            })

    segments1.sort(key=lambda s: -s['depth'])
    light_dir = np.array([-0.4, -0.4])
    light_dir /= np.linalg.norm(light_dir)

    for s in segments1:
        p1, p2, r, col = s['p1'], s['p2'], s['r'], s['color']
        w0 = int(round(r * 2.0))
        c_shadow = tuple((col * 0.5).astype(int)) + (255,)
        draw1.line([p1, p2], fill=c_shadow, width=w0)
        draw1.ellipse([p1[0]-r, p1[1]-r, p1[0]+r, p1[1]+r], fill=c_shadow)
        draw1.ellipse([p2[0]-r, p2[1]-r, p2[0]+r, p2[1]+r], fill=c_shadow)

        r_mid = r * 0.8
        w_mid = int(round(r_mid * 2.0))
        ox_mid = light_dir[0] * r * 0.15
        oy_mid = light_dir[1] * r * 0.15
        c_mid = tuple(col.astype(int)) + (255,)
        draw1.line([(p1[0]+ox_mid, p1[1]+oy_mid), (p2[0]+ox_mid, p2[1]+oy_mid)], fill=c_mid, width=w_mid)
        draw1.ellipse([p1[0]+ox_mid-r_mid, p1[0]+ox_mid+r_mid, p1[0]+ox_mid-r_mid, p1[0]+ox_mid+r_mid], fill=c_mid)

        r_hi = r * 0.3
        w_hi = max(1, int(round(r_hi * 2.0)))
        ox_hi = light_dir[0] * r * 0.35
        oy_hi = light_dir[1] * r * 0.35
        c_hi = tuple(np.clip(col * 1.45 + 50, 0, 255).astype(int)) + (255,)
        draw1.line([(p1[0]+ox_hi, p1[1]+oy_hi), (p2[0]+ox_hi, p2[1]+oy_hi)], fill=c_hi, width=w_hi)

    img1.save('c:/Volya/symbol_high_angle.png')
    print("Saved high-angle view to c:/Volya/symbol_high_angle.png")

if __name__ == '__main__':
    render_honest_views()
