# ✋ Hand Gesture Media Player

Control your media player using hand gestures — no keyboard, no mouse needed. Built with Python, OpenCV, and MediaPipe.

---

## 📸 Demo

> Webcam feed is embedded directly inside the app window. Landmarks are overlaid in real time by MediaPipe.

---

## ✨ Features

- 🎥 **Live webcam feed** embedded inside the GUI (no separate OpenCV window)
- 🤚 **Real-time hand tracking** using MediaPipe
- ▶️ **Separate Play & Pause** gestures — holding a gesture won't re-trigger
- 🎛️ **Fully customizable gestures** — assign any action to any finger combo
- ⦿ **Record Gesture mode** — show your hand to the camera to capture a new gesture live
- 💾 **Gestures saved to `gestures.json`** — persists across sessions
- 🧠 **Gesture smoothing** — must hold gesture for 6 frames to avoid accidental triggers
- ⏱️ **Cooldown timer** — prevents rapid re-firing
- 📋 **Activity log** with timestamps
- 🛑 **Start / Stop controls** from the GUI

---

## 🤌 Default Gestures

| Gesture | Fingers | Action |
|---|---|---|
| ✋ All open | `▮▮▮▮▮` | Play |
| ✊ Fist | `▯▯▯▯▯` | Pause |
| ☝️ Index only | `▯▮▯▯▯` | Next Track |
| 🤙 Pinky only | `▮▯▯▯▮` | Previous Track |
| ✌️ Two fingers | `▯▮▮▯▯` | Volume Up |
| 💍 Ring only | `▯▯▯▮▯` | Volume Down |
| 🤟 Three fingers | `▯▮▮▮▯` | Mute |

> All gestures can be changed from the **Settings** panel inside the app.

---

## 🛠️ Installation

**1. Clone the repo**
```bash
git clone https://github.com/YOUR_USERNAME/hand-gesture-media-player.git
cd hand-gesture-media-player
```

**2. Install dependencies**
```bash
pip install opencv-python mediapipe pyautogui pillow
```

**3. Run**
```bash
python gesture_media_player.py
```

---

## 🖥️ Requirements

- Python 3.9+
- Webcam
- Windows / macOS / Linux

> **macOS users:** Grant accessibility permissions to Terminal or VSCode under  
> System Settings → Privacy & Security → Accessibility

---

## 📁 Project Structure

```
hand-gesture-media-player/
│
├── gesture_media_player.py   # Main application
├── gestures.json             # Auto-generated gesture config (after first run)
└── README.md
```

---

## ⚙️ Customizing Gestures

1. Click **⚙ Settings** inside the app
2. Use checkboxes to toggle which fingers are raised
3. Pick an action from the dropdown
4. Or click **⦿ Record Gesture** and hold your hand in front of the camera
5. Click **Save Changes**

Gestures are saved to `gestures.json` automatically.

---

## 🚀 Built With

- [OpenCV](https://opencv.org/) — webcam capture & frame processing
- [MediaPipe](https://mediapipe.dev/) — hand landmark detection
- [PyAutoGUI](https://pyautogui.readthedocs.io/) — media key simulation
- [Pillow](https://pillow.readthedocs.io/) — embedding webcam feed in Tkinter
- [Tkinter](https://docs.python.org/3/library/tkinter.html) — GUI framework

---

## 📄 License

MIT License — free to use and modify.
