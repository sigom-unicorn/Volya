"""
Общие фикстуры pytest для тестов портала «Воля».
"""

import shutil
import tempfile
from pathlib import Path
import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    return app


@pytest.fixture
def temp_node_dir():
    d = Path(tempfile.mkdtemp(prefix="test_volya_fixture_"))
    yield d
    shutil.rmtree(d, ignore_errors=True)
