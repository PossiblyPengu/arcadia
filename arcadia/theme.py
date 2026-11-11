"""Look and feel: stylesheet, animated backdrop, and toast messages."""

from __future__ import annotations

from PySide6.QtCore import QPropertyAnimation, QTimer, QVariantAnimation, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QRadialGradient
from PySide6.QtWidgets import QGraphicsOpacityEffect, QLabel, QWidget

DEFAULT_ACCENT = "#3e89d6"


def mix(a: QColor, b: QColor, t: float) -> QColor:
    """Blend a toward b by t (0..1)."""
    return QColor.fromRgbF(
        a.redF() * (1 - t) + b.redF() * t,
        a.greenF() * (1 - t) + b.greenF() * t,
        a.blueF() * (1 - t) + b.blueF() * t,
    )


def _white(percent: int) -> str:
    return f"rgba(255, 255, 255, {percent}%)"


def build_stylesheet(accent: str) -> str:
    bright = QColor(accent).lighter(118).name()
    return f"""
    QWidget {{ color: #eceef4; font-size: 14px; }}
    QLabel {{ background: transparent; }}
    QLabel#wordmark {{ font-size: 18px; font-weight: 800; }}
    QLabel#banner {{ font-size: 36px; font-weight: 800; }}
    QLabel#gameTitle {{ font-size: 28px; font-weight: 800; }}
    QMainWindow, QDialog {{ background: #14151b; }}
    QLineEdit, QComboBox {{
        background: {_white(8)}; border: 1px solid {_white(12)};
        border-radius: 18px; padding: 8px 16px;
    }}
    QLineEdit:focus, QComboBox:focus {{ border: 1px solid {accent}; }}
    QComboBox::drop-down {{ border: none; width: 24px; }}
    QComboBox QAbstractItemView {{
        background: #1d1f27; selection-background-color: {accent}; padding: 4px;
    }}
    QPushButton {{
        background: {_white(10)}; border: 1px solid {_white(10)};
        border-radius: 18px; padding: 9px 20px; font-weight: 600;
    }}
    QPushButton:hover {{ background: {_white(18)}; }}
    QPushButton:focus {{ border: 2px solid {accent}; }}
    QPushButton:disabled {{ color: rgba(236, 238, 244, 40%); background: {_white(5)}; }}
    QPushButton#primary {{
        background: {accent}; border: none; font-size: 16px; padding: 12px 34px;
    }}
    QPushButton#primary:hover {{ background: {bright}; }}
    QPushButton#primary:disabled {{ background: {_white(10)}; }}
    QPushButton::menu-indicator {{ width: 0px; }}
    QListWidget#systems {{ background: transparent; border: none; outline: none; }}
    QListWidget#systems::item {{
        padding: 8px 18px; margin: 4px 3px; border-radius: 16px; background: {_white(7)};
    }}
    QListWidget#systems::item:hover {{ background: {_white(14)}; }}
    QListWidget#systems::item:selected {{ background: {accent}; color: white; }}
    QMenu {{
        background: #1d1f27; border: 1px solid {_white(12)}; border-radius: 10px; padding: 6px;
    }}
    QMenu::item {{ padding: 8px 24px; border-radius: 6px; }}
    QMenu::item:selected {{ background: {accent}; }}
    QMenu::item:disabled {{ color: rgba(236, 238, 244, 35%); }}
    QMenuBar {{ background: transparent; }}
    QMenuBar::item {{ padding: 6px 12px; background: transparent; }}
    QMenuBar::item:selected {{ background: {_white(12)}; border-radius: 6px; }}
    QTableWidget {{ background: {_white(4)}; gridline-color: {_white(8)}; }}
    QHeaderView {{ background: transparent; }}
    QTableCornerButton::section {{ background: transparent; border: none; }}
    QHeaderView::section {{ background: {_white(8)}; border: none; padding: 6px; }}
    QTabWidget::pane {{ border: 1px solid {_white(10)}; border-radius: 10px; background: transparent; top: -1px; }}
    QTabBar::tab {{ background: {_white(6)}; padding: 8px 18px; margin-right: 4px; border-top-left-radius: 10px; border-top-right-radius: 10px; }}
    QTabBar::tab:hover {{ background: {_white(12)}; }}
    QTabBar::tab:selected {{ background: {accent}; color: white; font-weight: 600; }}
    QCheckBox {{ background: transparent; spacing: 8px; }}
    QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 5px; border: 1px solid {_white(35)}; background: {_white(6)}; }}
    QCheckBox::indicator:checked {{ background: {accent}; border: 1px solid {accent}; }}
    QScrollBar:vertical {{ background: transparent; width: 12px; margin: 0; }}
    QScrollBar::handle:vertical {{ background: {_white(22)}; border-radius: 5px; min-height: 28px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
    QToolTip {{ background: #1d1f27; color: #eceef4; border: 1px solid {accent}; }}
    QMessageBox, QDialog {{ background: #1a1b22; }}
    """


