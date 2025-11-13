from flask import Flask, render_template, request, jsonify
import cv2
import numpy as np
import pyautogui
import threading
import time
import os
from datetime import datetime
from win32api import GetSystemMetrics

app = Flask(__name__)
recording_thread = None
recording_active = False
email_global = None

# Ensure logs folder exists
if not os.path.exists("logs"):
    os.makedirs("logs")

# Function to handle recording
def record_screen(email):
    global recording_active
    recording_active = True

    width = GetSystemMetrics(0)
    height = GetSystemMetrics(1)
    frame_rate = 1

    # Setup video writer
    fourcc = cv2.VideoWriter_fourcc(*"XVID")
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = os.path.join("logs", f"{email}_{timestamp}.avi")
    out = cv2.VideoWriter(filename, fourcc, frame_rate, (width, height))

    # Webcam setup
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[ERROR] Webcam not accessible. Proceeding with screen-only recording.")
        cap = None

    x_offset, y_offset = width - 220, 20  # Top-right corner

    while recording_active:
        try:
            img = pyautogui.screenshot()
            frame = np.array(img)
            screen = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

            if cap:
                ret, webcam_frame = cap.read()
                if ret and webcam_frame is not None:
                    webcam_frame = cv2.resize(webcam_frame, (200, 150))
                    screen[y_offset:y_offset+150, x_offset:x_offset+200] = webcam_frame
                else:
                    print("[WARNING] Failed to read webcam frame.")
            else:
                print("[INFO] Skipping webcam overlay (no camera).")

            out.write(screen)
            time.sleep(1 / frame_rate)
        except Exception as e:
            print(f"[ERROR] During recording: {e}")
            break

    if cap:
        cap.release()
    out.release()
    print("[INFO] Recording stopped.")

# Route: Homepage
@app.route("/")
def index():
    return render_template("index.html")

# Route: Start Recording (called after email entered)
@app.route("/start_recording", methods=["POST"])
def start_recording():
    global recording_thread, email_global, recording_active

    data = request.get_json()
    email = data.get("email")
    email_global = email

    if not email:
        return jsonify({"status": "error", "message": "Email is required"}), 400

    if recording_active:
        return jsonify({"status": "already recording"}), 200

    recording_thread = threading.Thread(target=record_screen, args=(email,))
    recording_thread.start()
    return jsonify({"status": "recording started"}), 200


@app.route("/stop_recording", methods=["POST"])
def stop_recording():
    global recording_active, recording_thread

    recording_active = False
    if recording_thread and recording_thread.is_alive():
        recording_thread.join(timeout=5)
    return jsonify({"status": "recording stopped"}), 200

# Route: Log final activity
@app.route("/log_final_activity", methods=["POST"])
def log_final_activity():
    global recording_active, recording_thread

    data = request.get_json()
    email = data.get("email")
    answer = data.get("final_answer", "").strip()
    time_spent = data.get("time_spent_seconds", 0)
    tab_switches = data.get("tab_switches", 0)
    window_blurs = data.get("window_blurs", 0)

    log_path = os.path.join("logs", f"{email}_log.txt")
    with open(log_path, "a") as log:
        log.write(f"\n------ TEST SUBMITTED AT {datetime.now()} ------\n")
        log.write(f"Time Spent (sec): {time_spent}\n")
        log.write(f"Tab Switches: {tab_switches}\n")
        log.write(f"Window Blurs: {window_blurs}\n")
        log.write(f"Answer:\n{answer}\n")

    # Stop the recording
    recording_active = False
    if recording_thread and recording_thread.is_alive():
        recording_thread.join(timeout=5)

    return jsonify({"status": "success", "message": "Activity logged and recording stopped"}), 200

if __name__ == "__main__":
    app.run(debug=True)
