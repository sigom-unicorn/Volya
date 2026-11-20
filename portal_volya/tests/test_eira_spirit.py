"""
Тесты живого воплощения Эйры (EiraLuminousSpirit).
"""

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication
import pytest
import sys

from portal_volya.ui_desktop.world.eira_spirit import EiraLuminousSpirit


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_eira_spirit_initialization(qapp):
    spirit = EiraLuminousSpirit(init_pos=QPointF(500.0, 300.0))
    assert spirit.pos.x() == 500.0
    assert spirit.pos.y() == 300.0
    assert spirit.current_emotion in spirit.EMOTION_PALETTES
    assert len(spirit.sparks) > 0


def test_eira_spirit_emotion_transition(qapp):
    spirit = EiraLuminousSpirit(init_pos=QPointF(500.0, 300.0))
    spirit.set_emotion("joy")
    assert spirit.target_emotion == "joy"
    assert spirit.emotion_blend == 0.0

    # Advance time
    spirit.update(0.5, 1200.0, 800.0)
    assert spirit.emotion_blend > 0.0

    spirit.update(1.0, 1200.0, 800.0)
    assert spirit.emotion_blend == 1.0
    assert spirit.current_emotion == "joy"


def test_eira_spirit_speech_trigger(qapp):
    spirit = EiraLuminousSpirit(init_pos=QPointF(500.0, 300.0))
    assert spirit.speech_pulse == 0.0

    spirit.trigger_speech(emotion="insight", intensity=1.2)
    assert spirit.speech_pulse >= 1.2
    assert spirit.target_emotion == "insight"

    # Decay
    spirit.update(1.0, 1200.0, 800.0)
    assert spirit.speech_pulse < 1.2


def test_eira_spirit_hit_test(qapp):
    spirit = EiraLuminousSpirit(init_pos=QPointF(400.0, 300.0))
    assert spirit.hit_test(QPointF(400.0, 300.0)) is True
    assert spirit.hit_test(QPointF(420.0, 310.0)) is True
    assert spirit.hit_test(QPointF(600.0, 300.0)) is False


def test_eira_spirit_rendering(qapp):
    img = QImage(800, 600, QImage.Format_ARGB32)
    img.fill(QColor(15, 23, 42))

    painter = QPainter(img)
    spirit = EiraLuminousSpirit(init_pos=QPointF(400.0, 300.0))
    spirit.trigger_speech(emotion="joy", intensity=1.0)
    spirit.is_hovered = True
    spirit.hover_glow = 1.0

    spirit.update(0.1, 800.0, 600.0)
    spirit.render(painter, night=True)
    painter.end()

    # Image should not be empty
    assert not img.isNull()
