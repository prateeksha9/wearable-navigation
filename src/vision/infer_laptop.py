#!/usr/bin/env python3
"""
Dual Synap Real-Time Inference + Laptop Speaker TTS
---------------------------------------------------
- Reads live camera frames from /dev/video8
- Runs TWO Synap models sequentially
- Annotates detections
- Speaks detected label via laptop speaker using nc
"""

import os
import json
import cv2
from pathlib import Path
from synap import Network
from synap.preprocessor import Preprocessor
from synap.postprocessor import Detector

# -----------------------------
#  Laptop Speaker TTS Settings
# -----------------------------
LAPTOP_IP = "192.168.137.196"   # <--- YOUR laptop IP (confirmed earlier)
TTS_PORT = 5005

def speak(msg):
    """Send message to laptop speaker via netcat."""
    os.system(f'echo "{msg}" | nc {LAPTOP_IP} {TTS_PORT}')
    print(f"[SPOKEN] {msg}")


# -----------------------------------
#  Load Model + Preprocessor + Detector
# -----------------------------------
def load_model(model_path, score_thr=0.5):
    model_file = Path(model_path)
    net = Network(model_file)
    pre = Preprocessor()
    det = Detector(score_thr, 0, True, 0.5, False)
    return net, pre, det


# ---------------------
#  Run Model Function
# ---------------------
def run_model(net, pre, det, frame, labels):
    """
    Run a Synap model on a single frame and return:
      - annotated frame
      - detected labels (list)
    """
    tmp = "/tmp/frame.jpg"
    cv2.imwrite(tmp, frame)

    rect = pre.assign(net.inputs, tmp)
    outputs = net.predict()
    result = det.process(outputs, rect)

    annotated = frame.copy()
    detected_labels = []

    for item in result.items:
        bb = item.bounding_box
        x, y = int(bb.origin.x), int(bb.origin.y)
        w, h = int(bb.size.x), int(bb.size.y)

        label = labels[item.class_index] if item.class_index < len(labels) else f"class_{item.class_index}"
        detected_labels.append(label)

        cv2.rectangle(annotated, (x, y), (x + w, y + h), (0, 255, 0), 2)
        cv2.putText(annotated, label, (x, max(y - 10, 20)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

    return annotated, detected_labels


# ------------------------
#       MAIN LOOP
# ------------------------
def main():

    # ------- Load Both Models ---------
    model1 = "models/traffic_v3/model.synap"
    labels1 = json.load(open("models/traffic_v3/traffic_labels.json"))["labels"]

    model2 = "models/walksign_v6/model.synap"
    labels2 = json.load(open("models/walksign_v6/traffic_labels.json"))["labels"]

    net1, pre1, det1 = load_model(model1)
    net2, pre2, det2 = load_model(model2)

    # ---------- CAMERA SOURCE ----------
    cap = cv2.VideoCapture("/dev/video8")

    if not cap.isOpened():
        print("❌ ERROR: Camera /dev/video8 not available")
        speak("camera not connected")
        return

    print("📷 Camera opened successfully.")
    speak("camera connected")

    last_spoken = ""  # for debouncing repeated TTS

    while True:
        ret, frame = cap.read()
        if not ret:
            print("❌ Failed to read frame.")
            speak("camera error")
            break

        # ---------- RUN MODEL 1 ----------
        annotated1, labels_detected_1 = run_model(net1, pre1, det1, frame, labels1)

        # ---------- RUN MODEL 2 ----------
        annotated2, labels_detected_2 = run_model(net2, pre2, det2, annotated1, labels2)

        # Combine all labels
        combined_labels = labels_detected_1 + labels_detected_2

        # ---------- TTS: Speak only when label changes ----------
        if combined_labels:
            text_to_speak = " , ".join(combined_labels)

            if text_to_speak != last_spoken:    # Debounce
                speak(text_to_speak)
                last_spoken = text_to_speak

        # Optional: Display on screen if you want
        # cv2.imshow("Dual Inference", annotated2)
        # if cv2.waitKey(1) & 0xFF == ord('q'):
        #     break

    cap.release()
    cv2.destroyAllWindows()
    print("👋 Program ended.")


if __name__ == "__main__":
    main()
