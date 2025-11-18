#!/usr/bin/env python3

import cv2
import os
from synap import Network  # ensures Synap packages load correctly


LAPTOP_IP = "192.168.137.196"  # your laptop IP
CAMERA_DEVICE = "/dev/video8"   # Astra SL1680 camera


def speak(msg):
    """
    Send a text message to laptop speaker using nc.
    """
    os.system(f'echo "{msg}" | nc {LAPTOP_IP} 5005')
    print(f"[Board] Sent to laptop → {msg}")


def test_camera():
    """
    Try opening the Astra camera & capturing one frame.
    """
    print(f"🔍 Trying to open camera at {CAMERA_DEVICE}...")

    cap = cv2.VideoCapture(CAMERA_DEVICE)

    if not cap.isOpened():
        print("❌ Camera failed to open")
        speak("camera not connected")
        return

    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        print("❌ Could not read frame from camera")
        speak("camera not connected")
        return

    # Save frame for debug
    # save_path = "/tmp/camera_test.jpg"
    current_dir = os.path.dirname(os.path.abspath(__file__))
    save_path = os.path.join(current_dir, "camera_test.jpg")
    cv2.imwrite(save_path, frame)
    print(f"📸 Frame captured and saved → {save_path}")

    speak("picture clicked")


def main():
    print("=== SL1680 Camera Test using Synap Dependencies ===")
    test_camera()
    print("=== Test Completed ===")


if __name__ == "__main__":
    main()
