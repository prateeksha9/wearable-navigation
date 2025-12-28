#!/usr/bin/env python3
"""
Synaptics SL1680 – three-model benchmark with:
 - per-frame latency
 - per-model latency
 - CPU / ADC temperature logs
 - OPTIONAL: CSV dump
 - OVERLAY: per-object bounding boxes + per-model HUD
"""

import cv2
import time
import argparse
from pathlib import Path

from synap import Network
from synap.preprocessor import Preprocessor
from synap.postprocessor import Detector


# ---------------------------------------------------------
# Temperature helpers
# ---------------------------------------------------------

def read_cpu_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            return int(f.read().strip()) / 1000.0
    except Exception:
        return None


def read_adc_temp():
    # second thermal sensor, may represent NPU, PMIC or board temp
    try:
        with open("/sys/class/thermal/thermal_zone1/temp", "r") as f:
            return int(f.read().strip()) / 1000.0
    except Exception:
        return None


# ---------------------------------------------------------
# SynapModel wrapper
# ---------------------------------------------------------

class SynapModel:
    def __init__(self, name, model_path, label_path, color):
        self.name = name
        self.color = color

        import json
        with open(label_path, "r") as f:
            self.labels = json.load(f)["labels"]

        self.net = Network(model_path)
        self.pre = Preprocessor()
        # Detector(threshold, maxDet, useNMS, iou, isTiny)
        self.det = Detector(0.05, 200, True, 0.45, False)

        print(f"[LOAD] {name}: {model_path.name}")

    def infer(self, frame, debug=False, frame_idx=0, model_tag=""):
        """
        Run Synap detector on an OpenCV BGR frame.
        Returns list of dicts: {label, score, x, y, w, h}
        Coords are converted to IMAGE PIXELS (not 0–1).
        """
        h_frame, w_frame = frame.shape[:2]

        # Write frame to disk for the Synap Preprocessor
        tmp = "/tmp/frame_synap.jpg"
        cv2.imwrite(tmp, frame)

        # Use ORIGINAL signature that works: inputs (Tensors) + filename
        rect = self.pre.assign(self.net.inputs, tmp)

        # Predict on NPU (keep original usage – returns outputs in this API)
        outputs = self.net.predict()

        # Post-process detections with rect
        result = self.det.process(outputs, rect)

        dets = []
        for item in result.items:
            bb = item.bounding_box
            conf = getattr(item, "score", getattr(item, "confidence", 0.0))

            # Raw values from Detector
            x = float(bb.origin.x)
            y = float(bb.origin.y)
            w = float(bb.size.x)
            h = float(bb.size.y)

            # --- IMPORTANT PART ---
            # If everything is tiny (<= 1.5), treat as NORMALIZED [0,1]
            # and scale to image pixels.
            if (
                0.0 <= x <= 1.5 and
                0.0 <= y <= 1.5 and
                0.0 <= w <= 1.5 and
                0.0 <= h <= 1.5
            ):
                x *= w_frame
                w *= w_frame
                y *= h_frame
                h *= h_frame

            # Convert to ints and clamp to frame bounds
            x = max(0, min(int(round(x)), w_frame - 1))
            y = max(0, min(int(round(y)), h_frame - 1))
            w = max(1, min(int(round(w)), w_frame - x))
            h = max(1, min(int(round(h)), h_frame - y))

            det = {
                "label": self.labels[item.class_index],
                "score": float(conf),
                "x": x,
                "y": y,
                "w": w,
                "h": h,
            }
            dets.append(det)

        # Small debug print for first few frames so we can see coords
        if debug and frame_idx < 5 and dets:
            first = dets[0]
            print(
                f"[DEBUG bbox] {model_tag} frame {frame_idx}: "
                f"x={first['x']} y={first['y']} w={first['w']} h={first['h']} "
                f"label={first['label']} score={first['score']:.2f}"
            )

        return dets


