"""Colour palette and stylesheet for the app.

The accent colour family is pulled from the Granblue UI itself (sampled
from the reference screenshots in the original instructions sheet — a
steel-blue in the ``#4F9DD6`` family), so the app feels visually related
to the game it's automating instead of looking like generic dev tooling.
"""
from __future__ import annotations

# --- base palette ---
BG = "#14181D"
PANEL = "#1B2128"
PANEL_ALT = "#10141A"
BORDER = "#2A323C"
TEXT_PRIMARY = "#E8EAED"
TEXT_SECONDARY = "#9AA4B2"
TEXT_MUTED = "#6B7280"

ACCENT = "#4F9DD6"
ACCENT_HOVER = "#6BB0E0"
ACCENT_PRESSED = "#3D85B8"

# --- status colours, keyed by the state_key the worker emits ---
STATUS_COLORS = {
    "idle": "#6B7280",
    "countdown": "#4F9DD6",
    "searching": "#4F9DD6",
    "loading": "#F2B84B",
    "recording": "#E5484D",
    "between": "#4F9DD6",
    "paused": "#A78BFA",
    "success": "#3FB67F",
    "error": "#E5484D",
    "stopped": "#6B7280",
}


def status_color(state_key: str) -> str:
    return STATUS_COLORS.get(state_key, STATUS_COLORS["idle"])


LOG_LEVEL_COLORS = {
    "info": TEXT_SECONDARY,
    "warn": "#F2B84B",
    "error": "#E5484D",
}


STYLESHEET = f"""
QWidget {{
    background-color: {BG};
    color: {TEXT_PRIMARY};
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 13px;
}}

QMainWindow {{
    background-color: {BG};
}}

QLabel {{
    background: transparent;
}}

QLabel[role="heading"] {{
    font-size: 18px;
    font-weight: 600;
    color: {TEXT_PRIMARY};
}}

QLabel[role="subtitle"] {{
    color: {TEXT_SECONDARY};
}}

QLabel[role="caption"] {{
    color: {TEXT_MUTED};
    font-size: 11px;
}}

QFrame[role="card"] {{
    background-color: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}

QPushButton {{
    background-color: #232B34;
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 7px 16px;
}}

QPushButton:hover {{
    background-color: #2C3640;
    border-color: #3A4452;
}}

QPushButton:pressed {{
    background-color: #1E252D;
}}

QPushButton:disabled {{
    color: {TEXT_MUTED};
    background-color: #1B2128;
    border-color: {BORDER};
}}

QPushButton[role="primary"] {{
    background-color: {ACCENT};
    border-color: {ACCENT};
    color: #0B1115;
    font-weight: 600;
}}

QPushButton[role="primary"]:hover {{
    background-color: {ACCENT_HOVER};
    border-color: {ACCENT_HOVER};
}}

QPushButton[role="primary"]:pressed {{
    background-color: {ACCENT_PRESSED};
    border-color: {ACCENT_PRESSED};
}}

QPushButton[role="primary"]:disabled {{
    background-color: #1B2128;
    border-color: {BORDER};
    color: {TEXT_MUTED};
}}

QPushButton[role="danger"]:disabled {{
    background-color: #1B2128;
    border-color: {BORDER};
    color: {TEXT_MUTED};
}}

QPushButton[role="danger"]:hover {{
    background-color: #3A2326;
    border-color: #5C2C30;
    color: #F3A6A9;
}}

QComboBox, QSpinBox {{
    background-color: {PANEL_ALT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 5px 8px;
    color: {TEXT_PRIMARY};
}}

QComboBox:hover, QSpinBox:hover {{
    border-color: #3A4452;
}}

QComboBox::drop-down {{
    border: none;
    width: 22px;
}}

QComboBox QAbstractItemView {{
    background-color: {PANEL};
    border: 1px solid {BORDER};
    selection-background-color: {ACCENT};
    selection-color: #0B1115;
    outline: none;
}}

QSpinBox::up-button, QSpinBox::down-button {{
    background-color: transparent;
    border: none;
    width: 16px;
}}

QCheckBox {{
    spacing: 8px;
}}

QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid {BORDER};
    background-color: {PANEL_ALT};
}}

QCheckBox::indicator:checked {{
    background-color: {ACCENT};
    border-color: {ACCENT};
}}

QProgressBar {{
    background-color: {PANEL_ALT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    text-align: center;
    color: {TEXT_PRIMARY};
    height: 18px;
}}

QProgressBar::chunk {{
    background-color: {ACCENT};
    border-radius: 5px;
}}

QPlainTextEdit[role="log"] {{
    background-color: {PANEL_ALT};
    border: 1px solid {BORDER};
    border-radius: 8px;
    color: {TEXT_SECONDARY};
    font-family: "Cascadia Code", "Consolas", monospace;
    font-size: 12px;
    padding: 6px;
}}

QToolButton {{
    background: transparent;
    border: none;
    color: {TEXT_SECONDARY};
}}

QToolButton:hover {{
    color: {TEXT_PRIMARY};
}}

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 0;
}}

QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 5px;
    min-height: 24px;
}}

QScrollBar::handle:vertical:hover {{
    background: #3A4452;
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
"""
