"""Renders the per-game score overlay onto a Pillow Image.

The workflow:
    1. Load the overlay PNG (full canvas, transparent except for the graphic).
    2. Scale it to match the actual video dimensions (designed at 2560×1440;
       scales proportionally for 1080p or any other resolution).
    3. Draw player names and scores into their respective zones using a
       font that auto-shrinks to fit whatever name length is given.
    4. Return the composited RGBA image ready to be handed to moviepy as
       an ImageClip overlay.

Zone detection:
    Zones are measured automatically from the overlay PNG by scanning for
    distinct contiguous groups of visible (non-transparent) pixels across
    a horizontal slice. For the default overlay this produces four zones:
      - P1 name bar (left)
      - P1 score square (inner-left)
      - P2 score square (inner-right)
      - P2 name bar (right)

    Zone coordinates are cached per overlay path so the scan only runs
    once per session. If you design a new overlay, pass its path to
    ``render_overlay_frame()`` and the zones will be auto-detected from it.
"""
from __future__ import annotations

import functools
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

# Design canvas dimensions — the overlay PNG must be made at this resolution.
DESIGN_W = 2560
DESIGN_H = 1440

# Text colors
NAME_COLOR   = (15, 15, 15, 255)    # dark on the light gray name bars
SCORE_COLOR  = (255, 255, 255, 255) # white on the dark score squares

# Inner margin applied to name bars so text doesn't hug the tapered edges
NAME_MARGIN_PX = 30


@dataclass
class OverlayZones:
    """Pixel-space bounding boxes for each text zone at design resolution."""
    p1_name:  tuple[int, int, int, int]   # (x1, y1, x2, y2)
    p1_score: tuple[int, int, int, int]
    p2_score: tuple[int, int, int, int]
    p2_name:  tuple[int, int, int, int]


def _detect_zones(overlay_path: Path) -> OverlayZones:
    """Auto-detect the four text zones from a 2560×1440 overlay PNG.

    Scans a horizontal row near the vertical mid-point of the visible
    graphic and groups contiguous visible columns into elements, then
    maps them: element 0 = P1 name bar, 1 = P1 score square,
    2 = P2 score square, 3 = P2 name bar.
    """
    import numpy as np

    img = Image.open(overlay_path).convert("RGBA")
    arr = np.array(img)
    alpha = arr[:, :, 3]

    # Find the vertical centre of the graphic
    visible_rows = np.where(np.any(alpha > 10, axis=1))[0]
    if len(visible_rows) == 0:
        raise ValueError(f"Overlay at {overlay_path} has no visible pixels.")
    mid_row = int((visible_rows.min() + visible_rows.max()) / 2)
    bar_bottom = int(visible_rows.max())

    # Find all visible columns at that row and group into contiguous runs
    row_alpha = alpha[mid_row, :]
    visible_cols = np.where(row_alpha > 10)[0]
    if len(visible_cols) < 4:
        raise ValueError(
            f"Expected at least 4 distinct elements in overlay at row {mid_row}, "
            f"found {len(visible_cols)} visible pixels."
        )

    groups: list[tuple[int, int]] = []
    start = int(visible_cols[0])
    prev  = int(visible_cols[0])
    for col in visible_cols[1:]:
        col = int(col)
        if col - prev > 10:  # gap larger than 10px = new element
            groups.append((start, prev))
            start = col
        prev = col
    groups.append((start, prev))

    if len(groups) != 4:
        raise ValueError(
            f"Expected exactly 4 distinct zones in the overlay, detected {len(groups)}: {groups}. "
            "Make sure the overlay has P1 name bar, P1 score square, P2 score square, P2 name bar "
            "separated by transparent gaps."
        )

    p1_bar, p1_sq, p2_sq, p2_bar = groups
    top = 0

    return OverlayZones(
        p1_name  = (p1_bar[0] + NAME_MARGIN_PX, top, p1_bar[1] - NAME_MARGIN_PX, bar_bottom),
        p1_score = (p1_sq[0],  top, p1_sq[1],  bar_bottom),
        p2_score = (p2_sq[0],  top, p2_sq[1],  bar_bottom),
        p2_name  = (p2_bar[0] + NAME_MARGIN_PX, top, p2_bar[1] - NAME_MARGIN_PX, bar_bottom),
    )


@functools.lru_cache(maxsize=4)
def _get_zones(overlay_path_str: str) -> OverlayZones:
    """Cached zone detection — runs once per overlay file per session."""
    return _detect_zones(Path(overlay_path_str))


def _fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    box: tuple[int, int, int, int],
    fill: tuple[int, int, int, int],
    font_path: Optional[Path],
    max_size: int = 52,
    min_size: int = 8,
) -> None:
    """Draw ``text`` centered in ``box``, shrinking the font until it fits."""
    x1, y1, x2, y2 = box
    box_w, box_h = x2 - x1, y2 - y1

    for size in range(max_size, min_size - 1, -1):
        if font_path and font_path.exists():
            font = ImageFont.truetype(str(font_path), size)
        else:
            font = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]

        if tw <= box_w and th <= box_h:
            tx = x1 + (box_w - tw) // 2
            ty = y1 + (box_h - th) // 2
            draw.text((tx, ty), text, font=font, fill=fill)
            return


def _scale_box(
    box: tuple[int, int, int, int], sx: float, sy: float
) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = box
    return (round(x1 * sx), round(y1 * sy), round(x2 * sx), round(y2 * sy))


def render_overlay_frame(
    overlay_path: Path,
    font_path: Optional[Path],
    video_w: int,
    video_h: int,
    p1_name: str,
    p2_name: str,
    p1_score: int,
    p2_score: int,
) -> Image.Image:
    """Return a full-canvas RGBA overlay image ready to paste onto a video frame.

    The returned image is ``video_w × video_h`` with a transparent background
    except for the overlay graphic and text.
    """
    zones = _get_zones(str(overlay_path))

    overlay = Image.open(overlay_path).convert("RGBA")

    # Scale overlay + zones to match actual video dimensions
    if overlay.size != (video_w, video_h):
        sx = video_w / DESIGN_W
        sy = video_h / DESIGN_H
        new_w = round(DESIGN_W * sx)
        new_h = round(DESIGN_H * sy)
        overlay = overlay.resize((new_w, new_h), Image.LANCZOS)
        canvas = Image.new("RGBA", (video_w, video_h), (0, 0, 0, 0))
        canvas.paste(overlay, (0, 0))
        overlay = canvas
        zones = OverlayZones(
            p1_name  = _scale_box(zones.p1_name,  sx, sy),
            p1_score = _scale_box(zones.p1_score, sx, sy),
            p2_score = _scale_box(zones.p2_score, sx, sy),
            p2_name  = _scale_box(zones.p2_name,  sx, sy),
        )

    draw = ImageDraw.Draw(overlay)
    _fit_text(draw, p1_name,       zones.p1_name,  NAME_COLOR,  font_path)
    _fit_text(draw, str(p1_score), zones.p1_score, SCORE_COLOR, font_path)
    _fit_text(draw, str(p2_score), zones.p2_score, SCORE_COLOR, font_path)
    _fit_text(draw, p2_name,       zones.p2_name,  NAME_COLOR,  font_path)

    return overlay
