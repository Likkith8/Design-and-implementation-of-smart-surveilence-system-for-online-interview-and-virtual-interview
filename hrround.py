import cv2
import dlib
import numpy as np
import pyaudio
import struct
import threading
from collections import deque

# --- AUDIO SETUP ---
AUDIO_THRESHOLD = 300  # Adjust based on environment
audio_active = False
mic_access = False

def audio_listener():
    global audio_active, mic_access
    CHUNK = 1024
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 16000

    try:
        p = pyaudio.PyAudio()
        stream = p.open(format=FORMAT,
                        channels=CHANNELS,
                        rate=RATE,
                        input=True,
                        frames_per_buffer=CHUNK)
        mic_access = True

        while True:
            data = stream.read(CHUNK, exception_on_overflow=False)
            audio_data = struct.unpack(str(CHUNK) + 'h', data)
            rms = np.sqrt(np.mean(np.square(audio_data)))
            audio_active = rms > AUDIO_THRESHOLD

    except Exception as e:
        print(f"Microphone access failed: {e}")
        mic_access = False

# --- START AUDIO THREAD ---
audio_thread = threading.Thread(target=audio_listener, daemon=True)
audio_thread.start()

# --- VIDEO SETUP ---
camera = cv2.VideoCapture(0)
if not camera.isOpened():
    print("Failed to open camera.")
    exit()

# Load face and landmark detector
detector = dlib.get_frontal_face_detector()
predictor = dlib.shape_predictor("shape_predictor_68_face_landmarks.dat")  # Download separately

# --- Lip Movement Detection ---
def detect_lip_movement(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = detector(gray)
    if len(faces) == 0:
        return False

    for face in faces:
        shape = predictor(gray, face)
        top_lip = shape.part(62).y
        bottom_lip = shape.part(66).y
        distance = abs(top_lip - bottom_lip)
        return distance > 3  # Threshold for lip opening
    return False

# --- Gaze and Eye Direction ---
def get_eye_direction(eye_landmarks):
    left_eye = np.array(eye_landmarks[0:6])  # Left eye landmarks
    right_eye = np.array(eye_landmarks[6:12])  # Right eye landmarks

    # Get center points of both eyes
    left_center = np.mean(left_eye, axis=0)
    right_center = np.mean(right_eye, axis=0)

    # Calculate the horizontal distance between the eye centers
    eye_center_x = (left_center[0] + right_center[0]) / 2

    if eye_center_x < 200:  # Left
        return 'Left'
    elif eye_center_x > 440:  # Right
        return 'Right'
    else:  # Center
        return 'Center'

# --- TEMPORAL BUFFER FOR STABILITY ---
HISTORY_LENGTH = 15  # About 0.5 sec at ~30 FPS
lip_movement_history = deque(maxlen=HISTORY_LENGTH)
audio_activity_history = deque(maxlen=HISTORY_LENGTH)

# --- PERSON COUNT SETUP ---
detected_persons = {}  # Using a dictionary to track people by their face id (or some unique feature)

# --- MAIN LOOP ---
while True:
    ret, frame = camera.read()
    if not ret:
        break

    # Convert to grayscale
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # Detect faces
    faces = detector(gray)
    current_persons = {}

    # --- Gaze and Eye Direction Tracking ---
    gaze_tracking = False
    eye_direction = "Center"

    for face in faces:
        # Use face coordinates to uniquely identify each face
        current_persons[face] = True  # Mark face as detected

        shape = predictor(gray, face)
        
        # Get the left and right eye landmarks
        left_eye_landmarks = [(shape.part(i).x, shape.part(i).y) for i in range(36, 42)]
        right_eye_landmarks = [(shape.part(i).x, shape.part(i).y) for i in range(42, 48)]

        # Gaze tracking logic
        left_eye = np.array(left_eye_landmarks)
        right_eye = np.array(right_eye_landmarks)
        
        # Calculate the EAR for gaze detection (eye aspect ratio)
        left_eye_horiz_dist = np.linalg.norm(left_eye[0] - left_eye[3])
        left_eye_vert_dist = np.linalg.norm(left_eye[1] - left_eye[5])
        right_eye_horiz_dist = np.linalg.norm(right_eye[0] - right_eye[3])
        right_eye_vert_dist = np.linalg.norm(right_eye[1] - right_eye[5])

        ear_left = left_eye_horiz_dist / left_eye_vert_dist
        ear_right = right_eye_horiz_dist / right_eye_vert_dist

        if ear_left > 0.25 and ear_right > 0.25:  # Adjust for better threshold
            gaze_tracking = True
            eye_direction = get_eye_direction(left_eye_landmarks + right_eye_landmarks)

    # --- Person Count Logic ---
    # Keep the set of detected faces consistent
    for face in list(detected_persons):
        if face not in current_persons:  # If the face is no longer detected, remove it
            detected_persons.pop(face)

    # Add new faces
    for face in current_persons:
        if face not in detected_persons:
            detected_persons[face] = True

    person_count = len(detected_persons)

    # Lip Cheating Logic
    lip_moving = detect_lip_movement(frame)
    lip_movement_history.append(lip_moving)
    audio_activity_history.append(audio_active)

    # Temporal smoothing logic
    lips_recent = sum(lip_movement_history)
    audio_recent = sum(audio_activity_history)

    lips_talking = lips_recent > HISTORY_LENGTH * 0.4
    audio_talking = audio_recent > HISTORY_LENGTH * 0.4

    # Final Cheating Logic
    if lips_talking and audio_talking:
        lip_cheating = False
    elif not lips_talking and not audio_talking:
        lip_cheating = False
    else:
        lip_cheating = True

    # --- DISPLAY RESULTS ---
    lip_color = (0, 0, 255) if lip_cheating else (0, 255, 0)
    cv2.putText(frame, f"Lip Cheating: {lip_cheating}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, lip_color, 2)

    # Gaze Tracking Display
    gaze_color = (0, 255, 0) if gaze_tracking else (0, 0, 255)
    cv2.putText(frame, f"Gaze Tracking: {gaze_tracking}", (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.8, gaze_color, 2)
    cv2.putText(frame, f"Eye: {eye_direction}", (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)

    # Person Count Display
    cv2.putText(frame, f"Person Count: {person_count}", (10, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)

    # Mic Status Display
    mic_status = "Active" if mic_access else "Not Detected"
    audio_status = "Detected" if audio_active else "Silent"
    cv2.putText(frame, f"Mic: {mic_status}", (10, 160), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)
    cv2.putText(frame, f"Audio: {audio_status}", (10, 190), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)

    # Show the frame
    cv2.imshow("Lip Cheating Detection", frame)

    # Exit on pressing ESC
    if cv2.waitKey(1) & 0xFF == 27:
        break

camera.release()
cv2.destroyAllWindows()
