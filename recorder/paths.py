"""Filesystem path helpers.

Two different kinds of paths matter here, and they live in different places
once the app is packaged with PyInstaller:

- Bundled, read-only resources (the resolution-profile template images)
  live inside the PyInstaller bundle when frozen (``sys._MEIPASS``), or under
  ``assets/`` next to this file in dev mode.
- Writable runtime folders (``temp/`` for the raw per-game OBS recordings,
  ``output/`` for the combined video) must live next to the actual .exe so
  the user can find them, and so OBS can be pointed at the recordings
  folder.
"""
from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_root() -> Path:
    """Folder the .exe (or this source tree, in dev mode) lives in.

    Use this for anything the user needs to find or OBS needs to write
    into: temp/, output/.
    """
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def bundle_root() -> Path:
    """Folder bundled read-only resources are extracted to.

    Same as app_root() in dev mode; points inside the PyInstaller bundle
    when frozen (works for both --onedir and --onefile builds).
    """
    if is_frozen() and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent


def resource_path(*parts: str) -> Path:
    """Path to a bundled, read-only resource (e.g. a profile template image)."""
    return bundle_root().joinpath(*parts)


def temp_dir() -> Path:
    """Folder raw per-game OBS recordings land in. This is the path the user
    should set as their OBS recording output path."""
    d = app_root() / "temp"
    d.mkdir(parents=True, exist_ok=True)
    return d


def output_dir() -> Path:
    """Folder the final combined video gets written to."""
    d = app_root() / "output"
    d.mkdir(parents=True, exist_ok=True)
    return d
