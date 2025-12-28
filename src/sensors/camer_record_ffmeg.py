#!/usr/bin/env python3
"""
QuickTime-compatible recorder for Synaptics Astra SL1680.
Records 10-second MP4 clips and remuxes them with ffmpeg (from pip package) for compatibility.
"""

import os
import time
import subprocess
from datetime import datetime
import imageio_ffmpeg

VIDEO_DIR = "videos"
DEVICE = "/dev/video8"      # confirmed working camera
DURATION = 10               # seconds per clip
INTERVAL = 2                # delay before next recording

def record_clip(filename: str):
    """Record one MP4 clip with GStreamer."""
    cmd = [
        "gst-launch-1.0",
        "v4l2src", f"device={DEVICE}", "!",
        "image/jpeg,framerate=30/1", "!", "jpegdec", "!", "videoconvert", "!",
        "x264enc", "tune=zerolatency", "bitrate=1000", "speed-preset=ultrafast", "!",
        "mp4mux", "!", "filesink", f"location={filename}"
    ]

    print(f"🎬 Recording {filename} for {DURATION}s ...")
    try:
        subprocess.run(cmd, check=True, timeout=DURATION,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"✅  Saved raw clip: {filename}")
    except subprocess.TimeoutExpired:
        print(f"✅  Clip finished (timeout): {filename}")
    except subprocess.CalledProcessError as e:
        print(f"❌  GStreamer error: {e}")

def remux_with_ffmpeg(infile: str):
    """Use ffmpeg (from imageio_ffmpeg) to fix MP4 container for QuickTime compatibility."""
    fixed = infile.replace(".mp4", "_fixed.mp4")
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()

    cmd = [ffmpeg_path, "-y", "-i", infile, "-c", "copy", fixed]
    try:
        subprocess.run(cmd, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"🎞️  Re-muxed for QuickTime: {fixed}")
        # Optionally remove raw file to save space
        os.remove(infile)
    except subprocess.CalledProcessError:
        print("⚠️  ffmpeg remux failed — keeping original clip.")

def main():
    os.makedirs(VIDEO_DIR, exist_ok=True)
    print(f"🎥 Recording continuously from {DEVICE} (Ctrl+C to stop)\n")

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
