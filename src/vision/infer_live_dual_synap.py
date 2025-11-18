#!/usr/bin/env python3
"""
Real-time Dual Synap Inference on Live Camera (/dev/video8)
------------------------------------------------------------
• Captures frames from Astra SL1680 camera (MJPEG or YUYV)
• Runs two .synap models sequentially on each frame
• Annotates detections with bounding boxes and labels
• Saves periodic frames or outputs a live stream
"""

import cv2
import json
import time
from pathlib import Path
from synap import Network
from synap.preprocessor import Preprocessor
from synap.postprocessor import Detector


def load_model(model_path, labels_path):
    """Load a Synap model and its labels."""
    model_file = Path(model_path)
    net = Network(model_file)
    pre = Preprocessor()
    det = Detector(0.5, 0, True, 0.5, False)
    with open(labels_path, "r") as f:
        labels = json.load(f)["labels"]
    return net, pre, det, labels


# def run_model(net, pre, det, frame, labels):
#     """Run inference on one frame and return annotated image."""
#     tmp = "/tmp/frame.jpg"
#     cv2.imwrite(tmp, frame)
#     rect = pre.assign(net.inputs, tmp)
#     outputs = net.predict()
#     result = det.process(outputs, rect)
#     print(result)

#     for item in result.items:
#         bb = item.bounding_box
#         x, y = int(bb.origin.x), int(bb.origin.y)
#         w, h = int(bb.size.x), int(bb.size.y)
#         label = labels[item.class_index] if labels and item.class_index < len(labels) else f"class_{item.class_index}"
#         conf = item.confidence
#         cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
#         cv2.putText(frame, f"{label} ({conf:.2f})", (x, max(y - 10, 20)),
#                     cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
#     return frame

def run_model(net, pre, det, frame, labels):
    """Run inference on one frame and return annotated image."""
    tmp = "/tmp/frame.jpg"
    cv2.imwrite(tmp, frame)
    rect = pre.assign(net.inputs, tmp)
    outputs = net.predict()
    result = det.process(outputs, rect)

    # 🧾 PRINT readable results
    if len(result.items) == 0:
        print("No detections.")
    else:
        print("\n🔍 Detections:")
        for i, item in enumerate(result.items):
            bb = item.bounding_box
            label = labels[item.class_index] if labels and item.class_index < len(labels) else f"class_{item.class_index}"
            print(f"  #{i}: {label:<12} | conf={item.confidence:.2f} | "
                  f"pos=({int(bb.origin.x)}, {int(bb.origin.y)}) | size=({int(bb.size.x)}, {int(bb.size.y)})")

    # 🟩 Draw bounding boxes on frame
    for item in result.items:
        bb = item.bounding_box
        x, y = int(bb.origin.x), int(bb.origin.y)
        w, h = int(bb.size.x), int(bb.size.y)
        label = labels[item.class_index] if labels and item.class_index < len(labels) else f"class_{item.class_index}"
        conf = item.confidence
        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
        cv2.putText(frame, f"{label} ({conf:.2f})", (x, max(y - 10, 20)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    return frame


def main():
    cam_path = "/dev/video8"
    print(f"🎥 Opening camera: {cam_path}")

    cap = cv2.VideoCapture(cam_path)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 30)

    if not cap.isOpened():
        print("❌ Failed to open camera. Check device node.")
        return

    print("✅ Camera opened successfully — starting inference...\n")

    # Load both models
    net1, pre1, det1, labels1 = load_model(
        "models/traffic_v3/model.synap", "models/traffic_v3/traffic_labels.json"
    )
    net2, pre2, det2, labels2 = load_model(
        "models/walksign_v6/model.synap", "models/walksign_v6/traffic_labels.json"
    )

    frame_id = 0
    save_dir = Path("live_results")
    save_dir.mkdir(exist_ok=True)

    start = time.time()
    while True:
        ret, frame = cap.read()
        if not ret:
            print("⚠️  Frame capture failed.")
            continue

        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)  # ensure correct color order

        # Run model 1 → then model 2
        annotated = run_model(net1, pre1, det1, frame, labels1)
        annotated = run_model(net2, pre2, det2, annotated, labels2)

        frame_id += 1

        # Save every Nth frame
        if frame_id % 30 == 0:
            out_path = save_dir / f"frame_{frame_id:05d}.jpg"
            cv2.imwrite(str(out_path), annotated)
            print(f"🖼️  Saved annotated frame {frame_id} → {out_path}")

        # Print simple FPS info
        if frame_id % 10 == 0:
            fps = frame_id / (time.time() - start)
            print(f"⏱️  FPS: {fps:.2f}")

    cap.release()


if __name__ == "__main__":
    main()
