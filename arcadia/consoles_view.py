"""The "choose a console" screen: a grid of big tiles, one per console (plus the collections)."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QAbstractItemView, QListView, QListWidget, QStyle, QStyledItemDelegate, QWidget

TILE = QSize(232, 152)
GAP = 14

# What a tile shows large. Anything not listed shows the first letters of its id.
SHORT = {
    "nes": "NES", "snes": "SNES", "n64": "N64", "gc": "GCN", "wii": "Wii", "wiiu": "Wii U", "switch": "Switch",
    "gb": "GB", "gbc": "GBC", "gba": "GBA", "nds": "DS", "n3ds": "3DS",
    "genesis": "Genesis", "sms": "SMS", "gamegear": "GG", "segacd": "Sega CD", "saturn": "Saturn", "dreamcast": "DC",
    "psx": "PS1", "ps2": "PS2", "ps3": "PS3", "psp": "PSP", "xbox": "Xbox",
    "pcengine": "PCE", "neogeo": "Neo Geo", "arcade": "Arcade",
    "atari2600": "2600", "atari7800": "7800", "lynx": "Lynx", "wonderswan": "WS", "ngp": "NGP", "virtualboy": "VB",
    "msx": "MSX", "amiga": "Amiga",
    "__recent__": "↺", "__favorites__": "★", "__all__": "ALL",
}

ROLE_ID = Qt.ItemDataRole.UserRole
ROLE_NAME = Qt.ItemDataRole.UserRole + 1
ROLE_COUNT = Qt.ItemDataRole.UserRole + 2
ROLE_ACCENT = Qt.ItemDataRole.UserRole + 3


def short_name(view_id: str) -> str:
    return SHORT.get(view_id) or view_id[:4].upper()


class TileDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index) -> QSize:
        return TILE

    def paint(self, painter: QPainter, option, index) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        accent = QColor(index.data(ROLE_ACCENT) or "#3e89d6")
        count = index.data(ROLE_COUNT) or 0
        rect = QRectF(option.rect).adjusted(6, 6, -6, -6)
        if selected:
            rect = rect.adjusted(-3, -3, 3, 3)  # the chosen tile steps forward

        path = QPainterPath()
        path.addRoundedRect(rect, 20, 20)
        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        if selected:
            gradient.setColorAt(0.0, accent.lighter(125))
            gradient.setColorAt(1.0, accent.darker(135))
        else:
            gradient.setColorAt(0.0, accent.darker(210))
            gradient.setColorAt(1.0, QColor(24, 25, 32))
        painter.fillPath(path, gradient)
        painter.setPen(QPen(QColor(255, 255, 255, 235) if selected else QColor(255, 255, 255, 28), 3 if selected else 1))
        painter.drawPath(path)

        faded = QColor(255, 255, 255, 255 if count or selected else 120)
        big = QFont(option.font)
        text = short_name(index.data(ROLE_ID))
        big.setPixelSize(40 if len(text) <= 5 else 30)
        big.setWeight(QFont.Weight.ExtraBold)
        painter.setFont(big)
        painter.setPen(faded)
        painter.drawText(rect.adjusted(10, 14, -10, -62), int(Qt.AlignmentFlag.AlignCenter), text)

        small = QFont(option.font)
        small.setPixelSize(14)
        small.setWeight(QFont.Weight.DemiBold)
        painter.setFont(small)
        name = painter.fontMetrics().elidedText(index.data(ROLE_NAME) or "", Qt.TextElideMode.ElideRight, int(rect.width() - 24))
        painter.setPen(QColor(255, 255, 255, 235 if count or selected else 140))
        painter.drawText(rect.adjusted(12, 0, -12, -34), int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom), name)

        small.setPixelSize(12)
        small.setWeight(QFont.Weight.Normal)
        painter.setFont(small)
        painter.setPen(QColor(255, 255, 255, 190 if selected else 120))
        label = "Empty" if not count else f"{count} game{'s' if count != 1 else ''}"
        painter.drawText(rect.adjusted(12, 0, -12, -12), int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom), label)
        painter.restore()


class ConsoleGrid(QListWidget):
    """Arrow keys move between tiles in two dimensions; Enter (or a click) opens the console."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("consoles")
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setMovement(QListView.Movement.Static)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setWrapping(True)
        self.setSpacing(0)
        self.setGridSize(QSize(TILE.width() + GAP, TILE.height() + GAP))
        self.setUniformItemSizes(True)
        self.setItemDelegate(TileDelegate(self))
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QListWidget.Shape.NoFrame)
        self.setMouseTracking(True)

    def columns(self) -> int:
        return max(1, self.viewport().width() // self.gridSize().width())


class CenteredGrid(QWidget):
    """Holds the grid and keeps it as wide as a whole number of tiles, centred, so the columns line up
    with the middle of the screen at any window size."""

    def __init__(self, grid: ConsoleGrid, parent=None):
        super().__init__(parent)
        self.grid = grid
        grid.setParent(self)
        self.setMinimumHeight(TILE.height())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        tile = self.grid.gridSize().width()
        scrollbar = 18  # room for the scrollbar so it never covers a column
        columns = max(1, (self.width() - scrollbar) // tile)
        width = columns * tile + scrollbar
        self.grid.setGeometry((self.width() - width) // 2, 0, width, self.height())