# ---------------------------------------------------------
# Drawing: per-object boxes
# ---------------------------------------------------------

def draw_boxes(frame, dets, color, prefix):
    """
    Draw a bounding box + label for every detection in `dets`.
    """
    font = cv2.FONT_HERSHEY_SIMPLEX

    for d in dets:
        x, y, w, h = d["x"], d["y"], d["w"], d["h"]
        label = d["label"]
        score = d["score"]

        # Ignore obviously degenerate boxes
        if w <= 2 or h <= 2:
            continue

        h_img, w_img = frame.shape[:2]
        x = max(0, min(x, w_img - 1))
        y = max(0, min(y, h_img - 1))
        w = max(2, min(w, w_img - x))
        h = max(2, min(h, h_img - y))

        # Bounding box
        cv2.rectangle(frame, (x, y), (x + w, y + h), color, 3)

        # Label text just above the box
        txt = f"{prefix}: {label} {score:.2f}"
        (tw, th), baseline = cv2.getTextSize(txt, font, 0.7, 2)

        text_x = x
        text_y = max(th + 4, y - 4)

        # Background for readability
        cv2.rectangle(
            frame,
            (text_x - 3, text_y - th - baseline),
            (text_x + tw + 3, text_y + baseline),
            color,
            thickness=-1,
        )
        cv2.putText(
            frame,
            txt,
            (text_x, text_y),
            font,
            0.7,
            (0, 0, 0),
            2,
            cv2.LINE_AA,
        )


# ---------------------------------------------------------
# Drawing: per-model summary HUD
# ---------------------------------------------------------

def draw_summary_hud(frame, summaries):
    """
    summaries: list of (tag, label, score, color)
    Draws one line per model at top-left of the frame with padding and spacing.
    """
    font = cv2.FONT_HERSHEY_SIMPLEX
    x0, y0 = 15, 40
    dy = 45  # vertical spacing between lines

    # Remove duplicate (tag, label) combos
    uniq = []
    seen = set()
    for tag, label, score, color in summaries:
        key = (tag, label)
        if key in seen:
            continue
        seen.add(key)
        uniq.append((tag, label, score, color))

    for i, (tag, label, score, color) in enumerate(uniq):
        txt = f"{tag}: {label} {score:.2f}"
        y = y0 + i * dy

        (tw, th), baseline = cv2.getTextSize(txt, font, 1.1, 3)

        cv2.rectangle(
            frame,
            (x0 - 8, y - th - baseline - 4),
            (x0 + tw + 8, y + baseline + 4),
            color,
            thickness=-1,
        )
        cv2.putText(
            frame,
            txt,
            (x0, y),
            font,
            1.1,
            (0, 0, 0),
            3,
            cv2.LINE_AA,
        )


