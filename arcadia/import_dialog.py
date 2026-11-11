"""The "Import ROMs" dialog: review what was found in the inbox, fix any guesses, confirm."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from arcadia.config import Config
from arcadia.sorter import Confidence, Plan, PlanItem, SYSTEM_LABELS

_BADGES = {
    Confidence.CERTAIN: ("✓", "#6fcf97"),
    Confidence.LIKELY: ("~", "#e0c15a"),
    Confidence.UNSURE: ("?", "#f2a33a"),
}
_ORDER = {Confidence.UNSURE: 0, Confidence.LIKELY: 1, Confidence.CERTAIN: 2}

COL_MOVE, COL_FILE, COL_SYSTEM, COL_WHY, COL_DEST = range(5)


class ImportDialog(QDialog):
    def __init__(self, config: Config, plan: Plan, parent=None, inbox_label: str = ""):
        super().__init__(parent)
        self.config = config
        self.plan = plan
        self.items = sorted(plan.items, key=lambda i: (_ORDER[i.confidence], i.source.name.lower()))
        self._updating = False
        self.setWindowTitle("Import ROMs")
        self.resize(1100, 540)

        unsure = sum(1 for i in self.items if i.confidence is Confidence.UNSURE)
        intro = f"Found {len(self.items)} ROM{'s' if len(self.items) != 1 else ''}"
        if inbox_label:
            intro += f" in {inbox_label}"
        intro += "."
        if unsure:
            intro += (
                f" {unsure} need{'s' if unsure == 1 else ''} your confirmation (marked ?): "
                "check the system, then tick the box to move it."
            )
        self.intro = QLabel(intro)
        self.intro.setWordWrap(True)

        self.table = QTableWidget(len(self.items), 5)
        self.table.setHorizontalHeaderLabels(["Move", "File", "System", "Why", "Goes to"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(COL_MOVE, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COL_FILE, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(COL_SYSTEM, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(COL_WHY, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(COL_DEST, QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(False)
        self.table.setColumnWidth(COL_FILE, 300)
        self.table.setColumnWidth(COL_SYSTEM, 300)
        self.table.verticalHeader().setDefaultSectionSize(42)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)

        self.combos: list[QComboBox] = []
        for row, item in enumerate(self.items):
            self._build_row(row, item)
        self.table.itemChanged.connect(lambda _i: self._refresh_summary())

        self.keep_both_box = QCheckBox("If a file with the same name is already in the library, keep both (rename the new one)")

        notes = []
        if plan.ignored:
            notes.append(f"{len(plan.ignored)} other file{'s' if len(plan.ignored) != 1 else ''} don't look like ROMs and were left alone.")
        if plan.waiting:
            notes.append(f"{len(plan.waiting)} still downloading; they'll be picked up later.")
        self.notes = QLabel("  ".join(notes))
        self.notes.setStyleSheet("color: rgba(236, 238, 244, 55%);")
        self.notes.setWordWrap(True)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.move_btn = QPushButton("Move")
        self.move_btn.setObjectName("primary")
        self.buttons.addButton(self.move_btn, QDialogButtonBox.ButtonRole.AcceptRole)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.intro)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.keep_both_box)
        if notes:
            layout.addWidget(self.notes)
        layout.addWidget(self.buttons)
        self._refresh_summary()

    # ----- rows -----

    def _default_checked(self, item: PlanItem) -> bool:
        return item.confidence is not Confidence.UNSURE and not item.exists

    def _build_row(self, row: int, item: PlanItem) -> None:
        self._updating = True
        check = QTableWidgetItem()
        check.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
        check.setCheckState(Qt.CheckState.Checked if self._default_checked(item) else Qt.CheckState.Unchecked)
        self.table.setItem(row, COL_MOVE, check)

        name = QTableWidgetItem(item.source.name)
        name.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        extra = [c.name for c in item.companions]
        name.setToolTip(str(item.source) + ("".join(f"\n+ {n}" for n in extra)))
        if extra:
            name.setText(f"{item.source.name}  (+{len(extra)} file{'s' if len(extra) != 1 else ''})")
        self.table.setItem(row, COL_FILE, name)

        combo = QComboBox()
        for system in self.config.systems:
            combo.addItem(system.name or SYSTEM_LABELS.get(system.id, system.id), system.id)
        combo.setCurrentIndex(max(0, combo.findData(item.system_id)))
        combo.setStyleSheet("padding: 3px 12px; border-radius: 12px;")
        combo.currentIndexChanged.connect(lambda _i, r=row: self._on_system_picked(r))
        self.table.setCellWidget(row, COL_SYSTEM, combo)
        self.combos.append(combo)

        self.table.setItem(row, COL_WHY, QTableWidgetItem())
        self.table.setItem(row, COL_DEST, QTableWidgetItem())
        self._updating = False
        self._paint_row(row)

    def _paint_row(self, row: int) -> None:
        item = self.items[row]
        badge, color = ("✓", "#6fcf97") if item.manual else _BADGES[item.confidence]
        why = "Confirmed by you" if item.manual else item.reason
        if item.exists:
            why += "  (already in the library)"
        self._updating = True
        why_cell = self.table.item(row, COL_WHY)
        why_cell.setText(f"{badge}  {why}")
        why_cell.setToolTip(why)
        why_cell.setForeground(QBrush(QColor(color)))
        dest = self.table.item(row, COL_DEST)
        dest.setText(item.destination.parent.name + "/")  # the folder under your ROM root
        dest.setToolTip(str(item.destination))
        self._updating = False

    def _on_system_picked(self, row: int) -> None:
        item = self.items[row]
        system_id = self.combos[row].currentData()
        if system_id == item.system_id and item.manual:
            return
        item.retarget(self.config, system_id)
        item.manual = True  # choosing a system is the user's confirmation
        self._updating = True
        self.table.item(row, COL_MOVE).setCheckState(
            Qt.CheckState.Unchecked if item.exists else Qt.CheckState.Checked
        )
        self._updating = False
        self._paint_row(row)
        self._refresh_summary()

    # ----- results -----

    def selected_items(self) -> list[PlanItem]:
        return [
            item
            for row, item in enumerate(self.items)
            if self.table.item(row, COL_MOVE).checkState() == Qt.CheckState.Checked
        ]

    def keep_both(self) -> bool:
        return self.keep_both_box.isChecked()

    def _refresh_summary(self) -> None:
        if self._updating:
            return
        n = len(self.selected_items())
        self.move_btn.setText(f"Move {n} ROM{'s' if n != 1 else ''}")
        self.move_btn.setEnabled(n > 0)
