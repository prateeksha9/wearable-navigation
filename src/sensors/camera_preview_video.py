#!/usr/bin/env python3
"""
QuickTime-compatible recorder for Synaptics Astra SL1680.
Records 10-second MP4 clips with GStreamer and remuxes them using static-ffmpeg (pip package).
"""

import os
import time
import subprocess
from datetime import datetime
from static_ffmpeg import add_paths

# make the ffmpeg binary bundled in static_ffmpeg available on PATH
add_paths()

VIDEO_DIR = "videos"
DEVICE = "/dev/video8"      # confirmed working node
DURATION = 10               # seconds per clip
INTERVAL = 2                # delay before next clip starts (seconds)

def record_clip(filename: str):
    """Record one MP4 clip using gst-launch-1.0."""
    cmd = [
        "gst-launch-1.0",
        "v4l2src", f"device={DEVICE}", "!",
        "image/jpeg,framerate=30/1", "!", "jpegdec", "!", "videoconvert", "!",
        "x264enc", "tune=zerolatency", "bitrate=1000", "speed-preset=ultrafast", "!",
        "mp4mux", "faststart=true", "!", "filesink", f"location={filename}"
    ]

    print(f"🎬 Recording {filename} for {DURATION}s ...")
    try:
        subprocess.run(
            cmd,
            check=True,
            timeout=DURATION,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        print(f"✅  Saved: {filename}")
    except subprocess.TimeoutExpired:
        print(f"✅  Completed (timeout): {filename}")
    except subprocess.CalledProcessError as e:
        print(f"❌  GStreamer error: {e}")

def remux_with_ffmpeg(infile: str):
    """Remux MP4 for QuickTime compatibility using static-ffmpeg binary."""
    fixed = infile.replace(".mp4", "_fixed.mp4")
    cmd = ["ffmpeg", "-y", "-i", infile, "-c", "copy", fixed]
    try:
        subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        print(f"🎞️  Re-muxed for QuickTime: {fixed}")
        # optional: delete raw file to save space
        os.remove(infile)
    except subprocess.CalledProcessError:
        print("⚠️  ffmpeg remux failed — keeping original clip.")

def main():
    os.makedirs(VIDEO_DIR, exist_ok=True)
    print(f"🎥 Starting continuous recording from {DEVICE} (Ctrl+C to stop)\n")

    count = 0
    try:
        while True:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            raw_file = os.path.join(VIDEO_DIR, f"clip_{count:03d}_{timestamp}.mp4")
            record_clip(raw_file)
            remux_with_ffmpeg(raw_file)
            count += 1
            time.sleep(INTERVAL)
    except KeyboardInterrupt:
        print("\n🛑 Recording stopped by user.")

if __name__ == "__main__":
    main()
