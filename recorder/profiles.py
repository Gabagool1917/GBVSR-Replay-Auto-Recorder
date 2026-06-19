"""Resolution profiles.

The original tool shipped as two separate downloads (one for 1080p
monitors, one for 2K/1440p monitors) because the on-screen template images
used for detection (``replay_theatre.png`` / ``replay_menu.png``) have to be
captured at the same pixel scale as whatever's actually on screen. This
module replaces "two separate downloads" with "one app, two bundled profiles
you can switch between" \u2014 auto-detected on launch, overridable from a
dropdown.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .paths import resource_path

# The original hardcoded black-fade check sampled the pixel at (500, 500).
# That was tuned against a 1920x1080 screen. Both the 1080p and 2K builds
# shipped with the exact same compiled script (verified by diffing them),
# so on a 2K screen that absolute coordinate just happened to still land on
# a part of the screen that goes black during the fade \u2014 it wasn't actually
# scaled for the resolution. We keep identical behaviour at 1920x1080 and
# scale it proportionally for every other resolution so it's correct by
# design rather than by coincidence.
_REFERENCE_W, _REFERENCE_H = 1920, 1080
_REFERENCE_SAMPLE_X, _REFERENCE_SAMPLE_Y = 500, 500


@dataclass(frozen=True)
class ResolutionProfile:
    key: str
    label: str
    width: int
    height: int
    theatre_template: Path
    menu_template: Path

    def fade_sample_point(self) -> tuple[int, int]:
        """Screen coordinate to sample for the black-fade loading check,
        scaled proportionally from the original (1920x1080)-tuned point."""
        x = round(_REFERENCE_SAMPLE_X / _REFERENCE_W * self.width)
        y = round(_REFERENCE_SAMPLE_Y / _REFERENCE_H * self.height)
        return x, y

    def assets_present(self) -> bool:
        return self.theatre_template.is_file() and self.menu_template.is_file()


def _profile(key: str, label: str, width: int, height: int) -> ResolutionProfile:
    folder = resource_path("assets", "profiles", key)
    return ResolutionProfile(
        key=key,
        label=label,
        width=width,
        height=height,
        theatre_template=folder / "replay_theatre.png",
        menu_template=folder / "replay_menu.png",
    )


# Ordered so dropdowns / "closest match" iteration is deterministic.
PROFILES: dict[str, ResolutionProfile] = {
    "1080p": _profile("1080p", "1080p (1920\u00d71080)", 1920, 1080),
    "1440p": _profile("1440p", "1440p / 2K (2560\u00d71440)", 2560, 1440),
}

DEFAULT_PROFILE_KEY = "1080p"


def detect_screen_resolution() -> Optional[tuple[int, int]]:
    """Best-effort screen resolution detection.

    Tries pyautogui first since that's the same library used for the actual
    screen capture/matching, so its idea of resolution is the one that
    matters for whether detection will actually work. Falls back to Qt's
    screen geometry if pyautogui isn't available for some reason.
    """
    try:
        import pyautogui

        size = pyautogui.size()
        return int(size.width), int(size.height)
    except Exception:
        pass

    try:
        from PySide6.QtGui import QGuiApplication

        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            geo = screen.geometry()
            return geo.width(), geo.height()
    except Exception:
        pass

    return None


def best_matching_profile(
    width: Optional[int], height: Optional[int]
) -> tuple[ResolutionProfile, bool]:
    """Returns (profile, exact_match).

    Falls back to the closest profile by total pixel count if there's no
    exact match, so an unrecognised resolution (e.g. 4K, ultrawide) still
    gets a sane default instead of the app failing to start.
    """
    if width and height:
        for profile in PROFILES.values():
            if profile.width == width and profile.height == height:
                return profile, True

        target_area = width * height
        closest = min(
            PROFILES.values(), key=lambda p: abs(p.width * p.height - target_area)
        )
        return closest, False

    return PROFILES[DEFAULT_PROFILE_KEY], False
