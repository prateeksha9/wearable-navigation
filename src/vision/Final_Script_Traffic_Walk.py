#!/usr/bin/env python3
"""
Three-model Synap inference: traffic_v3 + walksign_v6 + surroundings_v2

Models:
- traffic_v3 labels:   ["Green", "Red", "Yellow"]
- walksign_v6 labels:  ["Crosswalk", "No_Walk", "Walk"]
- surroundings_v2 labels (assumed):
    ["vehicles","bike","e-scooter","person","stairs","walls","tree"]

Behaviour:
- Runs ALL THREE models every frame on /dev/video9
- Per-model mapping + filtering:
    * traffic_v3: green / red / yellow (MIN_TRAFFIC_SCORE)
    * walksign_v6: walk / no_walk / crosswalk (MIN_WALKSIGN_SCORE)
    * surroundings_v2: ONLY bike / e-scooter / person / vehicle
      (stairs / tree / walls ignored)
    * vehicles class has an extra confidence gate to avoid random “vehicle ahead”
- Temporal smoothing with MajorityLabel:
    * window=6
    * need at least 3 hits AND 50% of non-"none" frames
- TTS over TCP to laptop (port 5005)
- For each stable phrase, TTS speaks it at most TWICE.
  It only speaks again when the stable phrase CHANGES.
- NO FORCED GUESSING: if nothing stable, no phrase is spoken.
"""

import cv2
import json
import socket
import time
from pathlib import Path
from collections import deque

# =========================
# TCP / TTS CONFIG
# =========================
LAPTOP_IP = "10.101.61.182"   # update to your laptop IP as needed
LAPTOP_PORT = 5005

TTS_MIN_INTERVAL = 2.0        # minimum time between ANY two TTS messages
PHRASE_REPEAT_INTERVAL = 8.0  # (unused now, but kept for reference)


