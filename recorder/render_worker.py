"""Combines per-game recordings into one video using a direct ffmpeg pipeline.

Why ffmpeg directly instead of moviepy for encoding:
    The original implementation used moviepy to composite the score overlay
    onto every video frame in Python — roughly 18,000 frames per game at
    60fps. That Python loop was the bottleneck (25+ minutes for a 3-game
    set). Handing the same job to ffmpeg's native overlay and xfade filters
    runs in 1–3 minutes on software encoding, and under 60 seconds with a
    GPU encoder.

The pipeline for N clips:
    1. Probe each clip's duration and video size via ffmpeg stderr.
    2. Pre-render the score overlay for each game as a PNG (Pillow, same as
       before) and write to a temp folder.
    3. Build a single ffmpeg filter_complex that trims each clip, composites
       its overlay PNG, chains them with xfade cross-fades, and concatenates
       the audio tracks.
    4. Run ffmpeg as a subprocess, parse its -progress output for the
       progress bar and log lines, collect stderr for error reporting.
    5. Auto-detect the best available hardware encoder (NVENC → AMF →
       QuickSync → software libx264 -preset fast).
"""
from __future__ import annotations

import datetime as _dt
import re
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QThread, Signal

from .paths import output_dir, temp_dir

if TYPE_CHECKING:
    from .game_results_dialog import SetInfo

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".flv"}
TRIM_END_SECONDS  = 3.5
CROSSFADE_SECONDS = 0.3

# Hardware encoders to try, in preference order.  Each entry is
# (ffmpeg_codec_name, display_name, extra_args).
_HW_ENCODERS = [
    ("h264_nvenc", "NVIDIA NVENC",     ["-preset", "fast", "-rc", "vbr", "-cq", "18"]),
    ("hevc_nvenc", "NVIDIA NVENC H265",["-preset", "fast", "-rc", "vbr", "-cq", "20"]),
    ("h264_amf",   "AMD AMF",          ["-quality", "speed"]),
    ("h264_qsv",   "Intel QuickSync",  ["-preset", "fast"]),
]
_SW_ENCODER = ("libx264", "CPU (software x264)", ["-preset", "fast", "-crf", "18"])

# Log a progress line every this many percent during encoding.
_LOG_EVERY_PCT = 10


