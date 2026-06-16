import tkinter as tk
from tkinter import ttk, messagebox
import cv2
import mediapipe as mp
import pyautogui
import time
import json
import os
from threading import Thread
from PIL import Image, ImageTk

# ─────────────────────────────────────────────────────────
#  Constants & Defaults
# ─────────────────────────────────────────────────────────
GESTURE_CONFIG_FILE = "gestures.json"
DETECTION_CONFIDENCE = 0.7
COOLDOWN_SEC        = 0.8   # minimum seconds between gesture triggers
SMOOTH_FRAMES       = 6     # gesture must stay stable for this many frames

FINGER_NAMES = ["Thumb", "Index", "Middle", "Ring", "Pinky"]

ACTION_LABELS = {
    "play":       "Play",
    "pause":      "Pause",
    "playpause":  "Play / Pause (toggle)",
    "nexttrack":  "Next Track",
    "prevtrack":  "Previous Track",
    "volumeup":   "Volume Up",
    "volumedown": "Volume Down",
    "mute":       "Mute",
    "none":       "No Action",
}

ACTION_EMOJI = {
    "play":       "▶️",
    "pause":      "⏸",
    "playpause":  "⏯",
    "nexttrack":  "⏭",
    "prevtrack":  "⏮",
    "volumeup":   "🔊",
    "volumedown": "🔉",
    "mute":       "🔇",
    "none":       "—",
}

# finger pattern → action key
DEFAULT_GESTURES = {
    "[1,1,1,1,1]": "play",        # all open   → play
    "[0,0,0,0,0]": "pause",       # fist       → pause
    "[0,1,0,0,0]": "nexttrack",   # index only → next track
    "[1,0,0,0,1]": "prevtrack",   # pinky only → prev track
    "[0,1,1,0,0]": "volumeup",    # 2 fingers  → volume up
    "[0,0,0,1,0]": "volumedown",  # ring only  → volume down
    "[0,1,1,1,0]": "mute",        # 3 fingers  → mute
}

# ─────────────────────────────────────────────────────────
#  GestureConfig  — load / save / query the gesture map
# ─────────────────────────────────────────────────────────
class GestureConfig:
    def __init__(self, path=GESTURE_CONFIG_FILE):
        self.path = path
        self.gesture_map: dict[tuple, str] = {}
        self.load()

    def load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path) as f:
                    raw = json.load(f)
                self.gesture_map = {
                    tuple(json.loads(k)): v for k, v in raw.items()
                }
                return
            except Exception:
                pass
        # fall back to built-in defaults
        self.gesture_map = {
            tuple(json.loads(k)): v for k, v in DEFAULT_GESTURES.items()
        }

    def save(self):
        data = {json.dumps(list(k)): v for k, v in self.gesture_map.items()}
        with open(self.path, "w") as f:
            json.dump(data, f, indent=2)

    def get_action(self, fingers: list) -> str | None:
        return self.gesture_map.get(tuple(fingers))

    def set_gesture(self, fingers: tuple, action: str):
        self.gesture_map[tuple(fingers)] = action

    def clear(self):
        self.gesture_map.clear()


# ─────────────────────────────────────────────────────────
#  GestureDetector  — MediaPipe wrapper
# ─────────────────────────────────────────────────────────
class GestureDetector:
    def __init__(self):
        self.mp_hands = mp.solutions.hands
        self.mp_draw  = mp.solutions.drawing_utils
        self._hands   = self.mp_hands.Hands(
            max_num_hands=1,
            min_detection_confidence=DETECTION_CONFIDENCE,
        )

    def process(self, rgb_frame):
        return self._hands.process(rgb_frame)

    def fingers_up(self, hand_landmarks, handedness: str = "Right") -> list:
        """
        Returns [thumb, index, middle, ring, pinky] as 0/1.
        Fixes the original thumb bug by using handedness label.
        """
        tip_ids = [8, 12, 16, 20]
        fingers = []

        # Thumb: compare x-position relative to the knuckle, adjusted for hand side
        thumb_tip  = hand_landmarks.landmark[4].x
        thumb_mcp  = hand_landmarks.landmark[2].x
        if handedness == "Right":
            fingers.append(1 if thumb_tip < thumb_mcp else 0)
        else:
            fingers.append(1 if thumb_tip > thumb_mcp else 0)

        # Other four fingers: tip.y above pip.y means finger is raised
        for tip in tip_ids:
            fingers.append(
                1 if hand_landmarks.landmark[tip].y < hand_landmarks.landmark[tip - 2].y else 0
            )
        return fingers

    def close(self):
        self._hands.close()


