@echo off
setlocal

echo ============================================
echo  GBVSR Auto Recorder - build script
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo ERROR: Python wasn't found on PATH.
    echo Install Python 3.10+ from https://python.org - during install,
    echo make sure "Add python.exe to PATH" is checked - then re-run this.
    pause
    exit /b 1
)

echo [1/3] Installing dependencies...
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies. See the output above.
    pause
    exit /b 1
)

echo.
echo [2/3] Installing PyInstaller...
python -m pip install pyinstaller
if errorlevel 1 (
    echo ERROR: Failed to install PyInstaller.
    pause
    exit /b 1
)

echo.
echo [3/3] Building the .exe - this can take a few minutes...
python -m PyInstaller --noconfirm build.spec
if errorlevel 1 (
    echo ERROR: Build failed. See the output above.
    pause
    exit /b 1
)

echo.
echo ============================================
echo  Done. The app is at:
echo  dist\GBVSR_Auto_Recorder.exe
echo.
echo  That's it - just the one file. Share it however
echo  you'd share any file (first launch is slower than
echo  later ones, it self-extracts each time it starts).
echo ============================================
pause
