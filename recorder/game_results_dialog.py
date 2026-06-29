"""Dialog shown before combining recordings.

Lets the user enter player names and mark each detected game as a win
for Player 1 or Player 2. Returns a ``SetInfo`` dataclass with all the
data the render pipeline needs to build the score overlay later.

Nothing about the video is touched here — this is pure data collection.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from . import theme


@dataclass
class GameResult:
    """Outcome of a single recorded game."""
    clip_path: Path
    winner: Optional[str] = None  # "p1" | "p2" | None (not yet set)


@dataclass
class SetInfo:
    """Everything collected from the dialog, ready for the render pipeline."""
    p1_name: str
    p2_name: str
    results: list[GameResult]

    @property
    def p1_wins(self) -> int:
        return sum(1 for r in self.results if r.winner == "p1")

    @property
    def p2_wins(self) -> int:
        return sum(1 for r in self.results if r.winner == "p2")

    def score_entering_game(self, index: int) -> tuple[int, int]:
        """Score (p1_wins, p2_wins) *before* game at ``index`` is played."""
        p1 = sum(1 for r in self.results[:index] if r.winner == "p1")
        p2 = sum(1 for r in self.results[:index] if r.winner == "p2")
        return p1, p2


class _GameRow(QWidget):
    """One row in the game list: game label, P1 radio, P2 radio."""

    def __init__(self, game_number: int, clip_path: Path, parent: QWidget | None = None):
        super().__init__(parent)
        self.clip_path = clip_path
        self._result: GameResult = GameResult(clip_path=clip_path)

        self._group = QButtonGroup(self)

        # --- game label ---
        label = QLabel(f"Game {game_number}")
        label.setStyleSheet(f"color: {theme.TEXT_PRIMARY}; font-weight: 600; min-width: 64px;")

        filename = QLabel(clip_path.name)
        filename.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 11px;")
        filename.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        filename.setWordWrap(False)

        # --- radio buttons ---
        self.p1_radio = QRadioButton("P1 win")
        self.p2_radio = QRadioButton("P2 win")
        self.p1_radio.setStyleSheet(f"color: {theme.TEXT_PRIMARY};")
        self.p2_radio.setStyleSheet(f"color: {theme.TEXT_PRIMARY};")

        self._group.addButton(self.p1_radio, 1)
        self._group.addButton(self.p2_radio, 2)
        self._group.buttonClicked.connect(self._on_selection_changed)

        # --- layout ---
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 4, 0, 4)
        row.setSpacing(12)

        labels = QVBoxLayout()
        labels.setSpacing(1)
        labels.addWidget(label)
        labels.addWidget(filename)

        row.addLayout(labels)
        row.addStretch(1)
        row.addWidget(self.p1_radio)
        row.addWidget(self.p2_radio)

    def _on_selection_changed(self) -> None:
        checked_id = self._group.checkedId()
        self._result.winner = "p1" if checked_id == 1 else "p2"
        # Bubble up — parent dialog listens via the row list
        parent = self.parent()
        while parent is not None:
            if isinstance(parent, GameResultsDialog):
                parent._refresh_score()
                break
            parent = parent.parent()

    @property
    def result(self) -> GameResult:
        return self._result

    def winner(self) -> Optional[str]:
        return self._result.winner


class GameResultsDialog(QDialog):
    """Pre-combine dialog: enter player names + mark each game outcome.

    Call ``set_info()`` on the accepted result to get the ``SetInfo``
    ready to pass to the render pipeline.
    """

    def __init__(self, clip_paths: list[Path], parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Set results")
        self.setMinimumWidth(500)
        self.setModal(True)

        self._rows: list[_GameRow] = []
        self._build_ui(clip_paths)
        self._refresh_score()

    # ------------------------------------------------------------------ build
    def _build_ui(self, clip_paths: list[Path]) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(14)
        root.setContentsMargins(20, 20, 20, 20)

        # --- player names ---
        names_frame = QFrame()
        names_frame.setProperty("role", "card")
        names_layout = QVBoxLayout(names_frame)
        names_layout.setContentsMargins(14, 12, 14, 12)
        names_layout.setSpacing(10)

        names_heading = QLabel("Player names")
        names_heading.setStyleSheet("font-weight: 600; font-size: 14px;")
        names_layout.addWidget(names_heading)

        p1_row = QHBoxLayout()
        p1_label = QLabel("Player 1")
        p1_label.setFixedWidth(70)
        p1_label.setStyleSheet(f"color: {theme.TEXT_SECONDARY};")
        self.p1_name_field = QLineEdit()
        self.p1_name_field.setPlaceholderText("Player 1")
        self.p1_name_field.textChanged.connect(self._refresh_player_labels)
        p1_row.addWidget(p1_label)
        p1_row.addWidget(self.p1_name_field)
        names_layout.addLayout(p1_row)

        p2_row = QHBoxLayout()
        p2_label = QLabel("Player 2")
        p2_label.setFixedWidth(70)
        p2_label.setStyleSheet(f"color: {theme.TEXT_SECONDARY};")
        self.p2_name_field = QLineEdit()
        self.p2_name_field.setPlaceholderText("Player 2")
        self.p2_name_field.textChanged.connect(self._refresh_player_labels)
        p2_row.addWidget(p2_label)
        p2_row.addWidget(self.p2_name_field)
        names_layout.addLayout(p2_row)

        root.addWidget(names_frame)

        # --- game list ---
        games_frame = QFrame()
        games_frame.setProperty("role", "card")
        games_layout = QVBoxLayout(games_frame)
        games_layout.setContentsMargins(14, 12, 14, 12)
        games_layout.setSpacing(6)

        games_heading = QLabel(f"Games  ({len(clip_paths)} recorded)")
        games_heading.setStyleSheet("font-weight: 600; font-size: 14px;")
        games_layout.addWidget(games_heading)

        # Column headers
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 4, 0, 0)
        spacer = QLabel("")
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._p1_col_label = QLabel("P1 win")
        self._p2_col_label = QLabel("P2 win")
        for lbl in (self._p1_col_label, self._p2_col_label):
            lbl.setStyleSheet(
                f"color: {theme.TEXT_MUTED}; font-size: 11px; min-width: 58px;"
            )
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_row.addWidget(spacer)
        header_row.addWidget(self._p1_col_label)
        header_row.addWidget(self._p2_col_label)
        games_layout.addLayout(header_row)

        # Divider
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"color: {theme.BORDER};")
        games_layout.addWidget(line)

        # Scrollable game rows
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(0)

        for i, path in enumerate(clip_paths, start=1):
            row = _GameRow(i, path, parent=self)
            self._rows.append(row)
            scroll_layout.addWidget(row)

            if i < len(clip_paths):
                divider = QFrame()
                divider.setFrameShape(QFrame.Shape.HLine)
                divider.setStyleSheet(f"background: {theme.BORDER}; max-height: 1px;")
                scroll_layout.addWidget(divider)

        scroll_area = QScrollArea()
        scroll_area.setWidget(scroll_content)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setMaximumHeight(280)
        scroll_area.setStyleSheet("background: transparent;")
        games_layout.addWidget(scroll_area)

        root.addWidget(games_frame)

        # --- live score ---
        score_frame = QFrame()
        score_frame.setProperty("role", "card")
        score_layout = QHBoxLayout(score_frame)
        score_layout.setContentsMargins(14, 10, 14, 10)

        score_heading = QLabel("Score")
        score_heading.setStyleSheet(f"color: {theme.TEXT_SECONDARY};")
        self._score_label = QLabel("—")
        self._score_label.setStyleSheet(
            f"font-size: 20px; font-weight: 700; color: {theme.ACCENT};"
        )
        self._score_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        score_layout.addWidget(score_heading)
        score_layout.addStretch(1)
        score_layout.addWidget(self._score_label)

        root.addWidget(score_frame)

        # --- dialog buttons ---
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    # ----------------------------------------------------------------- logic
    def _p1_display_name(self) -> str:
        return self.p1_name_field.text().strip() or "Player 1"

    def _p2_display_name(self) -> str:
        return self.p2_name_field.text().strip() or "Player 2"

    def _refresh_player_labels(self) -> None:
        """Update the column headers when names are edited."""
        p1 = self._p1_display_name()
        p2 = self._p2_display_name()
        self._p1_col_label.setText(f"{p1} win")
        self._p2_col_label.setText(f"{p2} win")
        for row in self._rows:
            row.p1_radio.setText(f"{p1} win")
            row.p2_radio.setText(f"{p2} win")
        self._refresh_score()

    def _refresh_score(self) -> None:
        p1_wins = sum(1 for r in self._rows if r.winner() == "p1")
        p2_wins = sum(1 for r in self._rows if r.winner() == "p2")
        unset = sum(1 for r in self._rows if r.winner() is None)
        p1 = self._p1_display_name()
        p2 = self._p2_display_name()

        if p1_wins == 0 and p2_wins == 0:
            self._score_label.setText("—")
        else:
            self._score_label.setText(f"{p1}  {p1_wins} – {p2_wins}  {p2}")

        # Grey out the OK button if any games are unset
        ok_btn = self.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn:
            ok_btn.setEnabled(unset == 0)
            ok_btn.setToolTip(
                "" if unset == 0
                else f"{unset} game(s) not yet marked — mark all games before combining."
            )

    def _on_ok(self) -> None:
        unset = [i + 1 for i, r in enumerate(self._rows) if r.winner() is None]
        if unset:
            QMessageBox.warning(
                self,
                "Unmarked games",
                f"Game(s) {', '.join(str(n) for n in unset)} haven't been marked yet.\n"
                "Mark every game as a win for Player 1 or Player 2 before combining.",
            )
            return
        self.accept()

    # ---------------------------------------------------------------- result
    def set_info(self) -> SetInfo:
        """Call this after ``exec()`` returns ``Accepted``."""
        return SetInfo(
            p1_name=self._p1_display_name(),
            p2_name=self._p2_display_name(),
            results=[r.result for r in self._rows],
        )