# ─────────────────────────────────────────────────────────
#  GestureApp  — main Tkinter application
# ─────────────────────────────────────────────────────────
class GestureApp:

    # ── Colours & fonts (centralised so easy to retheme) ──
    BG     = "#F5F4F0"
    CARD   = "#FFFFFF"
    ACCENT = "#534AB7"
    DANGER = "#A32D2D"
    FG     = "#1A1A1A"
    FG2    = "#6B6B6B"
    BORDER = "#E0DFD8"

    FONT      = ("Segoe UI", 10)
    FONT_BOLD = ("Segoe UI", 10, "bold")
    FONT_SM   = ("Segoe UI", 9)
    FONT_MONO = ("Courier New", 9)

    # ── Init ──────────────────────────────────────────────
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Hand Gesture Media Player")
        self.root.configure(bg=self.BG)
        self.root.resizable(False, False)

        self.config   = GestureConfig()
        self.detector = GestureDetector()

        # camera state
        self.running  = False
        self.cap      = None
        self.thread   = None

        # gesture smoothing
        self.gesture_history: list[list] = []
        self.last_action_time: float     = 0.0

        # play/pause state tracking — prevents re-triggering while holding gesture
        self.is_playing: bool = False

        # live-record mode
        self.recording_mode    = False
        self.recorded_fingers  = None

        # activity log
        self.log_entries: list[str] = []

        # tkinter string vars for status bar
        self.sv_cam     = tk.StringVar(value="Camera off")
        self.sv_hand    = tk.StringVar(value="No hand")
        self.sv_gesture = tk.StringVar(value="—")

        self._build_ui()

    # ── UI Construction ───────────────────────────────────
    def _build_ui(self):
        root = self.root

        # ── Header ──────────────────────────────────────
        hdr = tk.Frame(root, bg=self.BG)
        hdr.pack(fill="x", padx=16, pady=(14, 6))

        logo = tk.Label(hdr, text="✋", bg=self.ACCENT, fg="white",
                        font=("Segoe UI", 16), padx=6, pady=2, relief="flat")
        logo.pack(side="left")

        tk.Label(hdr, text="  Gesture Media Player",
                 bg=self.BG, fg=self.FG,
                 font=("Segoe UI", 14, "bold")).pack(side="left")

        # ── Status Bar ──────────────────────────────────
        sbar = tk.Frame(root, bg=self.BG)
        sbar.pack(fill="x", padx=16, pady=(0, 8))

        for icon, sv in [("⚫", self.sv_cam), ("🤚", self.sv_hand), ("👁", self.sv_gesture)]:
            pill = tk.Frame(sbar, bg="#EEEEE8",
                            highlightbackground=self.BORDER, highlightthickness=1)
            pill.pack(side="left", padx=(0, 6))
            tk.Label(pill, text=icon, bg="#EEEEE8",
                     font=("Segoe UI", 9)).pack(side="left", padx=(6, 2), pady=3)
            tk.Label(pill, textvariable=sv, bg="#EEEEE8",
                     fg="#3A3A3A", font=self.FONT_SM).pack(side="left", padx=(0, 8), pady=3)

        # ── Webcam Feed ─────────────────────────────────
        cam_wrapper = tk.Frame(root, bg=self.CARD,
                               highlightbackground=self.BORDER, highlightthickness=1)
        cam_wrapper.pack(padx=16, pady=(0, 10))

        self.cam_label = tk.Label(cam_wrapper, bg="#111111", width=480, height=270)
        self.cam_label.pack()
        self._show_placeholder()

        # ── Control Buttons ──────────────────────────────
        ctrl = tk.Frame(root, bg=self.BG)
        ctrl.pack(fill="x", padx=16, pady=(0, 10))

        self.btn_start = self._btn(ctrl, "▶  Start",   self.ACCENT, "white", self.start)
        self.btn_start.pack(side="left", padx=(0, 6))

        self.btn_stop = self._btn(ctrl, "■  Stop", self.DANGER, "white", self.stop)
        self.btn_stop.config(state="disabled")
        self.btn_stop.pack(side="left", padx=(0, 6))

        self._btn(ctrl, "⚙  Settings", self.CARD, self.FG,
                  self.open_settings, border=True).pack(side="left")

        # ── Gesture Map ──────────────────────────────────
        self._section_label(root, "GESTURE MAP")
        self.gesture_frame = tk.Frame(root, bg=self.BG)
        self.gesture_frame.pack(fill="x", padx=16)
        self._refresh_gesture_map()

        # ── Activity Log ─────────────────────────────────
        self._section_label(root, "RECENT ACTIVITY", top=10)

        log_wrapper = tk.Frame(root, bg=self.CARD,
                               highlightbackground=self.BORDER, highlightthickness=1)
        log_wrapper.pack(fill="x", padx=16, pady=(0, 14))

        self.log_text = tk.Text(log_wrapper, height=4, bg=self.CARD, fg=self.FG2,
                                font=self.FONT_SM, relief="flat",
                                state="disabled", padx=8, pady=6)
        self.log_text.pack(fill="x")

    # ── Helpers ───────────────────────────────────────────
    def _btn(self, parent, text, bg, fg, cmd, border=False):
        kw = dict(bg=bg, fg=fg, text=text, font=self.FONT_BOLD,
                  relief="flat", padx=14, pady=6, cursor="hand2", command=cmd)
        if border:
            kw.update(highlightbackground=self.BORDER, highlightthickness=1)
        return tk.Button(parent, **kw)

    def _section_label(self, parent, text, top=4):
        tk.Label(parent, text=text, bg=self.BG, fg=self.FG2,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=16,
                                                    pady=(top, 4))

    def _show_placeholder(self):
        img   = Image.new("RGB", (480, 270), (17, 17, 17))
        photo = ImageTk.PhotoImage(img)
        self.cam_label.config(image=photo)
        self.cam_label.image = photo

    def _fingers_bar(self, fingers: list) -> str:
        return "".join("▮" if f else "▯" for f in fingers)

    def _refresh_gesture_map(self):
        for w in self.gesture_frame.winfo_children():
            w.destroy()

        items = [(f, a) for f, a in self.config.gesture_map.items() if a != "none"]
        col, row = 0, 0

        for fingers, action in items:
            card = tk.Frame(self.gesture_frame, bg=self.CARD,
                            highlightbackground=self.BORDER, highlightthickness=1)
            card.grid(row=row, column=col,
                      padx=(0, 6) if col == 0 else 0, pady=3, sticky="ew")

            tk.Label(card, text=ACTION_EMOJI.get(action, "🎵"),
                     bg=self.CARD, font=("Segoe UI", 16),
                     pady=4).pack(side="left", padx=(8, 4))

            info = tk.Frame(card, bg=self.CARD)
            info.pack(side="left", pady=6, padx=(0, 8))
            tk.Label(info, text=ACTION_LABELS.get(action, action),
                     bg=self.CARD, fg=self.FG,
                     font=self.FONT_BOLD, anchor="w").pack(anchor="w")
            tk.Label(info, text=self._fingers_bar(fingers),
                     bg=self.CARD, fg=self.FG2,
                     font=self.FONT_MONO, anchor="w").pack(anchor="w")

            col += 1
            if col == 2:
                col = 0
                row += 1

        self.gesture_frame.columnconfigure(0, weight=1)
        self.gesture_frame.columnconfigure(1, weight=1)

    def _log(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        self.log_entries.insert(0, f"{ts}   {msg}")
        self.log_entries = self.log_entries[:20]
        self.root.after(0, self._refresh_log)

    def _refresh_log(self):
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        for entry in self.log_entries[:4]:
            self.log_text.insert("end", entry + "\n")
        self.log_text.config(state="disabled")

    # ── Camera / Detection Loop ───────────────────────────
    def start(self):
        if self.running:
            return
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            messagebox.showerror("Camera Error", "Could not open webcam.")
            return
        self.running = True
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.sv_cam.set("Camera active")
        self.gesture_history.clear()
        self.thread = Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.sv_cam.set("Camera off")
        self.sv_hand.set("No hand")
        self.sv_gesture.set("—")
        self._show_placeholder()
        if self.cap:
            self.cap.release()
            self.cap = None

    def _loop(self):
        mp_draw = mp.solutions.drawing_utils

        while self.running:
            if self.cap is None:
                break
            ret, frame = self.cap.read()
            if not ret:
                break

            frame = cv2.flip(frame, 1)
            rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.detector.process(rgb)

            detected_fingers = None
            hand_count = 0

            if results.multi_hand_landmarks:
                hand_count = len(results.multi_hand_landmarks)
                for i, lm in enumerate(results.multi_hand_landmarks):
                    mp_draw.draw_landmarks(frame, lm,
                                           self.detector.mp_hands.HAND_CONNECTIONS)
                    # get handedness (Left / Right)
                    label = "Right"
                    if results.multi_handedness:
                        label = results.multi_handedness[i].classification[0].label
                    detected_fingers = self.detector.fingers_up(lm, label)

            # ── Gesture smoothing ──
            if detected_fingers is not None:
                self.gesture_history.append(detected_fingers)
                if len(self.gesture_history) > SMOOTH_FRAMES:
                    self.gesture_history.pop(0)

                stable = (
                    len(self.gesture_history) == SMOOTH_FRAMES
                    and all(f == detected_fingers for f in self.gesture_history)
                )
                if stable:
                    self._handle_gesture(detected_fingers)

                bar = self._fingers_bar(detected_fingers)
                self.root.after(0, self.sv_gesture.set, bar)
                self.root.after(0, self.sv_hand.set,
                                f"{hand_count} hand detected")
            else:
                self.gesture_history.clear()
                self.root.after(0, self.sv_gesture.set, "—")
                self.root.after(0, self.sv_hand.set, "No hand")

            # ── Push frame to Tkinter ──
            frame_rgb     = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame_resized = cv2.resize(frame_rgb, (480, 270))
            img   = Image.fromarray(frame_resized)
            photo = ImageTk.PhotoImage(img)
            self.root.after(0, self._update_cam, photo)

        # cleanup after loop ends
        if self.cap:
            self.cap.release()
            self.cap = None

    def _update_cam(self, photo):
        self.cam_label.config(image=photo)
        self.cam_label.image = photo   # keep reference

    def _handle_gesture(self, fingers: list):
        # If in recording mode, capture and return
        if self.recording_mode:
            self.recorded_fingers = list(fingers)
            self.recording_mode   = False
            return

        now = time.time()
        if now - self.last_action_time < COOLDOWN_SEC:
            return

        action = self.config.get_action(fingers)
        if action and action != "none":
            # State-aware play/pause — prevents re-triggering while holding gesture
            if action == "play":
                if self.is_playing:
                    return          # already playing, ignore
                pyautogui.press("playpause")
                self.is_playing = True
            elif action == "pause":
                if not self.is_playing:
                    return          # already paused, ignore
                pyautogui.press("playpause")
                self.is_playing = False
            else:
                try:
                    pyautogui.press(action)
                except Exception as e:
                    print(f"pyautogui error: {e}")
            self.last_action_time = now
            label = ACTION_LABELS.get(action, action)
            bar   = self._fingers_bar(fingers)
            self._log(f"{label}   [{bar}]")

    # ── Settings Window ───────────────────────────────────
    def open_settings(self):
        win = tk.Toplevel(self.root)
        win.title("Gesture Settings")
        win.configure(bg=self.BG)
        win.resizable(False, False)
        win.grab_set()   # modal

        tk.Label(win, text="Customize Gestures", bg=self.BG, fg=self.FG,
                 font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=16, pady=(14, 2))
        tk.Label(win, text="Toggle fingers, pick an action, then save.\n"
                            "Use Record Gesture to capture a live hand pose.",
                 bg=self.BG, fg=self.FG2, font=self.FONT_SM,
                 justify="left").pack(anchor="w", padx=16, pady=(0, 10))

        # ── Column headers ──
        hrow = tk.Frame(win, bg=self.BG)
        hrow.pack(fill="x", padx=16)
        for name in FINGER_NAMES:
            tk.Label(hrow, text=name[:3], bg=self.BG, fg=self.FG2,
                     font=("Segoe UI", 8), width=5).pack(side="left", padx=2)
        tk.Label(hrow, text="Action", bg=self.BG, fg=self.FG2,
                 font=("Segoe UI", 8), width=14).pack(side="left", padx=(14, 0))

        # ── Scrollable list of gesture rows ──
        list_canvas = tk.Canvas(win, bg=self.BG, highlightthickness=0, height=220)
        scrollbar   = ttk.Scrollbar(win, orient="vertical",
                                    command=list_canvas.yview)
        list_canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y", padx=(0, 4))
        list_canvas.pack(fill="both", expand=True, padx=16)

        list_frame = tk.Frame(list_canvas, bg=self.BG)
        list_canvas.create_window((0, 0), window=list_frame, anchor="nw")
        list_frame.bind("<Configure>",
                        lambda e: list_canvas.configure(
                            scrollregion=list_canvas.bbox("all")))

        rows = []   # list of dicts with finger_vars + action_var

        def add_row(fingers=None, action="playpause"):
            f = list(fingers) if fingers else [0, 0, 0, 0, 0]
            row_frame = tk.Frame(list_frame, bg=self.CARD,
                                 highlightbackground=self.BORDER,
                                 highlightthickness=1)
            row_frame.pack(fill="x", pady=2)

            finger_vars = []
            for i in range(5):
                v = tk.IntVar(value=f[i])
                cb = tk.Checkbutton(row_frame, variable=v, bg=self.CARD,
                                    activebackground=self.CARD,
                                    selectcolor=self.CARD, width=4)
                cb.pack(side="left", padx=2, pady=5)
                finger_vars.append(v)

            action_var = tk.StringVar(value=action)
            dd = ttk.Combobox(row_frame, textvariable=action_var, width=13,
                              values=list(ACTION_LABELS.keys()), state="readonly")
            dd.pack(side="left", padx=(10, 4))

            def remove(rf=row_frame, entry_ref=None):
                rf.destroy()
                if entry_ref in rows:
                    rows.remove(entry_ref)

            entry = {"frame": row_frame,
                     "fingers": finger_vars,
                     "action": action_var}

            tk.Button(row_frame, text="✕", bg=self.CARD, fg=self.DANGER,
                      font=self.FONT_BOLD, relief="flat", cursor="hand2",
                      command=lambda e=entry: (rows.remove(e),
                                               e["frame"].destroy())
                      ).pack(side="right", padx=6)

            rows.append(entry)

        # Populate from current config
        for fingers, action in self.config.gesture_map.items():
            add_row(list(fingers), action)

        # ── Add / Record buttons ──
        btn_row = tk.Frame(win, bg=self.BG)
        btn_row.pack(fill="x", padx=16, pady=8)

        tk.Button(btn_row, text="+ Add Row", bg=self.CARD, fg=self.FG,
                  font=self.FONT, relief="flat", padx=12, pady=5, cursor="hand2",
                  highlightbackground=self.BORDER, highlightthickness=1,
                  command=add_row).pack(side="left", padx=(0, 8))

        sv_rec = tk.StringVar(value="")

        def record_live():
            if not self.running:
                messagebox.showwarning("Camera off",
                                       "Start the camera first, then try recording.",
                                       parent=win)
                return
            sv_rec.set("Hold your gesture in front of the camera...")
            self.recording_mode   = True
            self.recorded_fingers = None

            def wait():
                for _ in range(60):        # wait up to 6 s
                    if self.recorded_fingers is not None:
                        f = self.recorded_fingers[:]
                        bar = self._fingers_bar(f)
                        win.after(0, sv_rec.set,
                                  f"Captured  [{bar}]  — row added!")
                        win.after(0, add_row, f, "playpause")
                        return
                    time.sleep(0.1)
                self.recording_mode = False
                win.after(0, sv_rec.set, "No gesture detected. Try again.")

            Thread(target=wait, daemon=True).start()

        tk.Button(btn_row, text="⦿ Record Gesture", bg=self.ACCENT, fg="white",
                  font=self.FONT_BOLD, relief="flat", padx=12, pady=5,
                  cursor="hand2", command=record_live).pack(side="left")

        tk.Label(win, textvariable=sv_rec, bg=self.BG, fg=self.ACCENT,
                 font=self.FONT_SM, wraplength=440).pack(anchor="w", padx=16)

        # ── Save ──
        def save():
            self.config.clear()
            for entry in rows:
                f = tuple(v.get() for v in entry["fingers"])
                a = entry["action"].get()
                self.config.set_gesture(f, a)
            self.config.save()
            self._refresh_gesture_map()
            win.destroy()

        tk.Button(win, text="Save Changes", bg=self.ACCENT, fg="white",
                  font=self.FONT_BOLD, relief="flat", padx=20, pady=8,
                  cursor="hand2", command=save).pack(pady=(4, 14))

    # ── Shutdown ──────────────────────────────────────────
    def on_close(self):
        self.stop()
        self.detector.close()
        self.root.destroy()


# ─────────────────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    app  = GestureApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()
