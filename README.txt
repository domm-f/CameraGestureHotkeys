CameraGestureHotkeys
====================

CameraGestureHotkeys watches a webcam for saved upper-body poses and presses the
keyboard shortcut assigned to each pose. Camera frames are processed locally and
are not uploaded or saved.

SETUP
-----
1. Install 64-bit Python 3.11 from python.org.
2. During installation, enable "Add Python to PATH".
3. Double-click SETUP.bat.
4. After setup completes, double-click RUN_APP.bat.

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
