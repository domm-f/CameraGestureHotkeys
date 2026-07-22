CameraGestureHotkeys
====================

CameraGestureHotkeys watches a webcam for saved upper-body poses and presses the
keyboard shortcut assigned to each pose. Camera frames are processed locally and
are not uploaded or saved.

Author: domm-f

RUNNING FROM SOURCE
-------------------
1. Install 64-bit Python 3.11 from python.org.
2. During installation, enable "Add Python to PATH".
3. Open Command Prompt in this folder.
4. Run:

   py -3.11 -m pip install -r requirements.txt

5. Start the app with:

   py -3.11 app.py

The pose model is already included in this repository.

BUILDING THE INSTALLER
----------------------
Double-click BUILD_SETUP.bat.

The builder installs missing build tools when possible, packages Python and all
required libraries, and creates:

  release\Camera_Gesture_Hotkeys_Setup.exe

That setup file is the only file normal users need. It installs Camera Gesture
Hotkeys as a Windows app, lists domm-f as the publisher, creates Start menu and
optional desktop shortcuts, and includes a normal Windows uninstaller.

Do not commit generated .build-venv, build, dist, or release folders.

CREATING A GESTURE
------------------
1. Enter a gesture name.
2. Enter a hotkey, such as ctrl_l+shift_l+alt_l+s.
3. Click Capture new pose.
4. Hold the pose while samples are collected.
5. Leave the pose before trying it again.

SETTINGS
--------
Match strictness controls how closely your pose must match the saved pose.
Raise it if a gesture activates accidentally. Lower it if detection is unreliable.

Cooldown controls the minimum time between activations.

Hold frames controls how many camera frames must match before activation.
A larger value reduces accidental activations but responds more slowly.

Camera index is usually 0. Try 1 or 2 if the wrong camera opens, then click
Restart camera.

HOTKEY FORMAT
-------------
Separate keys with +. Examples:
  ctrl_l+shift_l+alt_l+s
  ctrl+c
  alt+f4
  shift+space
  f8
  win+d

Supported names include ctrl, ctrl_l, ctrl_r, shift, shift_l, shift_r, alt,
alt_l, alt_r, win, enter, space, tab, esc, backspace, delete, arrow keys,
f1 through f20, plain letters, and digits.

SAVED DATA
----------
Gesture profiles are stored at:

  %APPDATA%\CameraGestureHotkeys\gestures.json

Uninstalling the packaged app removes its installed files and saved gesture
profiles.

LICENSE
-------
MIT License

Copyright (c) 2026 domm-f

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
