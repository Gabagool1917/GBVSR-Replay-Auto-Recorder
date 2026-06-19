# GBVSR Auto Recorder

A GUI tool that automatically captures Granblue Fantasy Versus Rising replay
footage: it watches the screen for the right menus, sends the keypresses to
navigate and start/stop recording, and (optionally) stitches all the
recordings into one combined video with crossfade transitions afterward.

This is a GUI rewrite of an original command-line script. The underlying
automation logic — what gets pressed, when, and why — is unchanged; what's
new is live status, progress, and a detailed log in place of a scrolling
console window. See [What changed](#what-changed-from-the-original-cli-tool)
for a full, honest list of the differences.

## Requirements

- **Windows**, for the automation itself — it simulates keyboard input with
  a Windows-only library. Combining already-recorded footage into one video
  works on any OS, but the automated capture does not.
- **OBS Studio**, with hotkeys configured (below).
- **Python 3.10+**, only if running from source. Not needed if you're using
  a packaged .exe someone built for you.

## Setup

### 1. Install dependencies (source only)

```
pip install -r requirements.txt
```

### 2. Configure OBS

- Settings → Hotkeys: set **Start Recording** to the comma key (`,`) and
  **Stop Recording** to the period key (`.`). Unchanged from the original
  tool.
- Settings → Output: set your **Recording Path** to this app's `temp`
  folder. The app shows you the exact path, with Copy and Open buttons, in
  the Setup section — point OBS there. This is how the app finds your
  individual recordings afterward to combine them. It's easy to miss, and
  wasn't documented in the original tool's instructions at all.

### 3. Set up Granblue Fantasy Versus Rising

- Launch the game **without a controller connected** (per the original
  instructions).
- Navigate to the Replays screen.
- Hover over (highlight) the **last** replay in the list — the oldest one
  you want recorded. The automation starts there and works backward up the
  list.

## Using the app

1. Launch it (`python main.py` from source, or the packaged .exe).
2. In **Setup**: pick a resolution profile (auto-detected, but override the
   dropdown if it guessed wrong), set how many games to record, and confirm
   the recordings path matches what you set in OBS.
3. Click **Start**. You get a 5-second countdown — tab back into the game
   during that window.
4. The **Status** card tracks what's happening: searching for the menu,
   loading, recording, with a live game counter and recording timer.
5. Hold **S** to pause, press **E** to stop — both work even while the game
   window has focus, same as the original.
6. When every game is recorded, the app combines them into one video
   automatically if "Combine recordings into one video when finished" is
   checked — or click **Combine recordings into one video** any time to do
   it manually, independent of any automation run.
7. Combined videos land in the app's `output` folder, named with a
   timestamp.

## Building a standalone .exe

PyInstaller doesn't cross-compile, so this has to run on Windows itself.

Easiest path: double-click **`build.bat`**. It installs the dependencies,
installs PyInstaller, and runs the build, pausing on any error so you can
read what went wrong.

Or run the same three steps yourself:

```
pip install -r requirements.txt
pip install pyinstaller
pyinstaller build.spec
```

Either way, this produces a single file at `dist/GBVSR_Auto_Recorder.exe` —
no folder to keep together, just that one file to share. First launch
self-extracts to a temp folder before the window appears; expect it to take
several seconds (around 8-9s in testing here, could be faster or slower
depending on disk speed and antivirus scanning).

## What changed from the original CLI tool

- **One app instead of two downloads.** The original shipped separate
  1080p and 2K builds, because the on-screen template images have to match
  your actual resolution. This app bundles both and auto-detects (or lets
  you pick) which to use, with a closest-match fallback for resolutions
  like 4K that don't have a dedicated profile.
- **The "fade to black" detection point is now actually resolution-aware.**
  The original always sampled one hardcoded screen coordinate, (500, 500),
  tuned for 1920×1080. It happened to still land somewhere that goes black
  on a 2K screen too — by luck, not by design, since both builds shipped
  the exact same compiled script. This version scales that point
  proportionally to whatever resolution profile is active.
- **The recordings folder is surfaced directly in the UI**, with Copy and
  Open buttons, since pointing OBS at the right output folder turned out to
  be a real (and previously undocumented) requirement.
- **The 1–50 games limit is actually enforced.** The original printed a
  warning for an out-of-range number but then continued anyway. The GUI's
  spin box just won't let you enter an invalid number.
- **Combining recordings is more reliable.** The original trusted whatever
  order `os.listdir()` happened to return, which usually but not always
  matches chronological order, and didn't filter out non-video files. This
  version explicitly sorts recordings by filename (how OBS timestamps them)
  and only picks up actual video files.
- **Combined output goes to a dedicated, timestamped file**
  (`output/output_<timestamp>.mp4`) instead of overwriting a single
  `output.mp4` in the working directory every time.
- **Pressing E (or clicking Stop) no longer kills the whole program.** The
  original's stop hotkey called Python's `quit()`, which crashed the
  interpreter outright — among other things, that meant it could never
  auto-combine recordings after a manual stop, since it never reached that
  code. This version stops the automation cleanly. To match that same
  original behavior, auto-combine is still skipped after a manual stop (you
  can always combine manually afterward); a confirmation dialog also warns
  you if you stop mid-recording, since OBS won't stop recording on its own.
- **Status, progress, and a detailed log replace the scrolling console.**

## Project layout

```
main.py                  entry point
recorder/
  automation_worker.py   the screen-watching automation loop (background thread)
  render_worker.py       combines recordings into one video (background thread)
  main_window.py         the GUI
  profiles.py            resolution profiles + auto-detection
  paths.py               where bundled assets / temp / output live
  theme.py                colors + stylesheet
  widgets.py              small reusable UI pieces
assets/profiles/          template images used for on-screen detection, per resolution
build.spec                 PyInstaller packaging config
requirements.txt
```

## A note on testing

Everything that could reasonably be tested without your exact setup, was:
the full render pipeline (trimming, crossfading, encoding, progress
reporting) against real synthetic video clips; the entire automation phase
logic — including the first-game-vs-later-game branching, pause, and stop —
against a mocked screen and keyboard; the PyInstaller packaging end-to-end,
including the ffmpeg and OpenCV binaries that don't get bundled
automatically without the right hooks; and the actual frozen .exe launching
successfully. What can't be tested from here is the literal screen-reading
and key-sending against a real, running copy of Granblue Fantasy Versus
Rising — that needs your machine, your OBS setup, and your monitor. Run it
against one game first before queuing up a long batch.
