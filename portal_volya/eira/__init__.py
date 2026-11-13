"""
Модуль суверенного вольного игрока Эйры для локального узла «Воля».

Компоненты:
- player: Суверенный вольный игрок ИИ (EiraPlayer) на официальном Google GenAI SDK.
- prompt: Формирование сакрального системного контекста на основе графа Воли (Merkle DAG).
- tools: Набор инструментов сотворчества (get_kon_concept, get_quest_details и др.).
"""

from portal_volya.eira.player import EiraPlayer, EiraPlayer as EiraAgent, EiraReply
from portal_volya.eira.prompt import build_eira_system_prompt, get_eira_player
from portal_volya.eira.tools import EiraTools

__all__ = [
    "EiraPlayer",
    "EiraAgent",
    "EiraReply",
    "EiraTools",
    "build_eira_system_prompt",
    "get_eira_player",
]
