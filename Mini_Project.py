import tkinter as tk
import cv2
import mediapipe as mp
import pyautogui
import time
from threading import Thread

# MediaPipe ka matter (initialize once, outside function)
mp_hands = mp.solutions.hands
mp_draw = mp.solutions.drawing_utils
hands = mp_hands.Hands(max_num_hands=1, min_detection_confidence=0.7)

def fingers_up(hand_landmarks):
    finger_tips = [8, 12, 16, 20]  # index, middle, ring, pinky
    thumb_tip = 4
    fingers = []

    # Thumb ka matter
    if hand_landmarks.landmark[thumb_tip].x < hand_landmarks.landmark[thumb_tip - 1].x:
        fingers.append(1)
    else:
        fingers.append(0)

    # Other fingers ka matter
    for tip in finger_tips:
        if hand_landmarks.landmark[tip].y < hand_landmarks.landmark[tip - 2].y:
            fingers.append(1)
        else:
            fingers.append(0)
    return fingers

def run_gesture_player():
    cap = cv2.VideoCapture(0)  # webcam capture start

    prev_time = 0
    gesture_state = None
    last_gesture_time = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            print("❌ Frame not received")  # matter ho gya
            break

        frame = cv2.flip(frame, 1)
        h, w, _ = frame.shape
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        results = hands.process(rgb_frame)

        if results.multi_hand_landmarks:
            for hand_landmarks in results.multi_hand_landmarks:
                mp_draw.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)

                fingers = fingers_up(hand_landmarks)
                print(f"Fingers detected: {fingers}")
                thumb_tip_y = hand_landmarks.landmark[4].y * h
                thumb_base_y = hand_landmarks.landmark[2].y * h
                current_time = time.time()

                # ===== Continuous Volume Control ===== (lagatar badhegi ghategi volume)
                if fingers[0] == 1 and sum(fingers[1:]) == 0:
                    if thumb_tip_y < thumb_base_y - 30:
                        pyautogui.press("volumeup")
                        cv2.putText(frame, "🔊 Volume Up", (10, 50),
                                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,0), 2)
                    elif thumb_tip_y > thumb_base_y + 30:
                        pyautogui.press("volumedown")
                        cv2.putText(frame, "🔉 Volume Down", (10, 50),
                                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,0), 2)

                # ===== Play / Pause =====
                elif fingers == [1,1,1,1,1] and gesture_state != "play":
                    pyautogui.press("playpause")
                    gesture_state = "play"
                    last_gesture_time = current_time
                    cv2.putText(frame, "▶️ Play", (10, 100),
                                cv2.FONT_HERSHEY_SIMPLEX, 1, (255,255,0), 2)

                elif fingers == [0,0,0,0,0] and gesture_state != "pause":
                    pyautogui.press("playpause")
                    gesture_state = "pause"
                    last_gesture_time = current_time
                    cv2.putText(frame, "⏸ Pause", (10, 100),
                                cv2.FONT_HERSHEY_SIMPLEX, 1, (255,0,0), 2)

        # Show the webcam feed with gestures overlaid
        cv2.imshow(" Hand Gesture Media Player", frame)  # title h ye bhai box ka

        # Exit on 'q' key press
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

def start():
    t = Thread(target=run_gesture_player)
    t.daemon = True
    t.start()

# Tkinter GUI setup
root = tk.Tk()
root.title("Hand Gesture Media Player")
start_btn = tk.Button(root, text="Start Gesture Control", command=start)
start_btn.pack(pady=20)
root.mainloop()
