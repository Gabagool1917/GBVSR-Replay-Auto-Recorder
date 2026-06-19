# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec for GBVSR Auto Recorder.

Build on Windows (PyInstaller doesn't cross-compile, so this has to run
on the platform you're targeting) with:

    pip install -r requirements.txt
    pip install pyinstaller
    pyinstaller build.spec

(or just double-click build.bat, which does all three for you)

The result is a single self-contained GBVSR_Auto_Recorder.exe at
dist/GBVSR_Auto_Recorder.exe — a --onefile build, chosen for internal
distribution where handing someone one file is simpler than "unzip this
folder and keep the .exe next to its _internal folder." The tradeoff:
this app's dependency footprint (PySide6 + OpenCV + MoviePy) is big
enough that every launch pays a real self-extraction cost first — expect
several seconds before the window appears, more on a slow disk or the
very first run after antivirus scans the extracted files. If that delay
ends up being annoying for how this gets used day to day, switching back
to --onedir (instant launches, multi-file folder instead) is a small
change — see the git history or ask whoever built this for the onedir
version of this spec.

Note on ffmpeg/OpenCV binaries: moviepy needs an actual ffmpeg
executable, and OpenCV needs its native bindings, but neither is a
literal `import` PyInstaller's static analysis would catch. Both are
shipped as data files (ffmpeg) or compiled extension modules (OpenCV) by
their respective packages, located only at runtime. We don't bundle
those by hand here — `pyinstaller-hooks-contrib` (installed
automatically alongside `pyinstaller`) ships maintained hooks for
imageio_ffmpeg and cv2 that handle this for us. If you ever see a
"no ffmpeg exe could be found" or OpenCV DLL error from the built .exe,
that's the first thing to check (`pip show pyinstaller-hooks-contrib`).
"""
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = []
hiddenimports += collect_submodules("moviepy")
hiddenimports += collect_submodules("proglog")
hiddenimports += ["pyautogui", "pydirectinput", "keyboard", "cv2"]

datas = [
    ("assets/profiles", "assets/profiles"),
]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="GBVSR_Auto_Recorder",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon="assets/icon.ico",  # add an .ico here if you want a custom taskbar icon
)
