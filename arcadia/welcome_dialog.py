"""File > Get started: a short checklist for setting Arcadia up, shown the first time it runs."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout

from arcadia.config import Config
from arcadia.guide import Facts, Step, build_steps, gather, required_done
from arcadia.setup_dialog import _Busy
from arcadia.util import fit_label_height

GOOD = "#6fcf97"


class WelcomeDialog(QDialog, _Busy):
    def __init__(self, config: Config, actions: dict[str, Callable[[], None]], counts: Callable[[], dict[str, int]], parent=None):
        """actions maps a step key to what its button does; counts gives games per system (for the checks)."""
        super().__init__(parent)
        self.config = config
        self.actions = actions
        self.counts = counts
        self._task = None
        self.steps: list[Step] = []
        self.cards: dict[str, tuple[QLabel, QLabel, QLabel, QPushButton]] = {}
        self.setWindowTitle("Get started with Arcadia")
        self.setMinimumWidth(720)

        title = QLabel("Let's get you playing")
        title.setObjectName("gameTitle")
        self.summary = QLabel("Checking what's ready…")
        self.summary.setStyleSheet("color: rgba(236, 238, 244, 70%);")
        self.summary.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(self.summary)
        for key in ("folder", "games", "emulators", "bios", "sync"):
            layout.addWidget(self._card(key))
        self.status = QLabel("")
        self.bar = QProgressBar()
        self.bar.setVisible(False)
        layout.addWidget(self.status)
        layout.addWidget(self.bar)
        self.done_btn = QPushButton("Start playing")
        self.done_btn.setObjectName("primary")
        self.done_btn.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.done_btn)
        layout.addLayout(row)
        self.refresh()

    def _card(self, key: str) -> QFrame:
        card = QFrame()
        card.setStyleSheet("QFrame#card { background: rgba(255,255,255,6%); border-radius: 14px; }")
        card.setObjectName("card")
        badge = QLabel("•")
        badge.setFixedWidth(28)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet("font-size: 20px; font-weight: 800;")
        name = QLabel("")
        name.setStyleSheet("font-weight: 700; font-size: 15px;")
        detail = QLabel("")
        detail.setWordWrap(True)
        detail.setStyleSheet("color: rgba(236, 238, 244, 70%);")
        button = QPushButton("")
        button.setMinimumWidth(150)
        button.clicked.connect(lambda _c=False, k=key: self._act(k))
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(name)
        text.addWidget(detail)
        row = QHBoxLayout(card)
        row.setContentsMargins(14, 12, 14, 12)
        row.addWidget(badge)
        row.addLayout(text, 1)
        row.addWidget(button)
        self.cards[key] = (badge, name, detail, button)
        return card

    def refresh(self) -> None:
        counts = self.counts()
        self._run(lambda report: gather(self.config, counts), self._on_facts, "Checking…")

    def _on_facts(self, facts, error) -> None:
        if error is not None or not isinstance(facts, Facts):
            self.summary.setText(f"Couldn't check everything: {error}")
            return
        self.steps = build_steps(self.config, facts)
        for step in self.steps:
            badge, name, detail, button = self.cards[step.key]
            badge.setText("✓" if step.done else "•")
            badge.setStyleSheet(f"font-size: 20px; font-weight: 800; color: {GOOD if step.done else '#f2a33a'};")
            name.setText(step.title + ("  (optional)" if step.optional else ""))
            detail.setText(step.detail)
            button.setText(step.button)
        if required_done(self.steps):
            self.summary.setText("You're ready to play. The optional steps can wait; they're always under the File menu.")
        else:
            todo = [s.title for s in self.steps if not s.done and not s.optional]
            self.summary.setText("Still to do: " + ", ".join(t.lower() for t in todo) + ".")
        self._regrow()

    def _fit(self) -> None:
        fit_label_height(self.summary)
        for _badge, _name, detail, _button in self.cards.values():
            fit_label_height(detail)

    def _regrow(self) -> None:
        """Fit the text, then let the window take the height it now needs."""
        for _ in range(2):  # the width a label gets depends on its neighbours, so settle it twice
            self.layout().activate()
            self._fit()
            self.layout().invalidate()
        self.layout().activate()
        needed = self.layout().totalHeightForWidth(self.width())
        self.resize(self.width(), max(needed, self.minimumSizeHint().height(), self.height()))

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._regrow()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit()

    def _act(self, key: str) -> None:
        action = self.actions.get(key)
        if action is not None:
            action()
        self.refresh()

    def _busy_changed(self) -> None:
        busy = self._task is not None
        self.done_btn.setEnabled(not busy)