class RenderWorker(QThread):
    """Combines every recording in the source folder into one video."""

    progress       = Signal(float)      # 0.0 – 1.0
    log_message    = Signal(str, str)   # level, text
    finished_render = Signal(bool, str) # success, output path or error message

    def __init__(
        self,
        source_dir: Optional[Path] = None,
        set_info:   Optional["SetInfo"] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.source_dir = Path(source_dir) if source_dir else temp_dir()
        self.set_info   = set_info

    def run(self) -> None:
        try:
            self._render()
        except Exception as exc:            # noqa: BLE001
            msg = f"Render failed: {exc}"
            self.log_message.emit("error", msg)
            self.finished_render.emit(False, msg)

    # ---------------------------------------------------------------- internal

    def _find_clips(self) -> list[Path]:
        if not self.source_dir.is_dir():
            return []
        return sorted(
            (p for p in self.source_dir.iterdir()
             if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS),
            key=lambda p: p.name,
        )

    def _render(self) -> None:
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

        clip_paths = self._find_clips()
        if not clip_paths:
            msg = (
                f"No recordings found in {self.source_dir}. "
                "Make sure OBS's recording output path is set to that folder."
            )
            self.log_message.emit("error", msg)
            self.finished_render.emit(False, msg)
            return

        self.log_message.emit(
            "info", f"Combining {len(clip_paths)} recording(s) from {self.source_dir}"
        )

        # --- probe durations and video size ---
        durations:  list[float] = []
        fps_values: list[float] = []
        video_size: tuple[int, int] | None = None
        has_audio = True
        for p in clip_paths:
            info = self._probe(ffmpeg, p)
            if info is None:
                msg = f"Could not read metadata from {p.name} — is it a valid video file?"
                self.log_message.emit("error", msg)
                self.finished_render.emit(False, msg)
                return
            dur, size, clip_has_audio, clip_fps = info
            durations.append(dur)
            fps_values.append(clip_fps)
            if video_size is None and size is not None:
                video_size = size
            if not clip_has_audio:
                has_audio = False
            self.log_message.emit(
                "info",
                f"  {p.name}: {dur:.2f}s  {size}  {clip_fps:.0f}fps"
                + ("  (no audio)" if not clip_has_audio else ""),
            )

        if video_size is None:
            video_size = (1920, 1080)

        trimmed = [max(0.1, d - TRIM_END_SECONDS) for d in durations]
        n = len(clip_paths)
        total_out_duration = sum(trimmed) - (n - 1) * CROSSFADE_SECONDS

        # --- pre-render overlay PNGs to temp files ---
        tmp_dir: str | None = None
        overlay_files: list[str] = []
        try:
            if self.set_info is not None:
                from .overlay_renderer import render_overlay_frame
                from .paths import font_path, overlay_path as default_overlay_path
                _ovpath  = default_overlay_path()
                _fntpath = font_path()
                if _ovpath.exists():
                    tmp_dir = tempfile.mkdtemp(prefix="gbvsr_overlay_")
                    vw, vh  = video_size
                    for i in range(n):
                        p1s, p2s = self.set_info.score_entering_game(i)
                        img = render_overlay_frame(
                            overlay_path=_ovpath, font_path=_fntpath,
                            video_w=vw, video_h=vh,
                            p1_name=self.set_info.p1_name,
                            p2_name=self.set_info.p2_name,
                            p1_score=p1s, p2_score=p2s,
                        )
                        out_png = str(Path(tmp_dir) / f"overlay_{i}.png")
                        img.save(out_png)
                        overlay_files.append(out_png)
                    self.log_message.emit("info", f"Score overlays pre-rendered ({n} frame(s)).")
                else:
                    self.log_message.emit("warn", "Overlay PNG not found — encoding without score overlay.")

            # --- pick encoder ---
            encoder, enc_name, enc_args = self._detect_encoder(ffmpeg)
            self.log_message.emit("info", f"Encoder: {enc_name}")

            # --- build and run ffmpeg ---
            timestamp   = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = output_dir() / f"output_{timestamp}.mp4"

            args = _build_ffmpeg_args(
                ffmpeg=ffmpeg,
                clip_paths=clip_paths,
                trimmed=trimmed,
                fps_values=fps_values,
                overlay_files=overlay_files,
                output_path=output_path,
                encoder=encoder,
                enc_args=enc_args,
                has_audio=has_audio,
            )

            self.log_message.emit("info", "Encoding combined video…")
            ok = self._run_ffmpeg(args, total_out_duration)

            if ok:
                self.progress.emit(1.0)
                self.log_message.emit("info", f"Wrote {output_path}")
                self.finished_render.emit(True, str(output_path))
            else:
                self.finished_render.emit(False, "Encoding failed — see the log for details.")

        finally:
            if tmp_dir:
                shutil.rmtree(tmp_dir, ignore_errors=True)

    # ----------------------------------------------------------------- helpers

    @staticmethod
    def _probe(ffmpeg: str, path: Path) -> tuple[float, tuple[int, int] | None, bool, float] | None:
        """Return (duration_secs, (width, height)|None, has_audio, fps) from ffmpeg stderr."""
        try:
            result = subprocess.run(
                [ffmpeg, "-i", str(path)],
                capture_output=True, text=True, timeout=30,
            )
        except Exception:
            return None

        duration:  float | None          = None
        size:      tuple[int, int] | None = None
        has_audio: bool                  = False
        fps:       float                 = 60.0  # safe default for GBVSR

        for line in result.stderr.splitlines():
            if duration is None and "Duration:" in line:
                m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", line)
                if m:
                    h, mn, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
                    duration = h * 3600 + mn * 60 + s
            if "Stream" in line:
                if "Video:" in line:
                    if size is None:
                        m = re.search(r"(\d{3,4})x(\d{3,4})", line)
                        if m:
                            size = (int(m.group(1)), int(m.group(2)))
                    # Parse fps: "24 fps" or "59.94 fps"
                    mf = re.search(r"([\d.]+) fps", line)
                    if mf:
                        fps = float(mf.group(1))
                if "Audio:" in line:
                    has_audio = True

        if duration is None:
            return None
        return duration, size, has_audio, fps

    def _detect_encoder(self, ffmpeg: str) -> tuple[str, str, list[str]]:
        """Try each hardware encoder with a 1-frame test; fall back to software."""
        # Query available encoders first — quick text scan, no actual encode
        try:
            enc_list = subprocess.run(
                [ffmpeg, "-encoders"], capture_output=True, text=True, timeout=10
            ).stdout
        except Exception:
            enc_list = ""

        for codec, name, extra in _HW_ENCODERS:
            if codec not in enc_list:
                continue
            # The encoder binary exists — do a 1-frame smoke test to confirm
            # the hardware is actually present (driver could be missing etc.)
            try:
                test = subprocess.run(
                    [
                        ffmpeg, "-y",
                        "-f", "lavfi", "-i", "color=black:s=64x64:r=1",
                        "-frames:v", "1",
                        "-c:v", codec,
                        "-f", "null", "-",
                    ],
                    capture_output=True, timeout=15,
                )
                if test.returncode == 0:
                    return codec, name, extra
            except Exception:
                continue

        return _SW_ENCODER

    def _run_ffmpeg(self, args: list[str], total_secs: float) -> bool:
        """Run ffmpeg, stream -progress output to the progress bar + log."""
        self.log_message.emit("info", f"  Command: {' '.join(args[:6])} …")

        stderr_lines: list[str] = []

        # On Windows, CREATE_NO_WINDOW prevents ffmpeg from being attached to
        # the same console/process group as our app. Without it, some Windows
        # configurations propagate signals from the child process (e.g. when
        # ffmpeg finishes) back to the parent, which can close the app window.
        import platform
        popen_kwargs: dict = dict(
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        if platform.system() == "Windows":
            popen_kwargs["creationflags"] = (
                subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
            )

        try:
            proc = subprocess.Popen(args, **popen_kwargs)
        except Exception as exc:
            self.log_message.emit("error", f"Could not start ffmpeg: {exc}")
            return False

        # Read stderr in a background thread to avoid blocking.
        # Non-daemon so it always drains fully even if the QThread is stopping.
        def _drain_stderr() -> None:
            for line in proc.stderr:
                stderr_lines.append(line.rstrip())

        t = threading.Thread(target=_drain_stderr, daemon=False)
        t.start()

        # Parse stdout (-progress pipe:1 format)
        last_logged_pct = -_LOG_EVERY_PCT
        progress_data: dict[str, str] = {}

        for raw in proc.stdout:
            line = raw.rstrip()
            if "=" not in line:
                continue
            key, _, val = line.partition("=")
            progress_data[key] = val

            if key != "progress":
                continue

            # A full progress group just ended — process it
            us_str = progress_data.get("out_time_us", "N/A")
            if us_str not in ("N/A", ""):
                try:
                    us   = int(us_str)
                    secs = us / 1_000_000
                    frac = min(1.0, secs / total_secs) if total_secs > 0 else 0.0
                    self.progress.emit(frac)

                    pct = frac * 100
                    if pct >= last_logged_pct + _LOG_EVERY_PCT or val == "end":
                        last_logged_pct = pct
                        fps   = progress_data.get("fps",   "?")
                        speed = progress_data.get("speed", "?")
                        frame = progress_data.get("frame", "?")
                        self.log_message.emit(
                            "info",
                            f"  Video: {pct:.0f}%  frame {frame}  {fps} fps  {speed}",
                        )
                except (ValueError, ZeroDivisionError):
                    pass

            progress_data = {}

        proc.wait()
        t.join(timeout=5)

        if proc.returncode != 0:
            # Surface the last chunk of ffmpeg stderr so the user can see
            # what went wrong without hunting through a log file
            relevant = [l for l in stderr_lines if l and not l.startswith("frame=")][-30:]
            for line in relevant:
                self.log_message.emit("warn", f"  ffmpeg: {line}")
            self.log_message.emit(
                "error",
                f"ffmpeg exited with code {proc.returncode} — see lines above for details."
            )
            return False

        return True


# ------------------------------------------------------------------ pure helpers

def _build_ffmpeg_args(
    ffmpeg:        str,
    clip_paths:    list[Path],
    trimmed:       list[float],
    fps_values:    list[float],
    overlay_files: list[str],
    output_path:   Path,
    encoder:       str,
    enc_args:      list[str],
    has_audio:     bool = True,
) -> list[str]:
    """Assemble the full ffmpeg command for the combined video."""
    n           = len(clip_paths)
    has_overlay = len(overlay_files) == n

    # --- inputs ---
    inputs: list[str] = []
    for p in clip_paths:
        inputs += ["-i", str(p)]
    if has_overlay:
        for ov in overlay_files:
            inputs += ["-i", ov]

    # --- filter_complex ---
    parts:      list[str] = []
    vid_tags:   list[str] = []
    aud_tags:   list[str] = []

    for i, (d, fps) in enumerate(zip(trimmed, fps_values)):
        # Trim video + force constant frame rate (xfade requires CFR)
        tv = f"tv{i}"
        parts.append(
            f"[{i}:v]trim=end={d:.6f},setpts=PTS-STARTPTS,fps={fps:.3f}[{tv}]"
        )

        # Overlay PNG if available
        if has_overlay:
            ov_input_idx = n + i
            ov = f"ov{i}"
            parts.append(
                f"[{tv}][{ov_input_idx}:v]overlay=0:0:format=auto[{ov}]"
            )
            vid_tags.append(f"[{ov}]")
        else:
            vid_tags.append(f"[{tv}]")

        # Audio trim (only when clips have audio).
        # apad=whole_dur ensures the segment is at least d seconds (OBS AAC
        # frames don't divide evenly into arbitrary durations, so the audio
        # can come out fractionally short; silence-padding protects acrossfade).
        if has_audio:
            at = f"at{i}"
            parts.append(
                f"[{i}:a]atrim=end={d:.6f},asetpts=PTS-STARTPTS"
                f",apad=whole_dur={d:.6f}"
                f"[{at}]"
            )
            aud_tags.append(f"[{at}]")

    # Video: xfade chain (or pass-through for a single clip)
    if n == 1:
        parts.append(f"{vid_tags[0]}copy[vout]")
    else:
        cumulative = 0.0
        prev = vid_tags[0]
        for k in range(1, n):
            cumulative += trimmed[k - 1]
            offset = cumulative - k * CROSSFADE_SECONDS
            out = "[vout]" if k == n - 1 else f"[xf{k}]"
            parts.append(
                f"{prev}{vid_tags[k]}"
                f"xfade=transition=fade:duration={CROSSFADE_SECONDS}:offset={offset:.6f}"
                f"{out}"
            )
            prev = out

    # Audio: acrossfade chain — mirrors the xfade chain exactly.
    #
    # WHY NOT concat?
    # xfade makes video clips OVERLAP by CROSSFADE_SECONDS (game N+1 video
    # starts before game N video ends). concat makes audio clips play
    # SEQUENTIALLY with no overlap. That 0.3s gap accumulates at every
    # boundary: 0.3s out of sync after game 2, 0.6s after game 3, etc.
    #
    # acrossfade consumes the same 0.3s from each boundary that xfade does,
    # so the total audio duration equals the total video duration and they
    # stay perfectly locked no matter how many games are in the set.
    if has_audio:
        if n == 1:
            parts.append(f"{aud_tags[0]}acopy[aout]")
        else:
            prev_a = aud_tags[0]
            for k in range(1, n):
                out_a = "[aout]" if k == n - 1 else f"[axf{k}]"
                parts.append(
                    f"{prev_a}{aud_tags[k]}"
                    f"acrossfade=d={CROSSFADE_SECONDS}:c1=tri:c2=tri"
                    f"{out_a}"
                )
                prev_a = out_a

    filter_complex = ";\n".join(parts)

    audio_args = ["-map", "[aout]", "-c:a", "aac", "-b:a", "192k"] if has_audio else ["-an"]

    return [
        ffmpeg, "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        *audio_args,
        "-c:v", encoder, *enc_args,
        "-movflags", "+faststart",
        "-progress", "pipe:1",
        str(output_path),
    ]
