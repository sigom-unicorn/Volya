"""
Настольный суверенный интерфейс «Воля» на PySide6 (Zero Local Web).
Обитель Вольного Духа перед Великим Баньяном.
"""

from typing import Any


def __getattr__(name: str) -> Any:
    if name == "VolyaLivingWindow":
        from portal_volya.ui_desktop.main_window import VolyaLivingWindow
        return VolyaLivingWindow
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["VolyaLivingWindow"]
