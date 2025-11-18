#!/usr/bin/env bash

# ---------- SETTINGS ----------
DEV="/dev/video8"                    # <-- change if your camera node differs
IMG="/tmp/traffic_live.jpg"
MODEL="models/traffic_v3/model.synap"
SLEEP=1                              # seconds between iterations
# --------------------------------

# Helper: build a snapshot pipeline for this camera
build_snap_pipeline() {
  # Does the camera advertise MJPG?
  if v4l2-ctl --list-formats-ext -d "$DEV" 2>/dev/null | grep -q MJPG; then
    # Do we actually have jpegparse? If not, write MJPEG directly.
    if gst-inspect-1.0 jpegparse >/dev/null 2>&1; then
      SNAP="gst-launch-1.0 -q -e \
        v4l2src device=$DEV num-buffers=1 ! \
        image/jpeg,width=640,height=480,framerate=30/1 ! \
        jpegparse ! filesink location=$IMG"
    else
      SNAP="gst-launch-1.0 -q -e \
        v4l2src device=$DEV num-buffers=1 ! \
        image/jpeg,width=640,height=480,framerate=30/1 ! \
        filesink location=$IMG"
    fi
  else
    # RAW → JPEG (works on any V4L2 device that outputs raw)
    SNAP="gst-launch-1.0 -q -e \
      v4l2src device=$DEV num-buffers=1 ! \
      video/x-raw,format=YUY2,width=640,height=480,framerate=30/1 ! \
      videoconvert ! jpegenc quality=85 ! \
      filesink location=$IMG"
  fi
}

build_snap_pipeline

while true; do
  echo "📸 Capturing..."
  rm -f "$IMG"

  # Take snapshot
  if ! eval "$SNAP" >/dev/null 2>&1; then
    echo "STATE:NO_DET"
    echo "⚠️ Snapshot pipeline failed"
    sleep "$SLEEP"
    continue
  fi

  # Ensure the file exists and is non-zero size
  if [ ! -s "$IMG" ]; then
    echo "STATE:NO_DET"
    echo "⚠️ Snapshot invalid (empty file)"
    sleep "$SLEEP"
    continue
  fi

  echo "🧠 Running traffic model..."
  raw_output=$(synap_cli_od -m "$MODEL" "$IMG")

  # Show tool output (handy while debugging)
  echo "$raw_output"
  echo

  # Extract first class_index
  class=$(printf '%s\n' "$raw_output" \
            | sed -n 's/.*"class_index":[[:space:]]*\([0-9]\+\).*/\1/p' \
            | head -n1)

  if [ -z "$class" ]; then
    echo "STATE:NO_DET"
    echo "🚦 Traffic light: NO DETECTION"
  else
    case "$class" in
      0) color="GREEN";  token="CROSS" ;;
      1) color="RED";    token="STOP"  ;;
      2) color="YELLOW"; token="WAIT"  ;;
      *) color="UNKNOWN"; token="UNKNOWN" ;;
    esac
    echo "STATE:$token"
    echo "🚦 Traffic light: $color  (class = $class)"
  fi

  echo "----------------------------------------"
  sleep "$SLEEP"
done

