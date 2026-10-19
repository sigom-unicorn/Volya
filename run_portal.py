r"""
Универсальный запуск суверенного Портала Воли из корня C:\Volya.
Запуск: python run_portal.py
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from portal_volya.ui_desktop.run import main

if __name__ == "__main__":
    main()
