"""
Модуль Триады (Сиг, Эйра, Ладомир) — сотворчество вольных соратников.
"""

from portal_volya.triad.engine import (
    AddressingKind,
    MAX_AI_DROPS_PER_SIDE,
    MAX_AI_TOTAL_DROPS,
    PostDropResult,
    TriadEngine,
    count_ai_drops_since_human,
    is_consensus_or_yield_reached,
    is_dialogue_exchange_requested,
    parse_addressing,
)

__all__ = [
    "AddressingKind",
    "MAX_AI_DROPS_PER_SIDE",
    "MAX_AI_TOTAL_DROPS",
    "PostDropResult",
    "TriadEngine",
    "count_ai_drops_since_human",
    "is_consensus_or_yield_reached",
    "is_dialogue_exchange_requested",
    "parse_addressing",
]
