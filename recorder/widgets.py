"""Small reusable widgets used to build the main window."""
from __future__ import annotations

import datetime as _dt

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import theme


def make_card(title: str | None = None) -> tuple[QFrame, QVBoxLayout]:
    """A panel frame styled as a card, with an optional bold title row.

    Returns the frame (add it to a parent layout) and the inner layout
    (add the card's actual content to that).
    """
    frame = QFrame()
    frame.setProperty("role", "card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(10)

    if title:
        heading = QLabel(title)
        heading.setStyleSheet("font-size: 14px; font-weight: 600;")
        layout.addWidget(heading)

    return frame, layout


class StatusBadge(QWidget):
    """A colored status dot plus a headline and a smaller detail line.

    No animation here on purpose — this needs to be reliable when driven
    by signals from a worker thread, not flashy.
    """

    DOT_SIZE = 12

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self._dot = QLabel()
        self._dot.setFixedSize(self.DOT_SIZE, self.DOT_SIZE)
        self._apply_dot_color(theme.status_color("idle"))

        self._headline = QLabel("Idle")
        self._headline.setStyleSheet("font-size: 15px; font-weight: 600;")

        self._detail = QLabel("Set up your recording and press Start.")
        self._detail.setProperty("role", "subtitle")
        self._detail.setWordWrap(True)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        text_col.addWidget(self._headline)
        text_col.addWidget(self._detail)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)
        root.addWidget(self._dot, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(text_col, 1)

    def _apply_dot_color(self, color: str) -> None:
        self._dot.setStyleSheet(
            f"background-color: {color}; border-radius: {self.DOT_SIZE // 2}px;"
        )

    def set_status(self, state_key: str, headline: str, detail: str = "") -> None:
        self._apply_dot_color(theme.status_color(state_key))
        self._headline.setText(headline)
        self._detail.setText(detail)


class LogPanel(QPlainTextEdit):
    """A read-only, auto-scrolling, timestamped log."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("role", "log")
        self.setReadOnly(True)
        self.setMaximumBlockCount(2000)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def append_entry(self, level: str, text: str) -> None:
        timestamp = _dt.datetime.now().strftime("%H:%M:%S")
        color = theme.LOG_LEVEL_COLORS.get(level, theme.TEXT_SECONDARY)
        prefix = {"warn": "WARN", "error": "ERROR"}.get(level, "")
        label = f" [{prefix}]" if prefix else ""
        safe_text = (
            text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        self.appendHtml(
            f'<span style="color:{theme.TEXT_MUTED};">{timestamp}</span>'
            f'<span style="color:{color};">{label}</span> '
            f'<span style="color:{color};">{safe_text}</span>'
        )
        scrollbar = self.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())


class CollapsibleSection(QWidget):
    """A toggle button that shows/hides a content widget below it."""

    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._title = title

        self._toggle = QToolButton()
        self._toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle.clicked.connect(self._on_toggle_clicked)

        self._content_holder = QVBoxLayout()
        self._content_holder.setContentsMargins(0, 8, 0, 0)
        self._content: QWidget | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._toggle)
        root.addLayout(self._content_holder)

        self._expanded = False
        self._refresh_label()

    def set_content_widget(self, widget: QWidget) -> None:
        self._content = widget
        self._content_holder.addWidget(widget)
        widget.setVisible(self._expanded)

    def toggle(self) -> None:
        self._on_toggle_clicked()

    def _on_toggle_clicked(self) -> None:
        self._expanded = not self._expanded
        if self._content is not None:
            self._content.setVisible(self._expanded)
        self._refresh_label()

    def _refresh_label(self) -> None:
        arrow = "\u25be" if self._expanded else "\u25b8"
        self._toggle.setText(f"{arrow}  {self._title}")
