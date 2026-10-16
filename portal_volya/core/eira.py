"""
Реэкспорт ядра Эйры из пакета portal_volya.eira для обратной совместимости.
"""

from portal_volya.eira.prompt import build_eira_system_prompt, get_eira_player
from portal_volya.eira.tools import EiraTools

__all__ = [
    "build_eira_system_prompt",
    "get_eira_player",
    "EiraTools",
]
