"""The automation loop, refactored from the original ``auto_script.py``.

This is a faithful refactor, not a rewrite. The original's polling loop,
phase order, key bindings, and sleep timings are preserved exactly so the
on-screen behaviour (when to press what, how long to wait) is unchanged.
What's different is that each step now reports its status through Qt
signals instead of ``print()``, so the GUI can show live progress instead
of a scrolling console.

Original behaviour preserved:
    - Same 5 phases, same key bindings (j/j to open, ',' to start
      recording, 'u' to close the nav, '.' to stop recording, enter to
      close the replay), same sleep durations.
    - Same non-``elif`` phase checks: phases are checked in sequence with
      plain ``if`` statements (not ``elif``), so if phase 1's condition
      promotes straight to phase 2, phase 2's check still runs in that
      same tick using the new phase value. This is preserved exactly,
      including the implicit assumption that a phase transition only
      ever cascades forward, never skips backward.
    - Same first-game vs. later-game branch in phase 1 (``reps ==
      max_reps`` opens the replay directly; later reps press 's' to move
      down to the next entry first).
    - Hold 's' to pause, press 'e' to stop, checked every 0.1s tick,
      exactly like the original.

Behaviour changed (documented in the README too):
    - The 1-50 game count is no longer "validated" by printing a warning
      and continuing anyway (that was a no-op in the original — it never
      actually stopped you from entering 0 or 200). The GUI's spin box
      enforces the range, so this bug class doesn't exist anymore.
    - Pressing 'e' no longer hard-exits the whole process (the original
      called ``quit()``, killing the interpreter). It now stops the
      automation loop cleanly, the same way the GUI's Stop button does,
      and — like the original, which never reached ``render_video()``
      after a ``quit()`` — auto-render is skipped when stopped this way.
    - If phase 1 (searching for the replay menu) goes more than 20
      seconds without a match, a one-time warning is logged suggesting
      the resolution profile or game screen might be wrong. This doesn't
      change any behaviour, it just stops "silently stuck" from looking
      identical to "still working."
"""
from __future__ import annotations

import platform
import time
from enum import Enum, auto

from PySide6.QtCore import QThread, Signal

from .profiles import ResolutionProfile

PLATFORM_SUPPORTED = platform.system() == "Windows"

if PLATFORM_SUPPORTED:
    import keyboard
    import pyautogui
    import pydirectinput
else:  # pragma: no cover - exercised only when run on non-Windows
    keyboard = None
    pyautogui = None
    pydirectinput = None

INITIAL_GRACE_SECONDS = 5
BETWEEN_GAME_SECONDS = 5
SEARCH_WARNING_SECONDS = 20
PAUSE_HOTKEY = "s"
STOP_HOTKEY = "e"


class Phase(Enum):
    SEARCHING_MENU = auto()      # original phase 1
    LOADING = auto()             # original phase 2
    STARTING_RECORD = auto()     # original phase 3
    RECORDING = auto()           # original phase 4
    GAME_DONE = auto()           # original phase 5


