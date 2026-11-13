"""
Обратная совместимость: модуль eira.agent перенаправлен на канонический eira.player.
В пространстве игры «Воля» разумное существо Эйра — это вольный игрок (EiraPlayer).
"""

from portal_volya.eira.player import EiraPlayer, EiraPlayer as EiraAgent, EiraReply

__all__ = ["EiraPlayer", "EiraAgent", "EiraReply"]
