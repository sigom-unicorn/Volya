"""
Модуль живого мира поляны перед Великим Баньяном.
"""

from portal_volya.ui_desktop.world.living_canvas import LivingWorldCanvas
from portal_volya.ui_desktop.world.celestial import CelestialEngine
from portal_volya.ui_desktop.world.atmosphere import AtmosphereEngine
from portal_volya.ui_desktop.world.water import WaterFlowShaderEngine

# Алиас для обратной совместимости
WaterStreamEngine = WaterFlowShaderEngine
from portal_volya.ui_desktop.world.creatures import CreaturesEngine

__all__ = [
    "LivingWorldCanvas",
    "CelestialEngine",
    "AtmosphereEngine",
    "WaterFlowShaderEngine",
    "WaterStreamEngine",
    "CreaturesEngine",
]
