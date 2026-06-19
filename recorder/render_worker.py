"""Combines the per-game recordings into one video.

This preserves the original ``render_video()``'s trim and crossfade math
exactly (trim 3.5s off the end of each clip, 0.3s cross-fade between
them) — that's the part that actually defines what the output looks and
feels like, so it's untouched.

What's different from the original:
    - Files are explicitly sorted by name before being combined. The
      original used the raw, unsorted result of ``os.listdir()``, which
      happened to come out in chronological order often enough to work,
      but was never actually guaranteed to — it was relying on luck plus
      OBS's timestamped filenames. Sorting by filename is what actually
      makes "oldest recording first" reliable.
    - Files are filtered by known video extensions instead of "anything
      that isn't named .gitignore." A stray non-video file in the
      recordings folder would have crashed the original.
    - Output goes to a dedicated ``output/`` folder with a timestamped
      filename, instead of overwriting a single hardcoded ``output.mp4``
      in the current directory every time.
    - Progress is reported through a Qt signal (moviepy's own progress
      bars are bridged into a single 0-1 float) instead of printing
      ``clip.start`` / ``clip.duration`` to a console.
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QThread, Signal
from proglog import ProgressBarLogger

from .paths import output_dir, temp_dir

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".flv"}
TRIM_END_SECONDS = 3.5
CROSSFADE_SECONDS = 0.3


class _QtBridgeLogger(ProgressBarLogger):
    """Turns moviepy's internal progress bars into a single 0-1 float.

    moviepy reports progress through one or more named bars (video frames
    as 't', audio chunks as 'chunk', possibly others depending on the
    clip). Rather than trying to guess which bars will appear or weight
    them against each other, this just tracks the single highest
    index/total fraction seen across all of them so far. In practice
    these bars run one after another, so the result is a value that
    climbs from 0 to 1 without jumping backward.
    """

    def __init__(self, on_progress: Callable[[float], None]):
        super().__init__()
        self._on_progress = on_progress
        self._max_fraction = 0.0

    def bars_callback(self, bar, attr, value, old_value=None):  # noqa: D401
        if attr != "index":
            return
        total = self.bars.get(bar, {}).get("total")
        if not total:
            return
        fraction = max(0.0, min(1.0, value / total))
        if fraction > self._max_fraction:
            self._max_fraction = fraction
            self._on_progress(self._max_fraction)


class RenderWorker(QThread):
    """Combines every recording in the source folder into one video.

    Used both right after an automation run finishes (if "auto-combine"
    is checked) and from the standalone "Combine recordings" button, so
    it's self-contained and doesn't assume anything about how it was
    triggered.
    """

    progress = Signal(float)  # 0.0 - 1.0
    log_message = Signal(str, str)  # level, text
    finished_render = Signal(bool, str)  # success, output path or error message

    def __init__(self, source_dir: Optional[Path] = None, parent=None):
        super().__init__(parent)
        self.source_dir = Path(source_dir) if source_dir else temp_dir()

    def run(self) -> None:
        try:
            self._render()
        except Exception as exc:  # noqa: BLE001 - surface any failure to the GUI
            message = f"Render failed: {exc}"
            self.log_message.emit("error", message)
            self.finished_render.emit(False, message)

    def _find_clips(self) -> list[Path]:
        if not self.source_dir.is_dir():
            return []
        files = [
            p
            for p in self.source_dir.iterdir()
            if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS
        ]
        return sorted(files, key=lambda p: p.name)

    def _render(self) -> None:
        # Imported lazily: moviepy pulls in numpy/imageio/PIL, which is
        # only worth the load time when an actual render is happening.
        from moviepy import CompositeVideoClip, VideoFileClip, vfx

        clip_paths = self._find_clips()
        if not clip_paths:
            message = (
                f"No recordings found in {self.source_dir}. Make sure OBS's "
                "recording output path is set to that folder."
            )
            self.log_message.emit("error", message)
            self.finished_render.emit(False, message)
            return

        self.log_message.emit(
            "info", f"Combining {len(clip_paths)} recording(s) from {self.source_dir}"
        )

        clips = []
        for clip_path in clip_paths:
            clip = VideoFileClip(str(clip_path)).subclipped(0, -TRIM_END_SECONDS)
            clips.append(clip)
            self.log_message.emit(
                "info", f"Loaded {clip_path.name} ({clip.duration:.1f}s after trim)"
            )

        clips[0].start = 0
        for i in range(1, len(clips)):
            clips[i] = clips[i].with_start(
                clips[i - 1].duration + clips[i - 1].start - CROSSFADE_SECONDS
            ).with_effects([vfx.CrossFadeIn(CROSSFADE_SECONDS)])

        final_clip = CompositeVideoClip(clips)

        timestamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = output_dir() / f"output_{timestamp}.mp4"

        self.log_message.emit("info", "Encoding combined video…")
        bridge_logger = _QtBridgeLogger(self.progress.emit)
        final_clip.write_videofile(str(output_path), logger=bridge_logger)

        self.progress.emit(1.0)
        self.log_message.emit("info", f"Wrote {output_path}")
        self.finished_render.emit(True, str(output_path))
