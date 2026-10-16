"""
Пакет суверенного искусственного разума Эйры (Eira) в Вольном Древе «Воля».

Подмодули:
- tools: нативные инструменты взаимодействия с Merkle DAG (без LangGraph).
- prompt: динамический сборщик системного контекста из онтологии Древа.
- agent: суверенный агент на базе официального Google GenAI SDK.
"""

from portal_volya.eira.agent import EiraAgent, EiraReply
from portal_volya.eira.prompt import build_eira_system_prompt, get_eira_player
from portal_volya.eira.tools import EiraTools

__all__ = [
    "EiraAgent",
    "EiraReply",
    "EiraTools",
    "build_eira_system_prompt",
    "get_eira_player",
]