# ---------------------------------------------------------
# Main benchmark
# ---------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", type=str, required=True)
    parser.add_argument("--frames", type=int, default=300)
    parser.add_argument("--save-video", action="store_true")
    parser.add_argument("--dump", type=str, default=None)
    args = parser.parse_args()

    SCRIPT = Path(__file__).resolve()
    ROOT = SCRIPT.parents[2]   # wearable-navigation project root

    MODELS = {
        "surroundings": {
            "model": ROOT / "models/surroundings_v2/model.synap",
            "labels": ROOT / "models/surroundings_v2/surroundings_labels.json",
            "color": (0, 255, 0),
            "tag": "S",
        },
        "traffic": {
            "model": ROOT / "models/traffic_v3/model.synap",
            "labels": ROOT / "models/traffic_v3/traffic_labels.json",
            "color": (0, 0, 255),
            "tag": "T",
        },
        "walksign": {
            "model": ROOT / "models/walksign_v6/model.synap",
            "labels": ROOT / "models/walksign_v6/walksign_labels.json",
            "color": (255, 200, 0),
            "tag": "W",
        },
    }

    print("\nLoading Synap models...")
    models = {}
    cold_t0 = time.time()

    for key, cfg in MODELS.items():
        models[key] = {
            "model": SynapModel(key, cfg["model"], cfg["labels"], cfg["color"]),
            "color": cfg["color"],
            "tag": cfg["tag"],
        }

    cold_start = time.time() - cold_t0
    print(f"\nCold start load time: {cold_start:.3f} sec\n")

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        raise RuntimeError(f"Unable to open video: {args.video}")

    fps_in = cap.get(cv2.CAP_PROP_FPS) or 20.0
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"Input video: {W}x{H} @ {fps_in:.2f} fps")

    if args.save_video:
        out = cv2.VideoWriter(
            "synap_benchmark_output.mp4",
            cv2.VideoWriter_fourcc(*"mp4v"),
            fps_in,
            (W, H),
        )
        print("Will save output as synap_benchmark_output.mp4")
    else:
        out = None

    per_frame_lat = []
    per_model_lat = {k: [] for k in models.keys()}

    cpu_temp_log = []
    adc_temp_log = []

    print("Running benchmark...")
    t0 = time.time()
    frame_idx = 0

    while frame_idx < args.frames:
        ret, frame = cap.read()
        if not ret:
            break

        t_frame_start = time.time()

        hud_summaries = []

        for key, pack in models.items():
            m = pack["model"]

            t1 = time.time()
            dets = m.infer(
                frame,
                debug=True,          # print first few bboxes
                frame_idx=frame_idx,
                model_tag=pack["tag"],
            )
            t2 = time.time()
            per_model_lat[key].append(t2 - t1)

            # draw all boxes for this model
            draw_boxes(frame, dets, pack["color"], pack["tag"])

            if dets:
                best = max(dets, key=lambda d: d["score"])
                hud_summaries.append(
                    (pack["tag"], best["label"], best["score"], pack["color"])
                )

        # draw top-left HUD
        if hud_summaries:
            draw_summary_hud(frame, hud_summaries)

        t_frame_end = time.time()
        per_frame_lat.append(t_frame_end - t_frame_start)

        cpu_temp_log.append(read_cpu_temp())
        adc_temp_log.append(read_adc_temp())

        if out:
            out.write(frame)

        if frame_idx % 50 == 0:
            print(f"Processed {frame_idx} frames", end="\r")

        frame_idx += 1

    cap.release()
    if out:
        out.release()

    total_time = time.time() - t0
    fps_final = frame_idx / total_time if frame_idx > 0 else 0.0
    avg_lat = sum(per_frame_lat) / len(per_frame_lat) if per_frame_lat else 0.0
    p95_lat = (
        sorted(per_frame_lat)[int(0.95 * len(per_frame_lat))]
        if per_frame_lat
        else 0.0
    )

    # ---------------------------------------------------------
    # Dump logs
    # ---------------------------------------------------------

    if args.dump:
        dump_path = Path(args.dump)
        with open(dump_path, "w") as f:
            f.write("frame,latency_ms,cpu_temp_c,adc_temp_c\n")
            for i, lat in enumerate(per_frame_lat):
                f.write(
                    f"{i},{lat*1000:.3f},{cpu_temp_log[i]},{adc_temp_log[i]}\n"
                )
        print(f"\nSaved raw benchmark log to {dump_path}\n")

    print("\n==== RESULTS ====")
    print(f"Frames processed: {frame_idx}")
    print(f"FPS: {fps_final:.2f}")
    print(f"Avg latency: {avg_lat*1000:.2f} ms")
    print(f"P95 latency: {p95_lat*1000:.2f} ms\n")

    print("Per model avg latencies:")
    for key in per_model_lat:
        if per_model_lat[key]:
            ms = sum(per_model_lat[key]) / len(per_model_lat[key]) * 1000
        else:
            ms = 0.0
        print(f"{key}: {ms:.2f} ms")

    print("\nDone. If video saved: synap_benchmark_output.mp4\n")


if __name__ == "__main__":
    main()
