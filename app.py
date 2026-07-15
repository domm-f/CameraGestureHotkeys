from __future__ import annotations

import ctypes
import json
import math
import os
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import cv2
import mediapipe as mp
import numpy as np
import tkinter as tk
from PIL import Image, ImageTk
from pynput.keyboard import Controller, Key, KeyCode
from tkinter import messagebox, ttk

APP_NAME = "Camera Gesture Hotkeys"
MODEL_FILENAME = "pose_landmarker_lite.task"


def resource_path(relative_path: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / relative_path


BASE_DIR = Path(__file__).resolve().parent
if os.name == "nt" and os.getenv("APPDATA"):
    DATA_DIR = Path(os.environ["APPDATA"]) / "CameraGestureHotkeys"
else:
    DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
GESTURES_FILE = DATA_DIR / "gestures.json"
MODEL_PATH = resource_path(MODEL_FILENAME)


POSE_POINT_IDS = [0, 7, 8, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22]

POSE_CONNECTIONS = [
    (7, 8),
    (11, 12),
    (11, 13), (13, 15),
    (12, 14), (14, 16),
    (15, 17), (15, 19), (15, 21), (17, 19),
    (16, 18), (16, 20), (16, 22), (18, 20),
    (11, 23), (12, 24), (23, 24),
]


def strictness_to_threshold(strictness: float) -> float:
    
    return 0.35 - (float(strictness) / 100.0) * 0.25


def pose_embedding(world_landmarks: list[Any]) -> np.ndarray | None:
    
    try:
        points = np.array([[p.x, p.y, p.z] for p in world_landmarks], dtype=np.float32)
        visibility = np.array([getattr(p, "visibility", 1.0) for p in world_landmarks], dtype=np.float32)
    except Exception:
        return None

    if len(points) < 33:
        return None

    
    
    if visibility[11] < 0.22 or visibility[12] < 0.22:
        return None

    left_shoulder = points[11]
    right_shoulder = points[12]
    shoulder_mid = (left_shoulder + right_shoulder) * 0.5

    x_axis = left_shoulder - right_shoulder
    shoulder_width = float(np.linalg.norm(x_axis))
    if shoulder_width < 1e-5:
        return None
    x_axis /= shoulder_width

    
    
    face_ids = [0, 7, 8]
    visible_face_ids = [i for i in face_ids if visibility[i] >= 0.18]
    if not visible_face_ids:
        return None
    weights = np.array([max(float(visibility[i]), 0.05) for i in visible_face_ids], dtype=np.float32)
    face_center = np.average(points[visible_face_ids], axis=0, weights=weights)
    down_hint = shoulder_mid - face_center

    
    down_hint = down_hint - x_axis * float(np.dot(down_hint, x_axis))
    down_norm = float(np.linalg.norm(down_hint))
    if down_norm < 1e-5:
        return None
    y_axis = down_hint / down_norm
    z_axis = np.cross(x_axis, y_axis)
    z_norm = float(np.linalg.norm(z_axis))
    if z_norm < 1e-5:
        return None
    z_axis /= z_norm
    y_axis = np.cross(z_axis, x_axis)
    y_axis /= max(float(np.linalg.norm(y_axis)), 1e-5)

    selected = points[POSE_POINT_IDS] - shoulder_mid
    local = np.stack(
        [selected @ x_axis, selected @ y_axis, selected @ z_axis], axis=1
    ) / max(shoulder_width, 0.10)

    
    
    vis = np.clip(visibility[POSE_POINT_IDS], 0.0, 1.0).reshape(-1, 1)
    local = local * (0.72 + 0.28 * vis)
    return local.astype(np.float32).reshape(-1)


def embedding_distance(a: np.ndarray, b: np.ndarray) -> float:
    if a.shape != b.shape:
        return float("inf")
    return float(np.sqrt(np.mean(np.square(a - b))))


def robust_average(samples: list[np.ndarray]) -> np.ndarray:
    arr = np.stack(samples, axis=0)
    median = np.median(arr, axis=0)
    distances = np.sqrt(np.mean(np.square(arr - median), axis=1))
    cutoff = np.percentile(distances, 80)
    kept = arr[distances <= cutoff]
    if len(kept) < 5:
        kept = arr
    return np.mean(kept, axis=0).astype(np.float32)


def normalize_hotkey_text(text: str) -> str:
    return "+".join(part.strip().lower().replace(" ", "_") for part in text.split("+") if part.strip())


def parse_hotkey(text: str) -> list[Any]:
    aliases: dict[str, Any] = {
        "ctrl": Key.ctrl_l, "control": Key.ctrl_l, "lctrl": Key.ctrl_l, "ctrl_l": Key.ctrl_l,
        "rctrl": Key.ctrl_r, "ctrl_r": Key.ctrl_r,
        "shift": Key.shift_l, "lshift": Key.shift_l, "shift_l": Key.shift_l,
        "rshift": Key.shift_r, "shift_r": Key.shift_r,
        "alt": Key.alt_l, "lalt": Key.alt_l, "alt_l": Key.alt_l,
        "ralt": Key.alt_r, "alt_r": Key.alt_r,
        "win": Key.cmd_l, "windows": Key.cmd_l, "cmd": Key.cmd_l, "meta": Key.cmd_l,
        "space": Key.space, "enter": Key.enter, "return": Key.enter,
        "tab": Key.tab, "esc": Key.esc, "escape": Key.esc,
        "backspace": Key.backspace, "delete": Key.delete, "insert": Key.insert,
        "home": Key.home, "end": Key.end, "page_up": Key.page_up, "pageup": Key.page_up,
        "page_down": Key.page_down, "pagedown": Key.page_down,
        "up": Key.up, "down": Key.down, "left": Key.left, "right": Key.right,
        "caps_lock": Key.caps_lock, "capslock": Key.caps_lock,
        "print_screen": Key.print_screen, "printscreen": Key.print_screen,
        "media_play_pause": Key.media_play_pause,
        "media_next": Key.media_next,
        "media_previous": Key.media_previous,
        "volume_up": Key.media_volume_up,
        "volume_down": Key.media_volume_down,
        "volume_mute": Key.media_volume_mute,
    }

    keys: list[Any] = []
    for token in normalize_hotkey_text(text).split("+"):
        if not token:
            continue
        if token in aliases:
            keys.append(aliases[token])
        elif token.startswith("f") and token[1:].isdigit() and 1 <= int(token[1:]) <= 20:
            keys.append(getattr(Key, token))
        elif len(token) == 1:
            keys.append(KeyCode.from_char(token))
        else:
            raise ValueError(f"Unknown key: {token}")
    if not keys:
        raise ValueError("Enter at least one key.")
    return keys


def _windows_letter_button_event(token: str, pressed: bool) -> None:
    
    vk = ord(token.upper())
    scan = int(ctypes.windll.user32.MapVirtualKeyW(vk, 0))
    KEYEVENTF_KEYUP = 0x0002
    ctypes.windll.user32.keybd_event(vk, scan, 0 if pressed else KEYEVENTF_KEYUP, 0)


def send_hotkey(text: str) -> None:
    
    
    normalized = normalize_hotkey_text(text)
    tokens = normalized.split("+")
    keys = parse_hotkey(normalized)
    keyboard = Controller()
    pressed: list[tuple[str, Any]] = []
    try:
        for token, key in zip(tokens, keys):
            if os.name == "nt" and len(token) == 1 and token.isascii() and token.isalnum():
                _windows_letter_button_event(token, True)
                pressed.append(("letter", token))
            else:
                keyboard.press(key)
                pressed.append(("keyboard", key))
            time.sleep(0.018)
        time.sleep(0.055)
    finally:
        for method, key in reversed(pressed):
            try:
                if method == "letter":
                    _windows_letter_button_event(str(key), False)
                else:
                    keyboard.release(key)
            except Exception:
                pass


def load_gestures() -> list[dict[str, Any]]:
    if not GESTURES_FILE.exists():
        return []
    try:
        data = json.loads(GESTURES_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return []
        cleaned = []
        for item in data:
            if not isinstance(item, dict) or "embedding" not in item:
                continue
            item.setdefault("id", str(uuid.uuid4()))
            item.setdefault("name", "Unnamed gesture")
            item.setdefault("hotkey", "ctrl_l+shift_l+alt_l+s")
            item.setdefault("strictness", 72)
            item.setdefault("cooldown", 1.0)
            item.setdefault("hold_frames", 5)
            item.setdefault("enabled", True)
            cleaned.append(item)
        return cleaned
    except Exception:
        return []


def save_gestures(gestures: list[dict[str, Any]]) -> None:
    temp = GESTURES_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(gestures, indent=2), encoding="utf-8")
    temp.replace(GESTURES_FILE)


class GestureHotkeyApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("1320x720")
        self.root.minsize(1120, 650)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.lock = threading.RLock()
        self.running = True
        self.latest_frame: np.ndarray | None = None
        self.status_text = "Starting camera..."
        self.match_text = ""
        self.gestures = load_gestures()
        self.runtime: dict[str, dict[str, Any]] = {}
        self.capture_plan: dict[str, Any] | None = None
        self.refresh_needed = True
        self.triggers_enabled = True
        self.camera_index_value = 0
        self.camera_restart = False
        self.model_error: str | None = None

        self._build_ui()
        self.worker = threading.Thread(target=self._camera_worker, daemon=True)
        self.worker.start()
        self.root.after(40, self._update_ui)

    def _build_ui(self) -> None:
        
        
        colors = {
            "window": "#15171a",
            "panel": "#1d2024",
            "field": "#25292e",
            "field_hover": "#30353b",
            "border": "#3b4148",
            "text": "#f1f3f5",
            "muted": "#aeb4bb",
            "accent": "#4f8cff",
            "accent_hover": "#6a9dff",
            "selected": "#315f9f",
            "disabled": "#6e747b",
        }

        self.root.configure(background=colors["window"])
        style = ttk.Style(self.root)
        try:
            
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(".",
                        background=colors["window"],
                        foreground=colors["text"],
                        fieldbackground=colors["field"],
                        bordercolor=colors["border"],
                        lightcolor=colors["border"],
                        darkcolor=colors["border"],
                        troughcolor=colors["field"],
                        selectbackground=colors["selected"],
                        selectforeground=colors["text"],
                        font=("Segoe UI", 10))
        style.configure("TFrame", background=colors["window"])
        style.configure("Window.TFrame", background=colors["window"])
        style.configure("Panel.TFrame", background=colors["panel"])
        style.configure("TLabelframe",
                        background=colors["panel"],
                        bordercolor=colors["border"],
                        relief="solid")
        style.configure("TLabelframe.Label",
                        background=colors["panel"],
                        foreground=colors["text"],
                        font=("Segoe UI Semibold", 10))
        style.configure("TLabel", background=colors["window"], foreground=colors["text"])
        style.configure("Panel.TLabel", background=colors["panel"], foreground=colors["text"])
        style.configure("Muted.TLabel", background=colors["panel"], foreground=colors["muted"])
        style.configure("TCheckbutton", background=colors["panel"], foreground=colors["text"])
        style.map("TCheckbutton",
                  background=[("active", colors["panel"])],
                  foreground=[("disabled", colors["disabled"])])
        style.configure("TEntry",
                        fieldbackground=colors["field"],
                        foreground=colors["text"],
                        insertcolor=colors["text"],
                        bordercolor=colors["border"],
                        padding=5)
        style.map("TEntry",
                  fieldbackground=[("focus", colors["field_hover"])],
                  bordercolor=[("focus", colors["accent"])],
                  foreground=[("disabled", colors["disabled"])])
        style.configure("TButton",
                        background=colors["field"],
                        foreground=colors["text"],
                        bordercolor=colors["border"],
                        focusthickness=1,
                        focuscolor=colors["accent"],
                        padding=(9, 6))
        style.map("TButton",
                  background=[("pressed", colors["selected"]),
                              ("active", colors["field_hover"])],
                  bordercolor=[("focus", colors["accent"]),
                               ("active", colors["accent_hover"])],
                  foreground=[("disabled", colors["disabled"])])
        style.configure("Horizontal.TScale",
                        background=colors["panel"],
                        troughcolor=colors["field"],
                        bordercolor=colors["border"],
                        lightcolor=colors["accent"],
                        darkcolor=colors["accent"])
        style.configure("Vertical.TScrollbar",
                        background=colors["field"],
                        troughcolor=colors["panel"],
                        bordercolor=colors["border"],
                        arrowcolor=colors["text"])
        style.map("Vertical.TScrollbar",
                  background=[("active", colors["field_hover"]),
                              ("pressed", colors["selected"])])

        outer = ttk.Frame(self.root, padding=10, style="Window.TFrame")
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=3)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(0, weight=1)

        video_frame = ttk.LabelFrame(outer, text="Live camera", padding=6)
        video_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        video_frame.rowconfigure(0, weight=1)
        video_frame.columnconfigure(0, weight=1)
        self.video_label = ttk.Label(video_frame, anchor="center")
        self.video_label.grid(row=0, column=0, sticky="nsew")

        bottom = ttk.Frame(video_frame, style="Panel.TFrame")
        bottom.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        bottom.columnconfigure(0, weight=1)
        self.status_label = ttk.Label(bottom, text="Starting...", anchor="w", style="Panel.TLabel")
        self.status_label.grid(row=0, column=0, sticky="ew")
        self.match_label = ttk.Label(bottom, text="", anchor="e", style="Panel.TLabel")
        self.match_label.grid(row=0, column=1, sticky="e")

        panel = ttk.Frame(outer, style="Window.TFrame")
        panel.grid(row=0, column=1, sticky="nsew")
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(1, weight=1)

        enable_frame = ttk.LabelFrame(panel, text="Detection", padding=8)
        enable_frame.grid(row=0, column=0, sticky="ew")
        self.enabled_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            enable_frame,
            text="Enable gesture hotkeys",
            variable=self.enabled_var,
            command=self._toggle_enabled,
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(enable_frame, text="Camera index:", style="Panel.TLabel").grid(row=1, column=0, sticky="w", pady=(8, 0))
        camera_line = ttk.Frame(enable_frame, style="Panel.TFrame")
        camera_line.grid(row=2, column=0, sticky="ew")
        camera_line.columnconfigure(0, weight=1)
        self.camera_var = tk.StringVar(value="0")
        ttk.Entry(camera_line, textvariable=self.camera_var, width=8).grid(row=0, column=0, sticky="ew")
        ttk.Button(camera_line, text="Restart camera", command=self._restart_camera).grid(row=0, column=1, padx=(6, 0))

        list_frame = ttk.LabelFrame(panel, text="Saved gestures", padding=8)
        list_frame.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)
        self.gesture_list = tk.Listbox(
            list_frame,
            height=8,
            exportselection=False,
            background=colors["field"],
            foreground=colors["text"],
            selectbackground=colors["selected"],
            selectforeground=colors["text"],
            highlightbackground=colors["border"],
            highlightcolor=colors["accent"],
            highlightthickness=1,
            borderwidth=0,
            relief="flat",
            font=("Segoe UI", 10),
        )
        self.gesture_list.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.gesture_list.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.gesture_list.configure(yscrollcommand=scroll.set)
        self.gesture_list.bind("<<ListboxSelect>>", self._load_selected)
        buttons = ttk.Frame(list_frame, style="Panel.TFrame")
        buttons.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(7, 0))
        buttons.columnconfigure(0, weight=1)
        buttons.columnconfigure(1, weight=1)
        ttk.Button(buttons, text="Save changes", command=self._save_selected).grid(row=0, column=0, sticky="ew", padx=(0, 3))
        ttk.Button(buttons, text="Delete", command=self._delete_selected).grid(row=0, column=1, sticky="ew", padx=(3, 0))

        editor = ttk.LabelFrame(panel, text="Add or edit gesture", padding=8)
        editor.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        editor.columnconfigure(0, weight=1)

        ttk.Label(editor, text="Gesture name", style="Panel.TLabel").grid(row=0, column=0, sticky="w")
        self.name_var = tk.StringVar(value="Salute")
        ttk.Entry(editor, textvariable=self.name_var).grid(row=1, column=0, sticky="ew")

        ttk.Label(editor, text="Hotkey (use + between keys)", style="Panel.TLabel").grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.hotkey_var = tk.StringVar(value="ctrl_l+shift_l+alt_l+s")
        ttk.Entry(editor, textvariable=self.hotkey_var).grid(row=3, column=0, sticky="ew")
        ttk.Label(editor, text="Example: ctrl_l+shift_l+alt_l+s", style="Muted.TLabel").grid(row=4, column=0, sticky="w")

        ttk.Label(editor, text="Match strictness", style="Panel.TLabel").grid(row=5, column=0, sticky="w", pady=(8, 0))
        self.strictness_var = tk.DoubleVar(value=72)
        ttk.Scale(editor, from_=45, to=95, variable=self.strictness_var, orient="horizontal").grid(row=6, column=0, sticky="ew")

        settings_line = ttk.Frame(editor, style="Panel.TFrame")
        settings_line.grid(row=7, column=0, sticky="ew", pady=(8, 0))
        settings_line.columnconfigure(0, weight=1)
        settings_line.columnconfigure(1, weight=1)
        ttk.Label(settings_line, text="Cooldown (seconds)", style="Panel.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(settings_line, text="Hold frames", style="Panel.TLabel").grid(row=0, column=1, sticky="w", padx=(8, 0))
        self.cooldown_var = tk.StringVar(value="1.0")
        self.hold_frames_var = tk.StringVar(value="5")
        ttk.Entry(settings_line, textvariable=self.cooldown_var, width=9).grid(row=1, column=0, sticky="ew")
        ttk.Entry(settings_line, textvariable=self.hold_frames_var, width=9).grid(row=1, column=1, sticky="ew", padx=(8, 0))

        action_line = ttk.Frame(editor, style="Panel.TFrame")
        action_line.grid(row=8, column=0, sticky="ew", pady=(10, 0))
        action_line.columnconfigure(0, weight=1)
        action_line.columnconfigure(1, weight=1)
        ttk.Button(action_line, text="Capture new pose", command=self._start_capture).grid(row=0, column=0, sticky="ew", padx=(0, 3))
        ttk.Button(action_line, text="Test hotkey", command=self._test_hotkey).grid(row=0, column=1, sticky="ew", padx=(3, 0))

        ttk.Label(
            editor,
            text="After triggering, move out of the pose before it can trigger again.",
            wraplength=290,
            style="Muted.TLabel",
        ).grid(row=9, column=0, sticky="w", pady=(8, 0))

    def _toggle_enabled(self) -> None:
        with self.lock:
            self.triggers_enabled = bool(self.enabled_var.get())
            self.status_text = "Gesture hotkeys enabled." if self.triggers_enabled else "Gesture hotkeys paused."

    def _restart_camera(self) -> None:
        try:
            value = int(self.camera_var.get().strip())
            if value < 0:
                raise ValueError
        except ValueError:
            messagebox.showerror(APP_NAME, "Camera index must be 0 or a larger whole number.")
            return
        with self.lock:
            self.camera_index_value = value
            self.camera_restart = True
            self.status_text = f"Restarting camera {value}..."

    def _selected_index(self) -> int | None:
        selection = self.gesture_list.curselection()
        if not selection:
            return None
        return int(selection[0])

    def _load_selected(self, _event: Any = None) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        with self.lock:
            if idx >= len(self.gestures):
                return
            g = dict(self.gestures[idx])
        self.name_var.set(str(g["name"]))
        self.hotkey_var.set(str(g["hotkey"]))
        self.strictness_var.set(float(g.get("strictness", 72)))
        self.cooldown_var.set(str(g.get("cooldown", 1.0)))
        self.hold_frames_var.set(str(g.get("hold_frames", 5)))

    def _validated_editor_values(self) -> dict[str, Any] | None:
        name = self.name_var.get().strip()
        hotkey = normalize_hotkey_text(self.hotkey_var.get())
        if not name:
            messagebox.showerror(APP_NAME, "Enter a gesture name.")
            return None
        try:
            parse_hotkey(hotkey)
            cooldown = float(self.cooldown_var.get())
            hold_frames = int(self.hold_frames_var.get())
            if not 0.0 <= cooldown <= 60.0:
                raise ValueError("Cooldown must be between 0 and 60 seconds.")
            if not 1 <= hold_frames <= 60:
                raise ValueError("Hold frames must be between 1 and 60.")
        except ValueError as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return None
        return {
            "name": name,
            "hotkey": hotkey,
            "strictness": int(round(float(self.strictness_var.get()))),
            "cooldown": cooldown,
            "hold_frames": hold_frames,
        }

    def _save_selected(self) -> None:
        idx = self._selected_index()
        if idx is None:
            messagebox.showinfo(APP_NAME, "Select a saved gesture first, or use Capture new pose.")
            return
        values = self._validated_editor_values()
        if values is None:
            return
        with self.lock:
            if idx >= len(self.gestures):
                return
            self.gestures[idx].update(values)
            save_gestures(self.gestures)
            self.refresh_needed = True
            self.status_text = f"Saved changes to {values['name']}."

    def _delete_selected(self) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        with self.lock:
            if idx >= len(self.gestures):
                return
            name = self.gestures[idx]["name"]
        if not messagebox.askyesno(APP_NAME, f"Delete the gesture '{name}'?"):
            return
        with self.lock:
            gesture = self.gestures.pop(idx)
            self.runtime.pop(str(gesture.get("id")), None)
            save_gestures(self.gestures)
            self.refresh_needed = True
            self.status_text = f"Deleted {name}."

    def _start_capture(self) -> None:
        values = self._validated_editor_values()
        if values is None:
            return
        if not MODEL_PATH.exists():
            messagebox.showerror(APP_NAME, "The pose model is missing. Run SETUP.bat first.")
            return
        now = time.monotonic()
        with self.lock:
            if self.capture_plan is not None:
                messagebox.showinfo(APP_NAME, "A pose capture is already running.")
                return
            self.capture_plan = {
                **values,
                "capture_start": now + 3.0,
                "capture_end": now + 4.4,
                "samples": [],
            }
            self.status_text = "Get ready: 3"

    def _test_hotkey(self) -> None:
        try:
            text = normalize_hotkey_text(self.hotkey_var.get())
            parse_hotkey(text)
        except ValueError as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return
        threading.Thread(target=self._safe_send_hotkey, args=(text, "Test"), daemon=True).start()

    def _safe_send_hotkey(self, hotkey: str, gesture_name: str) -> None:
        try:
            send_hotkey(hotkey)
            with self.lock:
                self.status_text = f"Triggered: {gesture_name} → {hotkey}"
        except Exception as exc:
            with self.lock:
                self.status_text = f"Could not press hotkey: {exc}"

    def _refresh_listbox(self) -> None:
        selected = self._selected_index()
        with self.lock:
            names = [f"{'✓' if g.get('enabled', True) else '–'}  {g['name']}  →  {g['hotkey']}" for g in self.gestures]
            self.refresh_needed = False
        self.gesture_list.delete(0, tk.END)
        for text in names:
            self.gesture_list.insert(tk.END, text)
        if selected is not None and selected < len(names):
            self.gesture_list.selection_set(selected)

    def _draw_pose(self, frame: np.ndarray, landmarks: list[Any]) -> None:
        height, width = frame.shape[:2]
        points: dict[int, tuple[int, int]] = {}
        for i, p in enumerate(landmarks):
            if getattr(p, "visibility", 1.0) < 0.35:
                continue
            points[i] = (int(p.x * width), int(p.y * height))
        for a, b in POSE_CONNECTIONS:
            if a in points and b in points:
                cv2.line(frame, points[a], points[b], (70, 220, 120), 3, cv2.LINE_AA)
        for i in POSE_POINT_IDS:
            if i in points:
                cv2.circle(frame, points[i], 4, (255, 255, 255), -1, cv2.LINE_AA)
                cv2.circle(frame, points[i], 5, (70, 220, 120), 1, cv2.LINE_AA)

    def _camera_worker(self) -> None:
        if not MODEL_PATH.exists():
            with self.lock:
                self.model_error = "Pose model missing. Run SETUP.bat."
                self.status_text = self.model_error
            return

        try:
            options = mp.tasks.vision.PoseLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(model_asset_path=str(MODEL_PATH)),
                running_mode=mp.tasks.vision.RunningMode.VIDEO,
                num_poses=1,
                min_pose_detection_confidence=0.55,
                min_pose_presence_confidence=0.55,
                min_tracking_confidence=0.55,
            )
            landmarker = mp.tasks.vision.PoseLandmarker.create_from_options(options)
        except Exception as exc:
            with self.lock:
                self.model_error = f"Could not load pose detector: {exc}"
                self.status_text = self.model_error
            return

        cap: cv2.VideoCapture | None = None
        timestamp_ms = 0
        previous_tick = time.monotonic()

        def open_camera(index: int) -> cv2.VideoCapture:
            if os.name == "nt":
                camera = cv2.VideoCapture(index, cv2.CAP_DSHOW)
                if not camera.isOpened():
                    camera.release()
                    camera = cv2.VideoCapture(index)
            else:
                camera = cv2.VideoCapture(index)
            camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            camera.set(cv2.CAP_PROP_FPS, 30)
            return camera

        try:
            with self.lock:
                index = self.camera_index_value
            cap = open_camera(index)
            if not cap.isOpened():
                with self.lock:
                    self.status_text = f"Could not open camera {index}. Try another camera index."

            while self.running:
                with self.lock:
                    restart = self.camera_restart
                    if restart:
                        self.camera_restart = False
                        index = self.camera_index_value
                if restart:
                    if cap is not None:
                        cap.release()
                    cap = open_camera(index)
                    timestamp_ms = 0

                if cap is None or not cap.isOpened():
                    time.sleep(0.25)
                    continue

                ok, frame = cap.read()
                if not ok or frame is None:
                    with self.lock:
                        self.status_text = "Camera frame failed. Restarting camera..."
                        self.camera_restart = True
                    time.sleep(0.15)
                    continue

                frame = cv2.flip(frame, 1)
                frame = cv2.resize(frame, (960, 540), interpolation=cv2.INTER_AREA)
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                now = time.monotonic()
                elapsed_ms = max(1, int((now - previous_tick) * 1000))
                previous_tick = now
                timestamp_ms += elapsed_ms

                result = None
                try:
                    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                    result = landmarker.detect_for_video(mp_image, timestamp_ms)
                except Exception as exc:
                    with self.lock:
                        self.status_text = f"Pose detection error: {exc}"

                embedding = None
                if result and result.pose_world_landmarks:
                    embedding = pose_embedding(result.pose_world_landmarks[0])
                    if result.pose_landmarks:
                        self._draw_pose(frame, result.pose_landmarks[0])

                self._process_capture_or_detection(embedding, now)

                with self.lock:
                    overlay_status = self.status_text
                    overlay_match = self.match_text
                    capture_active = self.capture_plan is not None
                    enabled = self.triggers_enabled

                cv2.rectangle(frame, (0, 0), (960, 45), (0, 0, 0), -1)
                cv2.putText(frame, overlay_status[:95], (12, 29), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2, cv2.LINE_AA)
                if capture_active:
                    cv2.rectangle(frame, (0, 500), (960, 540), (0, 105, 255), -1)
                    cv2.putText(frame, "CAPTURING POSE", (365, 527), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2, cv2.LINE_AA)
                elif not enabled:
                    cv2.rectangle(frame, (0, 500), (960, 540), (70, 70, 70), -1)
                    cv2.putText(frame, "HOTKEYS PAUSED", (374, 527), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2, cv2.LINE_AA)
                elif overlay_match:
                    cv2.putText(frame, overlay_match[:60], (12, 520), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2, cv2.LINE_AA)

                with self.lock:
                    self.latest_frame = frame.copy()
        finally:
            if cap is not None:
                cap.release()
            landmarker.close()

    def _process_capture_or_detection(self, embedding: np.ndarray | None, now: float) -> None:
        with self.lock:
            plan = self.capture_plan

        if plan is not None:
            start = float(plan["capture_start"])
            end = float(plan["capture_end"])
            if now < start:
                remaining = max(1, int(math.ceil(start - now)))
                with self.lock:
                    self.status_text = f"Get ready: {remaining}"
                    self.match_text = ""
                return

            if embedding is not None and now <= end:
                with self.lock:
                    if self.capture_plan is not None:
                        self.capture_plan["samples"].append(embedding.copy())
                        count = len(self.capture_plan["samples"])
                        self.status_text = f"Hold the pose... sample {count}"
                return

            if now > end:
                with self.lock:
                    current = self.capture_plan
                    self.capture_plan = None
                if current is None:
                    return
                samples = current["samples"]
                if len(samples) < 8:
                    with self.lock:
                        self.status_text = "Capture failed: keep your face, both shoulders, and both arms visible, then try again."
                    return
                averaged = robust_average(samples)
                gesture = {
                    "id": str(uuid.uuid4()),
                    "name": current["name"],
                    "hotkey": current["hotkey"],
                    "strictness": current["strictness"],
                    "cooldown": current["cooldown"],
                    "hold_frames": current["hold_frames"],
                    "enabled": True,
                    "embedding": averaged.tolist(),
                }
                with self.lock:
                    self.gestures.append(gesture)
                    save_gestures(self.gestures)
                    self.refresh_needed = True
                    self.status_text = f"Saved pose: {gesture['name']}"
                    self.match_text = "Move out of the pose, then try it again."
                return

        with self.lock:
            triggers_enabled = self.triggers_enabled
            gestures = [dict(g) for g in self.gestures if g.get("enabled", True)]

        if not triggers_enabled:
            with self.lock:
                self.match_text = ""
            return

        if embedding is None:
            with self.lock:
                self.status_text = "Need your face and both shoulders visible. Hips and legs are not required."
                self.match_text = ""
            return

        distances: list[tuple[float, dict[str, Any]]] = []
        for gesture in gestures:
            try:
                reference = np.asarray(gesture["embedding"], dtype=np.float32)
                distances.append((embedding_distance(embedding, reference), gesture))
            except Exception:
                continue

        if not distances:
            with self.lock:
                self.status_text = "Camera ready. Capture a pose to begin."
                self.match_text = ""
            return

        distances.sort(key=lambda pair: pair[0])
        best_distance, best_gesture = distances[0]
        best_id = str(best_gesture["id"])
        best_threshold = strictness_to_threshold(float(best_gesture.get("strictness", 72)))
        score = max(0.0, min(100.0, 100.0 * (1.0 - best_distance / 0.35)))

        triggered: tuple[str, str] | None = None
        with self.lock:
            for _distance, gesture in distances:
                gid = str(gesture["id"])
                state = self.runtime.setdefault(gid, {
                    "match_count": 0,
                    "away_count": 0,
                    "armed": True,
                    "last_trigger": 0.0,
                })
                threshold = strictness_to_threshold(float(gesture.get("strictness", 72)))
                is_best_match = gid == best_id and best_distance <= best_threshold

                if is_best_match:
                    state["away_count"] = 0
                    if state["armed"]:
                        state["match_count"] += 1
                        needed = int(gesture.get("hold_frames", 5))
                        cooldown = float(gesture.get("cooldown", 1.0))
                        if state["match_count"] >= needed and now - state["last_trigger"] >= cooldown:
                            state["last_trigger"] = now
                            state["armed"] = False
                            state["match_count"] = 0
                            triggered = (str(gesture["hotkey"]), str(gesture["name"]))
                    else:
                        state["match_count"] = 0
                else:
                    state["match_count"] = max(0, int(state["match_count"]) - 1)
                    relevant_distance = best_distance if gid == best_id else _distance
                    if relevant_distance > threshold * 1.22:
                        state["away_count"] += 1
                        if state["away_count"] >= 4:
                            state["armed"] = True
                    else:
                        state["away_count"] = 0

            if best_distance <= best_threshold:
                state = self.runtime[best_id]
                if state["armed"]:
                    needed = int(best_gesture.get("hold_frames", 5))
                    self.status_text = f"Matching {best_gesture['name']}... {state['match_count']}/{needed}"
                else:
                    self.status_text = f"{best_gesture['name']} recognized — move out of the pose to re-arm."
                self.match_text = f"Best match: {best_gesture['name']} ({score:.0f}%)"
            else:
                self.status_text = "Watching for gestures..."
                self.match_text = f"Closest: {best_gesture['name']} ({score:.0f}%)"

        if triggered is not None:
            hotkey, name = triggered
            threading.Thread(target=self._safe_send_hotkey, args=(hotkey, name), daemon=True).start()

    def _update_ui(self) -> None:
        if not self.running:
            return
        with self.lock:
            frame = None if self.latest_frame is None else self.latest_frame.copy()
            status = self.status_text
            match = self.match_text
            refresh = self.refresh_needed
        if refresh:
            self._refresh_listbox()
        self.status_label.configure(text=status)
        self.match_label.configure(text=match)
        if frame is not None:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = Image.fromarray(rgb)
            photo = ImageTk.PhotoImage(image=image)
            self.video_label.configure(image=photo)
            self.video_label.image = photo
        self.root.after(40, self._update_ui)

    def on_close(self) -> None:
        self.running = False
        self.root.after(80, self.root.destroy)


def main() -> None:
    root = tk.Tk()
    GestureHotkeyApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
