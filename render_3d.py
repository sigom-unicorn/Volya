import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource

fig = plt.figure(figsize=(10, 10), facecolor='#121316')
ax = fig.add_subplot(111, projection='3d', facecolor='#121316')

# Parameters for synchronized spirals
turns = 4.5
z = np.linspace(-turns * np.pi, turns * np.pi, 2000)

# Exact mathematical synchronization: identical pitch
pitch_rate = 1.0  # z progress per radian

# Radius
r_center = 0.55
r_outer = 1.35

# 1. Central Purple Spiral (single, uniform)
theta_purple = z / pitch_rate
x_purple = r_center * np.cos(theta_purple)
y_purple = r_center * np.sin(theta_purple)

# 2. Outer Gold Spiral (clockwise)
theta_gold = z / pitch_rate
x_gold = r_outer * np.cos(theta_gold)
y_gold = r_outer * np.sin(theta_gold)

# 3. Outer Green Spiral (counter-clockwise)
theta_green = -z / pitch_rate
x_green = r_outer * np.cos(theta_green)
y_green = r_outer * np.sin(theta_green)

# Plot thick glowing curves
# Gold
ax.plot(x_gold, y_gold, z, color='#E5B842', linewidth=8, alpha=0.95, label='Золотая (по часовой)')
# Green
ax.plot(x_green, y_green, z, color='#10B981', linewidth=8, alpha=0.95, label='Зелёная (против часовой)')
# Purple
ax.plot(x_purple, y_purple, z, color='#A855F7', linewidth=6.5, alpha=0.98, label='Фиолетовая (центр)')

# View setup
ax.view_init(elev=12, azim=45)
ax.set_box_aspect([1, 1, 2.5])

# Hide axes and grid for a clean sacred emblem
ax.set_axis_off()
ax.grid(False)

plt.tight_layout()
plt.savefig('c:/Volya/spirals_matplotlib.png', dpi=150, facecolor='#121316', edgecolor='none')
print("Successfully generated spirals_matplotlib.png")