def send_to_laptop(text: str):
    """Send a short text message to laptop over TCP."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2.0)
        s.connect((LAPTOP_IP, LAPTOP_PORT))
        # No newline; listener uses ReadToEnd()
        s.sendall(text.encode("utf-8"))
        s.close()
        print(f"[TTS] {text}")
    except Exception as e:
        print(f"[TTS ERROR] {e}")


# =========================
# Synap imports
# =========================
from synap import Network
from synap.preprocessor import Preprocessor
from synap.postprocessor import Detector

# =========================
# PATHS / CONFIG
# =========================
CAMERA_DEV = "/dev/video8"

# Detector threshold – keep it low, we’ll filter with our own thresholds
SCORE_THR = 0.1

THIS_FILE = Path(__file__).resolve()
PROJECT_ROOT = THIS_FILE.parents[2]

# One temp image path reused by all models (sequential per frame)
TMP_IMAGE_PATH = "/tmp/frame_synap_combo.jpg"

# Delay between frames for behaviour
FRAME_DELAY = 0.3  # ~3+ updates per second

# Models:
MODELS = {
    "traffic": {
        "model_path": PROJECT_ROOT / "models/traffic_v3/model.synap",
        "label_path": PROJECT_ROOT / "models/traffic_v3/traffic_labels.json",
    },
    "walksign": {
        "model_path": PROJECT_ROOT / "models/walksign_v6/model.synap",
        "label_path": PROJECT_ROOT / "models/walksign_v6/walksign_labels.json",
    },
    "surroundings": {
        "model_path": PROJECT_ROOT / "models/surroundings_v2/model.synap",
        "label_path": PROJECT_ROOT / "models/surroundings_v2/surroundings_labels.json",
    },
}

# =========================
# UTILITY CLASSES
# =========================
class SynapModel:
    def __init__(self, name: str, model_path: Path, label_path: Path):
        self.name = name
        self.model_path = model_path
        self.label_path = label_path

        with open(label_path, "r") as f:
            data = json.load(f)
        self.labels = data["labels"]

        self.net = Network(model_path)
        self.pre = Preprocessor()
        self.det = Detector(SCORE_THR, 0, True, 0.5, False)

        print(f"[LOAD] {name}: {model_path.name}, labels={self.labels}")

    def infer(self, frame) -> list:
        """
        Run model on frame and return list of dicts:
          {"class_id","label","score","x","y","w","h"}
        """
        cv2.imwrite(TMP_IMAGE_PATH, frame)
        rect = self.pre.assign(self.net.inputs, TMP_IMAGE_PATH)
        outputs = self.net.predict()
        result = self.det.process(outputs, rect)

        dets = []
        for item in result.items:
            class_id = item.class_index
            score = getattr(item, "score", getattr(item, "confidence", None))
            bb = item.bounding_box
            x = int(bb.origin.x)
            y = int(bb.origin.y)
            w = int(bb.size.x)
            h = int(bb.size.y)
            label = (
                self.labels[class_id] if class_id < len(self.labels) else f"class_{class_id}"
            )
            dets.append(
                {
                    "class_id": class_id,
                    "label": label,
                    "score": float(score) if score is not None else 0.0,
                    "x": x,
                    "y": y,
                    "w": w,
                    "h": h,
                }
            )
        return dets


class MajorityLabel:
    """
    Frame-buffer style temporal smoothing:

    - Maintains a history window of the last N labels (e.g., 6 frames).
    - majority_with_count(min_count, min_frac) returns (label, count) where:
        * label appears at least `min_count` times, and
        * covers at least `min_frac` fraction of the NON-"none" entries.
    - "none" entries are:
        * stored in the history (so we still know gaps)
        * ignored when computing label counts and fraction.
    """

    def __init__(self, window=6):
        self.hist = deque(maxlen=window)

    def update(self, label: str | None):
        # Store "none" for empty / no detection cases
        self.hist.append(label or "none")

    def majority_with_count(self, min_count=3, min_frac=0.5) -> tuple[str | None, int]:
        """
        Return (best_label, best_count) or (None, 0) if no stable label.
        """
        if not self.hist:
            return None, 0

        counts = {}
        non_none_total = 0

        for lab in self.hist:
            if lab == "none":
                continue
            counts[lab] = counts.get(lab, 0) + 1
            non_none_total += 1

        # If we only saw "none" in the window
        if non_none_total == 0 or not counts:
            return None, 0

        best_label, best_count = max(counts.items(), key=lambda kv: kv[1])

        # 1) need at least min_count detections
        if best_count < min_count:
            return None, 0

        # 2) fraction is over NON-"none" entries only
        if best_count < min_frac * non_none_total:
            return None, 0

        return best_label, best_count

    def majority(self, min_count=3, min_frac=0.5) -> str | None:
        label, _ = self.majority_with_count(min_count=min_count, min_frac=min_frac)
        return label


# =========================
# MODEL-SPECIFIC LOGIC
# =========================

MIN_TRAFFIC_SCORE = 0.50   # only trust traffic light if conf >= 0.5
MIN_WALKSIGN_SCORE = 0.50  # only trust walk sign if conf >= 0.5
MIN_SURR_SCORE = 0.50      # only trust surroundings detection if conf >= 0.5

# STRONGER gate for vehicles to avoid random “vehicle ahead”
MIN_VEHICLE_SCORE = 0.95   # was 0.90; now more strict
VEHICLE_MIN_WIDTH = 80     # ignore tiny vehicle boxes
VEHICLE_MIN_HEIGHT = 60
VEHICLE_MIN_AREA = 8000    # w*h must exceed this
VEHICLE_MIN_HISTORY_COUNT = 4  # out of 6-history window, need >=4 frames

# Surroundings: keep only these labels (lowercase)
VALID_SURR_LABELS = {
    "bike",
    "e-scooter",
    "e_scooter",   # in case of underscore naming
    "person",
    "vehicles",
    "vehicle",     # in case it's singular
}
# stairs / tree / walls are implicitly ignored


def best_label(dets):
    """Return (label, score) of best detection, or (None, 0.0)."""
    if not dets:
        return None, 0.0
    best = max(dets, key=lambda d: d["score"])
    return best["label"], best["score"]


def map_traffic(dets) -> str | None:
    """
    Choose traffic light color:
    - look at best detection
    - only accept if label is Green/Red/Yellow and score high enough
    """
    label, score = best_label(dets)
    if label is None:
        return None

    l = label.lower()
    if score < MIN_TRAFFIC_SCORE:
        return None

    if l == "green":
        return "green"
    if l == "red":
        return "red"
    if l == "yellow":
        return "yellow"
    return None


def map_walksign(dets) -> str | None:
    """
    Choose walk sign state:
    - walksign_labels.json: ["Crosswalk", "No_Walk", "Walk"]
    - only accept if score high enough
    """
    label, score = best_label(dets)
    if label is None:
        return None

    if score < MIN_WALKSIGN_SCORE:
        return None

    l = label.lower()
    if "walk" in l and "no" in l:
        return "no_walk"
    if l == "walk":
        return "walk"
    if "cross" in l:
        return "crosswalk"
    return None


def map_surroundings(dets) -> str | None:
    """
    Choose surroundings state:
    - Consider only valid classes: bike, e-scooter, person, vehicles
    - Ignore stairs, tree, walls, etc.
    - Return canonical labels: "bike","e-scooter","person","vehicle"
    - EXTRA: vehicles/vehicle requires higher confidence + size gate.
    """
    best_label_local = None
    best_score = 0.0

    for d in dets:
        label = d["label"].lower()
        score = d["score"]

        if label not in VALID_SURR_LABELS:
            continue

        # Stronger gate for vehicle class to reduce random triggers
        if label in ("vehicles", "vehicle"):
            if score < MIN_VEHICLE_SCORE:
                continue

            # Geometric gate – avoid tiny / noisy boxes
            w = d["w"]
            h = d["h"]
            area = w * h

            if w < VEHICLE_MIN_WIDTH or h < VEHICLE_MIN_HEIGHT:
                continue
            if area < VEHICLE_MIN_AREA:
                continue
        else:
            # Non-vehicle classes use normal surroundings score gate
            if score < MIN_SURR_SCORE:
                continue

        if score > best_score:
            best_score = score
            best_label_local = label

    if best_label_local is None:
        return None

    # Canonicalize label
    if best_label_local in ("vehicles", "vehicle"):
        return "vehicle"
    if best_label_local in ("e-scooter", "e_scooter"):
        return "e-scooter"
    if best_label_local == "bike":
        return "bike"
    if best_label_local == "person":
        return "person"

    # Fallback (shouldn't happen often)
    return best_label_local


def _phrase_for_walk(walk: str | None) -> str | None:
    if walk == "no_walk":
        return "Do not walk"
    if walk == "walk":
        return "Walk signal on"
    if walk == "crosswalk":
        return "Crosswalk ahead"
    return None


def _phrase_for_traffic(traf: str | None) -> str | None:
    if traf == "red":
        return "Traffic light red"
    if traf == "green":
        return "Traffic light green"
    if traf == "yellow":
        return "Traffic light yellow"
    return None


def phrase_for_surroundings(label: str | None) -> str | None:
    """Map canonical surroundings label -> TTS sentence."""
    if label == "vehicle":
        return "Vehicle ahead"
    if label == "bike":
        return "Bike ahead"
    if label == "e-scooter":
        return "E-scooter ahead"
    if label == "person":
        return "Person ahead"
    return None


def compose_signal_phrase(
    traf: str | None,
    walk: str | None,
    traf_count: int = 0,
    walk_count: int = 0,
) -> str | None:
    """
    Build a user-facing message for TRAFFIC + WALK ONLY.

    Rules:
      - If only one of traf/walk is present -> use that.
      - If BOTH present -> choose the one with HIGHER history count.
            * If tie -> prefer walk (original priority).
    """

    # Both present: choose by count
    if traf and walk:
        if walk_count > traf_count:
            phrase = _phrase_for_walk(walk)
            if phrase:
                return phrase
            # fallback if weird label
            return _phrase_for_traffic(traf)

        if traf_count > walk_count:
            phrase = _phrase_for_traffic(traf)
            if phrase:
                return phrase
            # fallback
            return _phrase_for_walk(walk)

        # Tie: keep original priority (walk first, then traffic)
        phrase = _phrase_for_walk(walk)
        if phrase:
            return phrase
        return _phrase_for_traffic(traf)

    # Only walk present
    if walk:
        return _phrase_for_walk(walk)

    # Only traffic present
    if traf:
        return _phrase_for_traffic(traf)

    # Nothing stable
    return None


# =========================
# MAIN
# =========================
def main():
    print("Loading models...")
    traffic_model = SynapModel(
        "traffic",
        MODELS["traffic"]["model_path"],
        MODELS["traffic"]["label_path"],
    )
    walk_model = SynapModel(
        "walksign",
        MODELS["walksign"]["model_path"],
        MODELS["walksign"]["label_path"],
    )
    surroundings_model = SynapModel(
        "surroundings",
        MODELS["surroundings"]["model_path"],
        MODELS["surroundings"]["label_path"],
    )
    print("All three models loaded.\n")

    cap = cv2.VideoCapture(CAMERA_DEV)
    if not cap.isOpened():
        print("ERROR: cannot open camera", CAMERA_DEV)
        return
    print(f"Camera {CAMERA_DEV} opened. Ctrl+C to stop.\n")

    # History buffers (frame-based majority voting)
    traffic_hist = MajorityLabel(window=6)
    walk_hist = MajorityLabel(window=6)
    surr_hist = MajorityLabel(window=6)

    last_tts_time = 0.0
    frame_idx = 0

    # Phrase tracking:
    # - current_phrase: the currently stable phrase (string or None)
    # - current_phrase_speak_count: how many times we've spoken this phrase (0..2)
    current_phrase = None
    current_phrase_speak_count = 0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("ERROR reading frame")
                break
            frame_idx += 1

            # 1) Run ALL THREE models every frame
            traf_dets = traffic_model.infer(frame)
            walk_dets = walk_model.infer(frame)
            surr_dets = surroundings_model.infer(frame)

            # 2) Map raw detections to canonical labels (or None)
            traf_raw = map_traffic(traf_dets)
            walk_raw = map_walksign(walk_dets)
            surr_raw = map_surroundings(surr_dets)

            # 3) Update history buffers
            traffic_hist.update(traf_raw)
            walk_hist.update(walk_raw)
            surr_hist.update(surr_raw)

            # 4) Majority over last N frames (with counts)
            traf_major, traf_count = traffic_hist.majority_with_count(
                min_count=3, min_frac=0.5
            )
            walk_major, walk_count = walk_hist.majority_with_count(
                min_count=3, min_frac=0.5
            )
            surr_major, surr_count = surr_hist.majority_with_count(
                min_count=3, min_frac=0.5
            )

            # Extra strict gate for 'vehicle': needs stronger temporal consensus
            if surr_major == "vehicle" and surr_count < VEHICLE_MIN_HISTORY_COUNT:
                surr_major = None
                surr_count = 0

            print(
                f"[frame {frame_idx}] "
                f"traf_raw={traf_raw or 'none'} (major={traf_major or 'none'}; count={traf_count}), "
                f"walk_raw={walk_raw or 'none'} (major={walk_major or 'none'}; count={walk_count}), "
                f"surr_raw={surr_raw or 'none'} (major={surr_major or 'none'}; count={surr_count})"
            )

            # 5) Build phrases:
            #    - First, traffic + walk combined
            #    - If none, fall back to surroundings
            signal_phrase = compose_signal_phrase(
                traf_major, walk_major, traf_count, walk_count
            )
            surr_phrase = phrase_for_surroundings(surr_major)

            if signal_phrase is not None:
                phrase = signal_phrase
            else:
                phrase = surr_phrase  # may still be None

            now = time.time()

            # 6) TTS: speak each stable phrase at most TWO times,
            #    then stay silent until the phrase CHANGES to a different phrase.
            if phrase is not None:
                if phrase != current_phrase:
                    # New stable phrase detected -> reset counter
                    current_phrase = phrase
                    current_phrase_speak_count = 0

                if (
                    current_phrase_speak_count < 2
                    and (now - last_tts_time) >= TTS_MIN_INTERVAL
                ):
                    send_to_laptop(current_phrase)
                    last_tts_time = now
                    current_phrase_speak_count += 1

            # NOTE:
            # If phrase is None, we do NOT reset current_phrase or its count.
            # This prevents the same phrase from being re-spoken after short gaps
            # in detection (e.g., intermittent frames with no stable label).

            # 7) Slow down loop a bit
            time.sleep(FRAME_DELAY)

    except KeyboardInterrupt:
        print("\nStopped by user.")
    finally:
        cap.release()
        print("Camera released. Exiting.")
        try:
            send_to_laptop("STOP")
        except Exception:
            pass


if __name__ == "__main__":
    main()
