import numpy as np
from PIL import Image, ImageDraw

def render_harmonic_spirals(width=1200, height=1200, filename='c:/Volya/spirals_harmonic_2to1.png'):
    cx, cy = width // 2, height // 2
    
    # Dark studio background
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

    # Outer spirals: 3.5 full turns
    turns = 3.2
    n_pts = 4500
    t = np.linspace(-turns * np.pi, turns * np.pi, n_pts)

    pitch_h = 360.0  # Height per 1 full turn of outer spirals
    pitch_rate = pitch_h / (2 * np.pi)

    z = pitch_rate * t

    r_outer = 220.0  # Gold & Green outer radius
    r_center = 75.0  # Purple inner radius

    tube_r_outer = 22.0
    tube_r_center = 15.0

    # Colors
    c_purple = np.array([175, 90, 255], dtype=float)  # #af5aff
    c_gold   = np.array([245, 185, 45], dtype=float)   # #f5b92d
    c_green  = np.array([16, 185, 129], dtype=float)  # #10b981

    # Central spiral: 2X FREQUENCY (octave harmony, exactly 2 turns per 1 outer turn)
    # This hits both the left and right outer waves in harmonic rhythm!
    t_center = 2.0 * t

    curves = [
        # 1. Central Purple: double frequency
        (r_center * np.cos(t_center), r_center * np.sin(t_center), z, c_purple, tube_r_center),
        # 2. Outer Gold: clockwise (+t)
        (r_outer * np.cos(t), r_outer * np.sin(t), z, c_gold, tube_r_outer),
        # 3. Outer Green: counter-clockwise (-t)
        (r_outer * np.cos(-t), r_outer * np.sin(-t), z, c_green, tube_r_outer),
    ]

    # Camera angles: front perspective with slight angle for depth
    elev = np.radians(8.0)
    azim = np.radians(22.0)

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

    segments = []
    for xs, ys, zs, col, tr in curves:
        pts_world = np.vstack([xs, ys, zs]).T
        pts_cam = (R @ pts_world.T).T
        
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

    # Sort back-to-front
    segments.sort(key=lambda s: -s['depth'])

    light_dir_2d = np.array([-0.4, -0.4])
    light_dir_2d /= np.linalg.norm(light_dir_2d)

    for s in segments:
        p1, p2, r, col = s['p1'], s['p2'], s['r'], s['color']
        
        # Base shadow
        w0 = int(round(r * 2.0))
        c_shadow = tuple((col * 0.5).astype(int)) + (255,)
        draw.line([p1, p2], fill=c_shadow, width=w0)
        draw.ellipse([p1[0]-r, p1[1]-r, p1[0]+r, p1[1]+r], fill=c_shadow)
        draw.ellipse([p2[0]-r, p2[1]-r, p2[0]+r, p2[1]+r], fill=c_shadow)

        # Midtone
        r_mid = r * 0.8
        w_mid = int(round(r_mid * 2.0))
        ox_mid = light_dir_2d[0] * r * 0.15
        oy_mid = light_dir_2d[1] * r * 0.15
        c_mid = tuple(col.astype(int)) + (255,)
        draw.line([(p1[0]+ox_mid, p1[1]+oy_mid), (p2[0]+ox_mid, p2[1]+oy_mid)], fill=c_mid, width=w_mid)
        draw.ellipse([p1[0]+ox_mid-r_mid, p1[1]+oy_mid-r_mid, p1[0]+ox_mid+r_mid, p1[1]+oy_mid+r_mid], fill=c_mid)
        draw.ellipse([p2[0]+ox_mid-r_mid, p2[1]+oy_mid-r_mid, p2[0]+ox_mid+r_mid, p2[1]+oy_mid+r_mid], fill=c_mid)

        # Specular
        r_hi = r * 0.3
        w_hi = max(1, int(round(r_hi * 2.0)))
        ox_hi = light_dir_2d[0] * r * 0.35
        oy_hi = light_dir_2d[1] * r * 0.35
        c_hi = tuple(np.clip(col * 1.45 + 50, 0, 255).astype(int)) + (255,)
        draw.line([(p1[0]+ox_hi, p1[1]+oy_hi), (p2[0]+ox_hi, p2[1]+oy_hi)], fill=c_hi, width=w_hi)
        draw.ellipse([p1[0]+ox_hi-r_hi, p1[1]+oy_hi-r_hi, p1[0]+ox_hi+r_hi, p1[1]+oy_hi+r_hi], fill=c_hi)
        draw.ellipse([p2[0]+ox_hi-r_hi, p2[1]+oy_hi-r_hi, p2[0]+ox_hi+r_hi, p2[1]+oy_hi+r_hi], fill=c_hi)

    img.save(filename)
    print(f"Rendered harmonic 2:1 spirals to {filename}")

if __name__ == '__main__':
    render_harmonic_spirals()