class Backdrop(QWidget):
    """Window background: a dark gradient tinted by the accent, with a soft glow
    behind the cover shelf. The tint glides to the new color on a system change."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._accent = QColor(DEFAULT_ACCENT)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(520)
        self._anim.valueChanged.connect(self._on_value)

    def set_accent(self, color: QColor) -> None:
        self._anim.stop()
        if not self.isVisible():
            self._accent = QColor(color)
            self.update()
            return
        self._anim.setStartValue(QColor(self._accent))
        self._anim.setEndValue(QColor(color))
        self._anim.start()

    def _on_value(self, value) -> None:
        self._accent = QColor(value)
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        w, h = self.width(), self.height()
        base = QColor(13, 14, 19)
        gradient = QLinearGradient(0, 0, 0, h)
        gradient.setColorAt(0.0, mix(base, self._accent, 0.30))
        gradient.setColorAt(0.55, mix(base, self._accent, 0.10))
        gradient.setColorAt(1.0, base)
        painter.fillRect(self.rect(), gradient)

        glow = QRadialGradient(w / 2, h * 0.47, max(w, h) * 0.42)
        center = QColor(self._accent)
        center.setAlpha(80)
        edge = QColor(self._accent)
        edge.setAlpha(0)
        glow.setColorAt(0.0, center)
        glow.setColorAt(1.0, edge)
        painter.fillRect(self.rect(), glow)
        painter.end()


class Toast(QLabel):
    """A short message that fades in at the top centre of its parent, then fades out."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setStyleSheet(
            "background: rgba(8, 9, 13, 82%); color: white; border-radius: 18px;"
            "padding: 10px 22px; font-weight: 600;"
        )
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._fx = QGraphicsOpacityEffect(self)
        self._fx.setOpacity(0.0)
        self.setGraphicsEffect(self._fx)
        self._anim = QPropertyAnimation(self._fx, b"opacity", self)
        self._anim.finished.connect(self._on_anim_finished)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade_out)
        self.hide()

    def show_message(self, text: str, ms: int = 2600) -> None:
        self.setText(text)
        self.adjustSize()
        self.reposition()
        self.show()
        self.raise_()
        self._anim.stop()
        self._anim.setDuration(180)
        self._anim.setStartValue(self._fx.opacity())
        self._anim.setEndValue(1.0)
        self._anim.start()
        self._timer.start(ms)

    def reposition(self) -> None:
        parent = self.parentWidget()
        if parent is not None:
            self.move((parent.width() - self.width()) // 2, 18)

    def _fade_out(self) -> None:
        self._anim.stop()
        self._anim.setDuration(380)
        self._anim.setStartValue(self._fx.opacity())
        self._anim.setEndValue(0.0)
        self._anim.start()

    def _on_anim_finished(self) -> None:
        if self._fx.opacity() <= 0.01:
            self.hide()
