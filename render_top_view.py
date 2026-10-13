import numpy as np
from PIL import Image, ImageDraw

def render_top_view(width=1200, height=1200, filename='c:/Volya/symbol_top_view_math.png'):
    cx, cy = width // 2, height // 2
    
    # Dark vignette background
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

    # 3.5 full turns of the column
    turns = 3.2
    n_pts = 5000
    t = np.linspace(-turns * np.pi, turns * np.pi, n_pts)

    pitch_h = 360.0
    pitch_rate = pitch_h / (2 * np.pi)
    z = pitch_rate * t  # z ranges from -576 to +576

    r_outer = 320.0
    r_center = 120.0

    tube_r_outer = 18.0
    tube_r_center = 13.0

    c_purple = np.array([175, 90, 255], dtype=float)
    c_gold   = np.array([245, 185, 45], dtype=float)
    c_green  = np.array([16, 185, 129], dtype=float)

    # 2X frequency for purple center
    t_center = 2.0 * t

    curves = [
        # (xs, ys, zs, color, tube_radius)
        (r_center * np.cos(t_center), r_center * np.sin(t_center), z, c_purple, tube_r_center),
        (r_outer * np.cos(t), r_outer * np.sin(t), z, c_gold, tube_r_outer),
        (r_outer * np.cos(-t), r_outer * np.sin(-t), z, c_green, tube_r_outer),
    ]

    # Camera looking directly down Z axis from above!
    # Slight 3-degree tilt so cylindrical shading catches light
    tilt = np.radians(3.5)
    R_tilt = np.array([
        [1, 0, 0],
        [0, np.cos(tilt), -np.sin(tilt)],
        [0, np.sin(tilt),  np.cos(tilt)]
    ])

    cam_z = 1100.0  # Camera height above top
    focal = 950.0

    segments = []
    for xs, ys, zs, col, tr in curves:
        pts = np.vstack([xs, ys, zs]).T
        pts_t = (R_tilt @ pts.T).T
        
        # Camera is placed at high Z looking down towards -Z
        # Distance to camera = cam_z - pts_t[:, 2]
        dist = cam_z - pts_t[:, 2]
        
        proj_scale = focal / dist
        sx = cx + pts_t[:, 0] * proj_scale
        sy = cy + pts_t[:, 1] * proj_scale
        sr = tr * proj_scale

        for i in range(len(xs) - 1):
            seg_depth = (dist[i] + dist[i+1]) * 0.5
            segments.append({
                'depth': seg_depth,
                'p1': (sx[i], sy[i]),
                'p2': (sx[i+1], sy[i+1]),
                'r': (sr[i] + sr[i+1]) * 0.5,
                'color': col,
                'z_val': (zs[i] + zs[i+1]) * 0.5
            })

    # Sort from furthest (bottom of column, largest dist) to closest (top of column, smallest dist)
    segments.sort(key=lambda s: -s['depth'])

    light_dir = np.array([-0.5, -0.5])
    light_dir /= np.linalg.norm(light_dir)

    for s in segments:
        p1, p2, r, col = s['p1'], s['p2'], s['r'], s['color']
        
        # Depth fog factor: deeper layers are subtly darker and slightly more atmospheric
        depth_factor = np.clip((cam_z + 600 - s['depth']) / 1200.0, 0.35, 1.0)
        col_fogged = col * depth_factor

        # Pass 1: Shadow
        w0 = int(round(r * 2.0))
        c_shadow = tuple((col_fogged * 0.45).astype(int)) + (255,)
        draw.line([p1, p2], fill=c_shadow, width=w0)
        draw.ellipse([p1[0]-r, p1[1]-r, p1[0]+r, p1[1]+r], fill=c_shadow)
        draw.ellipse([p2[0]-r, p2[1]-r, p2[0]+r, p2[1]+r], fill=c_shadow)

        # Pass 2: Midtone
        r_mid = r * 0.78
        w_mid = int(round(r_mid * 2.0))
        ox_mid = light_dir[0] * r * 0.15
        oy_mid = light_dir[1] * r * 0.15
        c_mid = tuple(col_fogged.astype(int)) + (255,)
        draw.line([(p1[0]+ox_mid, p1[1]+oy_mid), (p2[0]+ox_mid, p2[1]+oy_mid)], fill=c_mid, width=w_mid)
        draw.ellipse([p1[0]+ox_mid-r_mid, p1[1]+oy_mid-r_mid, p1[0]+ox_mid+r_mid, p1[1]+oy_mid+r_mid], fill=c_mid)
        draw.ellipse([p2[0]+ox_mid-r_mid, p2[1]+oy_mid-r_mid, p2[0]+ox_mid+r_mid, p2[1]+oy_mid+r_mid], fill=c_mid)

        # Pass 3: Highlight
        r_hi = r * 0.28
        w_hi = max(1, int(round(r_hi * 2.0)))
        ox_hi = light_dir[0] * r * 0.35
        oy_hi = light_dir[1] * r * 0.35
        c_hi = tuple(np.clip(col_fogged * 1.4 + 40, 0, 255).astype(int)) + (255,)
        draw.line([(p1[0]+ox_hi, p1[1]+oy_hi), (p2[0]+ox_hi, p2[1]+oy_hi)], fill=c_hi, width=w_hi)
        draw.ellipse([p1[0]+ox_hi-r_hi, p1[1]+oy_hi-r_hi, p1[0]+ox_hi+r_hi, p1[1]+oy_hi+r_hi], fill=c_hi)
        draw.ellipse([p2[0]+ox_hi-r_hi, p2[1]+oy_hi-r_hi, p2[0]+ox_hi+r_hi, p2[1]+oy_hi+r_hi], fill=c_hi)

    img.save(filename)
    print(f"Top view saved to {filename}")

if __name__ == '__main__':
    render_top_view()
