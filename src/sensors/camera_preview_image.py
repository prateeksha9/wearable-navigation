#!/usr/bin/env python3
"""
Pure-GStreamer fallback for Synaptics Astra SL1680.
Captures a JPEG frame every few seconds using the working gst-launch pipeline.
"""

import os
import time
import subprocess
from datetime import datetime

CAPTURE_DIR = "captures"
DEVICE = "/dev/video8"        # confirmed working camera node
INTERVAL = 5                  # seconds between frames

def capture_frame(filename: str):
    """Run the gst-launch command once to capture a single frame."""
    cmd = [
        "gst-launch-1.0",
        "v4l2src", f"device={DEVICE}",
        "num-buffers=1",
        "!", "jpegenc",
        "!", "filesink", f"location={filename}"
    ]
    try:
        subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        print(f"✅  Saved: {filename}")
    except subprocess.CalledProcessError as e:
        print(f"❌  GStreamer failed: {e}")

def main():
    os.makedirs(CAPTURE_DIR, exist_ok=True)
    print(f"📸  Starting snapshot capture from {DEVICE}  (Ctrl+C to stop)\n")

    count = 0
    try:
        while True:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(CAPTURE_DIR, f"frame_{count:03d}_{timestamp}.jpg")
            capture_frame(filename)
            count += 1
            time.sleep(INTERVAL)
    except KeyboardInterrupt:
        print("\n🛑  Capture stopped by user.")

if __name__ == "__main__":
    main()