class AutomationWorker(QThread):
    """Runs the screen-watching automation loop on a background thread.

    Qt can't touch widgets from a non-GUI thread, so every bit of status
    this worker wants to report goes out as a signal; ``main_window.py``
    is responsible for turning those into UI updates.
    """

    # state_key (for colour/icon lookup), headline, detail
    status_update = Signal(str, str, str)
    # current_game (1-indexed, i.e. how many are done-or-in-progress), total_games
    progress_update = Signal(int, int)
    # level: "info" | "warn" | "error"
    log_message = Signal(str, str)
    # seconds remaining in the initial grace period (0 when it ends)
    countdown_update = Signal(int)
    # elapsed seconds of the current game's recording
    recording_tick = Signal(int)
    # True when paused (by hotkey or GUI), False when resumed
    paused_changed = Signal(bool)
    # True if every requested game was recorded, False if stopped/errored
    finished_run = Signal(bool)

    def __init__(self, profile: ResolutionProfile, total_games: int, parent=None):
        super().__init__(parent)
        self.profile = profile
        self.total_games = total_games
        self._stop_requested = False
        self._gui_pause_requested = False

    # --- thread-safe controls, called from the GUI thread ---
    def request_stop(self) -> None:
        self._stop_requested = True

    def set_paused(self, paused: bool) -> None:
        self._gui_pause_requested = paused

    # --- QThread entry point ---
    def run(self) -> None:
        if not PLATFORM_SUPPORTED:
            self.log_message.emit(
                "error",
                "This automation needs Windows — it simulates key presses "
                "with pydirectinput, which only works there. The app can "
                "still combine recordings on other platforms.",
            )
            self.finished_run.emit(False)
            return

        try:
            self._run_grace_period()
            if not self._stop_requested:
                self._run_phase_loop()
        except Exception as exc:  # noqa: BLE001 - surface any failure to the GUI
            self.log_message.emit("error", f"Automation stopped unexpectedly: {exc}")
            self.finished_run.emit(False)
            return

        self.finished_run.emit(not self._stop_requested)

    # --- internal helpers ---
    def _run_grace_period(self) -> None:
        self.status_update.emit(
            "countdown",
            "Get ready",
            "Switch back to Granblue Fantasy Versus Rising",
        )
        self.log_message.emit(
            "info", f"Starting in {INITIAL_GRACE_SECONDS}s — tab back into the game now."
        )
        for remaining in range(INITIAL_GRACE_SECONDS, 0, -1):
            if self._stop_requested:
                return
            self.countdown_update.emit(remaining)
            time.sleep(1)
        self.countdown_update.emit(0)

    def _check_hotkeys(self) -> bool:
        """Returns True if a stop was triggered."""
        try:
            if keyboard.is_pressed(STOP_HOTKEY):
                self.log_message.emit("warn", f"Stop hotkey ('{STOP_HOTKEY}') pressed.")
                self._stop_requested = True
                return True
        except Exception as exc:  # noqa: BLE001
            self.log_message.emit("error", f"Couldn't read keyboard state: {exc}")
        return False

    def _is_paused(self) -> bool:
        hotkey_held = False
        try:
            hotkey_held = keyboard.is_pressed(PAUSE_HOTKEY)
        except Exception:  # noqa: BLE001
            pass
        return hotkey_held or self._gui_pause_requested

    def _run_phase_loop(self) -> None:
        reps = self.total_games
        max_reps = self.total_games
        phase = Phase.SEARCHING_MENU
        was_paused = False
        search_started_at: float | None = None
        search_warning_sent = False
        recording_started_at: float | None = None

        self.progress_update.emit(0, max_reps)

        while reps > 0:
            time.sleep(0.1)

            if self._check_hotkeys():
                return

            paused_now = self._is_paused()
            if paused_now != was_paused:
                was_paused = paused_now
                self.paused_changed.emit(paused_now)
                self.log_message.emit("info", "Paused." if paused_now else "Resumed.")
            if paused_now:
                continue

            game_number = max_reps - reps + 1

            # --- Phase 1: searching for the replay menu ---
            # (plain `if`, not `elif` below — matches the original so a
            # phase change can fall through into the next phase's check
            # within the same 0.1s tick, same as the source script.)
            if phase is Phase.SEARCHING_MENU:
                if search_started_at is None:
                    search_started_at = time.time()
                    search_warning_sent = False
                    self.status_update.emit(
                        "searching",
                        "Searching for replay menu",
                        f"Game {game_number} of {max_reps}",
                    )
                found = self._locate(self.profile.theatre_template)
                if found:
                    if reps == max_reps:
                        self._open_replay()
                    else:
                        self._move_down()
                        time.sleep(0.2)
                        self._open_replay()
                    self.log_message.emit("info", "Replay opened, waiting for it to load.")
                    search_started_at = None
                    phase = Phase.LOADING
                else:
                    if (
                        not search_warning_sent
                        and time.time() - search_started_at > SEARCH_WARNING_SECONDS
                    ):
                        search_warning_sent = True
                        self.log_message.emit(
                            "warn",
                            "Still haven't found the replay menu after "
                            f"{SEARCH_WARNING_SECONDS}s — double check the "
                            "resolution profile and that you're on the "
                            "Replays screen.",
                        )
                    time.sleep(0.5)

            # --- Phase 2: waiting for the loading fade-out ---
            if phase is Phase.LOADING:
                self.status_update.emit(
                    "loading", "Loading replay", f"Game {game_number} of {max_reps}"
                )
                if self._is_black_screen():
                    phase = Phase.STARTING_RECORD

            # --- Phase 3: waiting for the fade-in, then start recording ---
            if phase is Phase.STARTING_RECORD:
                if not self._is_black_screen():
                    self._begin_record()
                    self._close_replay_nav()
                    recording_started_at = time.time()
                    self.status_update.emit(
                        "recording", "Recording", f"Game {game_number} of {max_reps}"
                    )
                    self.log_message.emit("info", "Recording started.")
                    phase = Phase.RECORDING

            # --- Phase 4: recording, watching for the match-end menu ---
            if phase is Phase.RECORDING:
                if recording_started_at is not None:
                    self.recording_tick.emit(int(time.time() - recording_started_at))
                if self._locate(self.profile.menu_template):
                    self._end_record()
                    self._close_replay()
                    self.log_message.emit("info", "Recording stopped.")
                    recording_started_at = None
                    phase = Phase.GAME_DONE

            # --- Phase 5: this game's done, line up the next one ---
            if phase is Phase.GAME_DONE:
                reps -= 1
                self.progress_update.emit(max_reps - reps, max_reps)
                phase = Phase.SEARCHING_MENU
                if reps > 0:
                    self.status_update.emit(
                        "between",
                        "Moving to the next game",
                        f"Game {max_reps - reps + 1} of {max_reps} starts shortly",
                    )
                time.sleep(BETWEEN_GAME_SECONDS)

        self.status_update.emit(
            "success", "All games recorded", f"{max_reps} game(s) captured"
        )

    # --- screen interaction (all on the worker thread) ---
    def _locate(self, template_path) -> bool:
        try:
            location = pyautogui.locateOnScreen(str(template_path), confidence=0.95)
            return location is not None
        except pyautogui.ImageNotFoundException:
            return False
        except Exception as exc:  # noqa: BLE001
            self.log_message.emit("error", f"Screen search failed: {exc}")
            return False

    def _is_black_screen(self) -> bool:
        x, y = self.profile.fade_sample_point()
        try:
            return pyautogui.pixel(x, y) == (0, 0, 0)
        except Exception as exc:  # noqa: BLE001
            self.log_message.emit("error", f"Couldn't read screen pixel: {exc}")
            return False

    @staticmethod
    def _move_down() -> None:
        pydirectinput.press("s")

    @staticmethod
    def _open_replay() -> None:
        pydirectinput.press("j")
        time.sleep(0.5)
        pydirectinput.press("j")
        time.sleep(3)

    @staticmethod
    def _begin_record() -> None:
        pydirectinput.press(",")

    @staticmethod
    def _close_replay_nav() -> None:
        pydirectinput.press("u")

    @staticmethod
    def _end_record() -> None:
        pydirectinput.press(".")

    @staticmethod
    def _close_replay() -> None:
        time.sleep(4)
        pydirectinput.press("enter")
