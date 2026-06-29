"""The main application window."""
from __future__ import annotations

import re

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .automation_worker import PLATFORM_SUPPORTED, AutomationWorker
from .game_results_dialog import GameResultsDialog, SetInfo
from .paths import icon_path, temp_dir
from .profiles import PROFILES, best_matching_profile, detect_screen_resolution
from .render_worker import RenderWorker
from . import theme
from .widgets import CollapsibleSection, LogPanel, StatusBadge, make_card

DEFAULT_GAMES = 7


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GBVSR Auto Recorder")
        self.resize(460, 760)

        self.automation_worker: AutomationWorker | None = None
        self.render_worker: RenderWorker | None = None
        self._current_state_key = "idle"
        self._gui_pause_flag = False

        self._build_ui()
        self._populate_resolution_profiles()
        self._refresh_recordings_path()

        # App icon (title bar + taskbar)
        icon_file = icon_path()
        if icon_file.exists():
            self.setWindowIcon(QIcon(str(icon_file)))

        if not PLATFORM_SUPPORTED:
            self._log(
                "error",
                "Running on a non-Windows platform \u2014 automation needs Windows "
                "(it simulates key presses with pydirectinput), so Start is disabled "
                "here. Combining existing recordings still works on any platform.",
            )
            self.start_button.setEnabled(False)

    # ------------------------------------------------------------ UI build
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        title = QLabel("GBVSR Auto Recorder")
        title.setProperty("role", "heading")
        subtitle = QLabel("Hands-off replay capture for Granblue Fantasy Versus Rising")
        subtitle.setProperty("role", "subtitle")
        subtitle.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(subtitle)

        root.addWidget(self._build_setup_card())
        root.addWidget(self._build_preflight_card())

        controls_row = QHBoxLayout()
        self.start_button = QPushButton("Start")
        self.start_button.setProperty("role", "primary")
        self.pause_button = QPushButton("Pause")
        self.stop_button = QPushButton("Stop")
        self.stop_button.setProperty("role", "danger")
        self.pause_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.start_button.clicked.connect(self._on_start_clicked)
        self.pause_button.clicked.connect(self._on_pause_clicked)
        self.stop_button.clicked.connect(self._on_stop_clicked)
        controls_row.addWidget(self.start_button)
        controls_row.addWidget(self.pause_button)
        controls_row.addWidget(self.stop_button)
        root.addLayout(controls_row)

        hotkey_caption = QLabel(
            "Hold S to pause \u2022 Press E to stop \u2014 these work even while "
            "the game window has focus."
        )
        hotkey_caption.setProperty("role", "caption")
        hotkey_caption.setWordWrap(True)
        root.addWidget(hotkey_caption)

        root.addWidget(self._build_status_card())

        self.combine_button = QPushButton("Combine recordings into one video")
        self.combine_button.clicked.connect(self._on_combine_clicked)
        root.addWidget(self.combine_button)

        root.addWidget(self._build_log_section())
        root.addStretch(1)

    def _build_preflight_card(self) -> QFrame:
        frame, layout = make_card()
        layout.setSpacing(6)

        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        dot = QLabel("⚠")
        dot.setStyleSheet(f"color: {theme.STATUS_COLORS['loading']}; font-size: 15px;")
        heading = QLabel("Before you start")
        heading.setStyleSheet("font-weight: 600; font-size: 13px;")
        header_row.addWidget(dot)
        header_row.addWidget(heading)
        header_row.addStretch(1)
        layout.addLayout(header_row)

        items = [
            ("OBS keybinds", "Start Recording = , (comma) · Stop Recording = . (period)"),
            ("Controllers", "Unplug all controllers and peripherals — the game must receive keyboard input"),
            ("Replay selection", "In Replays, hover over the LAST game in your set before pressing Start"),
        ]
        for title, detail in items:
            row = QHBoxLayout()
            row.setSpacing(8)
            row.setContentsMargins(4, 0, 0, 0)

            bullet = QLabel("›")
            bullet.setStyleSheet(f"color: {theme.ACCENT}; font-size: 14px; font-weight: 700;")
            bullet.setFixedWidth(12)

            text = QLabel(f"<b>{title}:</b> {detail}")
            text.setStyleSheet(f"color: {theme.TEXT_SECONDARY}; font-size: 12px;")
            text.setWordWrap(True)

            row.addWidget(bullet, 0)
            row.addWidget(text, 1)
            layout.addLayout(row)

        return frame

    def _build_setup_card(self) -> QFrame:
        frame, layout = make_card("Setup")

        profile_row = QHBoxLayout()
        profile_row.addWidget(QLabel("Resolution profile"))
        self.profile_combo = QComboBox()
        profile_row.addWidget(self.profile_combo, 1)
        layout.addLayout(profile_row)

        self.profile_caption = QLabel("")
        self.profile_caption.setProperty("role", "caption")
        self.profile_caption.setWordWrap(True)
        layout.addWidget(self.profile_caption)

        games_row = QHBoxLayout()
        games_row.addWidget(QLabel("Games to record"))
        games_row.addStretch(1)
        self.games_spin = QSpinBox()
        self.games_spin.setRange(1, 50)
        self.games_spin.setValue(DEFAULT_GAMES)
        self.games_spin.valueChanged.connect(self._on_games_value_changed)
        games_row.addWidget(self.games_spin)
        layout.addLayout(games_row)

        path_row = QHBoxLayout()
        self.path_field = QLineEdit()
        self.path_field.setReadOnly(True)
        copy_path_btn = QPushButton("Copy")
        open_path_btn = QPushButton("Open")
        copy_path_btn.clicked.connect(self._copy_recordings_path)
        open_path_btn.clicked.connect(self._open_recordings_folder)
        path_row.addWidget(self.path_field, 1)
        path_row.addWidget(copy_path_btn)
        path_row.addWidget(open_path_btn)
        layout.addLayout(path_row)

        path_caption = QLabel(
            "Point OBS's recording output to this folder \u2014 that's how the "
            "app finds your clips to combine afterward."
        )
        path_caption.setProperty("role", "caption")
        path_caption.setWordWrap(True)
        layout.addWidget(path_caption)

        self.auto_combine_check = QCheckBox(
            "Combine recordings into one video when finished"
        )
        self.auto_combine_check.setChecked(True)
        layout.addWidget(self.auto_combine_check)

        return frame

    def _build_status_card(self) -> QFrame:
        frame, layout = make_card("Status")

        self.status_badge = StatusBadge()
        layout.addWidget(self.status_badge)

        self.countdown_label = QLabel("")
        self.countdown_label.setProperty("role", "caption")
        self.countdown_label.setVisible(False)
        layout.addWidget(self.countdown_label)

        self.games_progress = QProgressBar()
        self.games_progress.setFormat("Game %v of %m")
        self.games_progress.setMinimum(0)
        self.games_progress.setMaximum(DEFAULT_GAMES)
        layout.addWidget(self.games_progress)

        self.recording_time_label = QLabel("")
        self.recording_time_label.setProperty("role", "caption")
        self.recording_time_label.setVisible(False)
        layout.addWidget(self.recording_time_label)

        self.render_progress = QProgressBar()
        self.render_progress.setFormat("Combining\u2026 %p%")
        self.render_progress.setRange(0, 100)
        self.render_progress.setVisible(False)
        layout.addWidget(self.render_progress)

        return frame

    def _build_log_section(self) -> CollapsibleSection:
        self.log_section = CollapsibleSection("Detailed log")
        section = self.log_section
        self.log_panel = LogPanel()
        self.log_panel.setMinimumHeight(160)
        section.set_content_widget(self.log_panel)

        copy_log_row = QHBoxLayout()
        copy_log_row.setContentsMargins(0, 6, 0, 0)
        copy_log_btn = QPushButton("Copy log")
        copy_log_btn.clicked.connect(self._copy_log)
        copy_log_row.addStretch(1)
        copy_log_row.addWidget(copy_log_btn)

        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.addWidget(section)
        wrapper_layout.addLayout(copy_log_row)
        # Returning a QWidget instead of the section directly so the
        # "Copy log" row rides along underneath it as one unit.
        self._log_section_wrapper = wrapper
        return wrapper  # type: ignore[return-value]

    # --------------------------------------------------------- automation
    def _on_start_clicked(self) -> None:
        if not PLATFORM_SUPPORTED:
            return

        profile = self.profile_combo.currentData()
        if profile is None or not profile.assets_present():
            QMessageBox.warning(
                self,
                "Missing resolution assets",
                "Couldn't find the template images for this resolution profile. "
                "Try reinstalling the app.",
            )
            return

        self.automation_worker = AutomationWorker(profile, self.games_spin.value())
        self.automation_worker.status_update.connect(self._on_status_update)
        self.automation_worker.progress_update.connect(self._on_progress_update)
        self.automation_worker.log_message.connect(self._log)
        self.automation_worker.countdown_update.connect(self._on_countdown_update)
        self.automation_worker.recording_tick.connect(self._on_recording_tick)
        self.automation_worker.paused_changed.connect(self._on_paused_changed)
        self.automation_worker.finished_run.connect(self._on_automation_finished)

        self._gui_pause_flag = False
        self.pause_button.setText("Pause")
        self._set_running_ui_state(True)
        self.automation_worker.start()

    def _on_pause_clicked(self) -> None:
        if self.automation_worker is None:
            return
        self._gui_pause_flag = not self._gui_pause_flag
        self.automation_worker.set_paused(self._gui_pause_flag)

    def _on_stop_clicked(self) -> None:
        if self.automation_worker is None:
            return
        if self._current_state_key == "recording":
            reply = QMessageBox.question(
                self,
                "Stop while recording?",
                "A recording is currently in progress. Stopping now will end the "
                "automation, but OBS will keep recording until you stop it there "
                "yourself \u2014 the original tool worked the same way, this app "
                "doesn't reach into OBS directly.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self.automation_worker.request_stop()
        self.stop_button.setEnabled(False)

    def _set_running_ui_state(self, running: bool) -> None:
        self.start_button.setEnabled(not running)
        self.pause_button.setEnabled(running)
        self.stop_button.setEnabled(running)
        self.profile_combo.setEnabled(not running)
        self.games_spin.setEnabled(not running)
        self.combine_button.setEnabled(not running)

    def _on_games_value_changed(self, value: int) -> None:
        if self.automation_worker is None:
            self.games_progress.setMaximum(value)
            self.games_progress.setValue(0)

    # ------------------------------------------------ automation signals
    def _on_status_update(self, state_key: str, headline: str, detail: str) -> None:
        self._current_state_key = state_key
        self.status_badge.set_status(state_key, headline, detail)
        if state_key != "countdown":
            self.countdown_label.setVisible(False)
        if state_key != "recording":
            self.recording_time_label.setVisible(False)

    def _on_progress_update(self, current: int, total: int) -> None:
        self.games_progress.setMaximum(total)
        self.games_progress.setValue(current)

    def _on_countdown_update(self, seconds_left: int) -> None:
        if seconds_left <= 0:
            self.countdown_label.setVisible(False)
            return
        self.countdown_label.setVisible(True)
        self.countdown_label.setText(f"Starting in {seconds_left}s\u2026")

    def _on_recording_tick(self, elapsed_seconds: int) -> None:
        minutes, seconds = divmod(elapsed_seconds, 60)
        self.recording_time_label.setVisible(True)
        self.recording_time_label.setText(f"Recording time: {minutes}:{seconds:02d}")

    def _on_paused_changed(self, paused: bool) -> None:
        self.pause_button.setText("Resume" if paused else "Pause")

    def _on_automation_finished(self, success: bool) -> None:
        self._set_running_ui_state(False)
        self.pause_button.setText("Pause")
        self.countdown_label.setVisible(False)
        self.recording_time_label.setVisible(False)
        self.automation_worker = None
        if success and self.auto_combine_check.isChecked():
            self._on_combine_clicked()

    # -------------------------------------------------------------- render
    def _on_combine_clicked(self) -> None:
        from .render_worker import VIDEO_EXTENSIONS
        clips = sorted(
            [p for p in temp_dir().iterdir()
             if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS]
        ) if temp_dir().is_dir() else []

        if not clips:
            QMessageBox.warning(
                self,
                "No recordings found",
                f"No video files found in:\n{temp_dir()}\n\n"
                "Make sure OBS's recording output path points to that folder.",
            )
            return

        # Rename raw OBS files to Game 1, Game 2, etc. before showing dialog
        try:
            clips = self._rename_to_game_numbers(clips)
            self._log("info", f"Recordings renamed: {', '.join(c.name for c in clips)}")
        except Exception as exc:  # noqa: BLE001
            self._log("warn", f"Could not rename recordings: {exc} — using original names.")

        dialog = GameResultsDialog(clips, parent=self)
        if dialog.exec() != GameResultsDialog.DialogCode.Accepted:
            return

        self._start_render(dialog.set_info())

    @staticmethod
    def _rename_to_game_numbers(clips: list) -> list:
        """Rename sorted clip files to 'Game 1.ext', 'Game 2.ext', etc.

        Uses a two-pass rename (temp names first) to safely handle any
        collisions when some files are already named 'Game N'.
        Returns the list of new Path objects.
        """
        from pathlib import Path

        already_pattern = re.compile(r'^Game \d+\.\w+$', re.IGNORECASE)
        if all(already_pattern.match(c.name) for c in clips):
            return clips  # already correctly named, nothing to do

        # Pass 1: rename to temp names to avoid collisions mid-rename
        temp_clips = []
        for i, clip in enumerate(clips):
            temp = clip.parent / f"_gbvsr_renaming_{i}{clip.suffix}"
            clip.rename(temp)
            temp_clips.append(temp)

        # Pass 2: rename from temp to final Game N names
        final_clips = []
        for i, clip in enumerate(temp_clips, start=1):
            final = clip.parent / f"Game {i}{clip.suffix}"
            clip.rename(final)
            final_clips.append(final)

        return final_clips

    def _start_render(self, set_info: SetInfo | None = None) -> None:
        if self.render_worker is not None and self.render_worker.isRunning():
            return
        self.render_worker = RenderWorker(set_info=set_info)
        self.render_worker.progress.connect(self._on_render_progress)
        self.render_worker.log_message.connect(self._log)
        self.render_worker.finished_render.connect(self._on_render_finished)
        # Clean up the QThread object via Qt's own scheduler once run() returns.
        # Dropping a Python reference to a live QThread can crash on Windows;
        # deleteLater() queues the deletion safely after the thread fully exits.
        self.render_worker.finished.connect(self.render_worker.deleteLater)
        self.render_worker.finished.connect(self._on_render_worker_finished)

        self.start_button.setEnabled(False)
        self.combine_button.setEnabled(False)
        self.render_progress.setVisible(True)
        self.render_progress.setValue(0)

        # Auto-open the log so encoding progress is visible without extra clicks
        if not self.log_section._expanded:
            self.log_section.toggle()

        self.render_worker.start()

    def _on_render_worker_finished(self) -> None:
        """Called when the QThread itself has exited — safe point to clear the ref."""
        self.render_worker = None

    def _on_render_progress(self, fraction: float) -> None:
        self.render_progress.setValue(int(fraction * 100))
        # Keep the window title updated so progress is visible even when minimised
        pct = int(fraction * 100)
        self.setWindowTitle(f"GBVSR Auto Recorder — Encoding {pct}%")

    def _on_render_finished(self, success: bool, path_or_error: str) -> None:
        self.setWindowTitle("GBVSR Auto Recorder")
        self.render_progress.setVisible(False)
        self.start_button.setEnabled(PLATFORM_SUPPORTED)
        self.combine_button.setEnabled(True)
        if success:
            self.status_badge.set_status("success", "Combined video ready", path_or_error)
            self._log("info", "✓ Encoding complete.")
            # Flash the taskbar button so the user knows it's done even if
            # they've switched windows. Flashes until they click back in.
            QApplication.alert(self, 0)
        else:
            self.status_badge.set_status("error", "Combine failed", path_or_error)
            self._log("error", "✗ Encoding failed.")
        # Note: self.render_worker = None is handled by _on_render_worker_finished
        # (connected to QThread.finished) to avoid dropping the ref prematurely.

    # --------------------------------------------------------------- misc
    def _populate_resolution_profiles(self) -> None:
        for profile in PROFILES.values():
            self.profile_combo.addItem(profile.label, profile)

        detected = detect_screen_resolution()
        if detected:
            width, height = detected
            profile, exact = best_matching_profile(width, height)
            index = self.profile_combo.findData(profile)
            if index >= 0:
                self.profile_combo.setCurrentIndex(index)
            if exact:
                self.profile_caption.setText(
                    f"Detected {width}\u00d7{height} \u2014 matched automatically."
                )
            else:
                self.profile_caption.setText(
                    f"Detected {width}\u00d7{height} \u2014 no exact profile for that, "
                    "using the closest match. Pick a different one above if needed."
                )
        else:
            self.profile_caption.setText(
                "Couldn't auto-detect your screen resolution \u2014 pick the closest "
                "match above."
            )

    def _refresh_recordings_path(self) -> None:
        self.path_field.setText(str(temp_dir()))

    def _copy_recordings_path(self) -> None:
        QApplication.clipboard().setText(str(temp_dir()))
        self._log("info", "Recordings folder path copied to clipboard.")

    def _open_recordings_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(temp_dir())))

    def _copy_log(self) -> None:
        QApplication.clipboard().setText(self.log_panel.toPlainText())

    def _log(self, level: str, text: str) -> None:
        self.log_panel.append_entry(level, text)

    # -------------------------------------------------------------- close
    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self.automation_worker is not None and self.automation_worker.isRunning():
            self.automation_worker.request_stop()
            self.automation_worker.wait(2000)

        if self.render_worker is not None and self.render_worker.isRunning():
            reply = QMessageBox.question(
                self,
                "Combine still running",
                "Recordings are still being combined. Quit anyway? The partial "
                "output file may not be usable.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.render_worker.terminate()
            self.render_worker.wait(2000)

        event.accept()
