#!/usr/bin/env python3
"""
Synap Object Detection Inference for Image or Video Input
 - Works with .synap models
 - Reads labels from JSON (e.g., {"labels": ["Green", "Red", "Yellow"]})
 - Annotates frames with bounding boxes
 - Supports .jpg/.png and .mp4/.avi inputs
"""

import json
import sys
import time
from pathlib import Path
import cv2

from synap import Network
from synap.preprocessor import Preprocessor
from synap.postprocessor import Detector


def infer_frame(network, preprocessor, detector, frame, labels):
    """Run inference on one frame and return annotated image."""
    # Save temporary frame to disk for the preprocessor
    tmp_path = "/tmp/frame.jpg"
    cv2.imwrite(tmp_path, frame)

    assigned_rect = preprocessor.assign(network.inputs, tmp_path)
    outputs = network.predict()
    result = detector.process(outputs, assigned_rect)

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


def main(args):
    model_file = Path(args.model)
    if not model_file.exists():
        raise FileNotFoundError(f"Model not found: {model_file}")

    labels = []
    if args.labels:
        with open(args.labels, "r") as f:
            labels = json.load(f).get("labels", [])

    print(f"📦 Loading model: {model_file}")
    network = Network(model_file)
    preprocessor = Preprocessor()
    detector = Detector(
        args.score_threshold,
        args.max_detections,
        not args.disable_nms,
        args.iou_threshold,
        args.iou_with_min
    )

    inp = args.input
    ext = Path(inp).suffix.lower()

    # ---- IMAGE INPUT ----
    if ext in [".jpg", ".jpeg", ".png"]:
        print(f"📷 Running inference on image: {inp}")
        frame = cv2.imread(inp)
        annotated = infer_frame(network, preprocessor, detector, frame, labels)
        out_path = str(Path(inp).with_name(Path(inp).stem + "_result.jpg"))
        cv2.imwrite(out_path, annotated)
        print(f"🖼️  Saved annotated image: {out_path}")

    # ---- VIDEO INPUT ----
    elif ext in [".mp4", ".avi", ".mov", ".mkv"]:
        print(f"🎥 Running inference on video: {inp}")
        cap = cv2.VideoCapture(inp)
        if not cap.isOpened():
            print("❌ Failed to open video.")
            return
        fps = cap.get(cv2.CAP_PROP_FPS)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        out_path = str(Path(inp).with_name(Path(inp).stem + "_result.mp4"))
        out_writer = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*'mp4v'), fps, (w, h))

        frame_count = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            annotated = infer_frame(network, preprocessor, detector, frame, labels)
            out_writer.write(annotated)
            frame_count += 1
            if frame_count % int(fps) == 0:
                print(f"⏱️  Processed {frame_count} frames...")

        cap.release()
        out_writer.release()
        print(f"✅ Saved annotated video: {out_path}")
    else:
        print("❌ Unsupported file type. Please use .jpg, .png, or .mp4")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run object detection on image or video using Synap SDK")
    parser.add_argument("-m", "--model", required=True, help="Path to .synap model file")
    parser.add_argument("--labels", help="Path to JSON file with labels")
    parser.add_argument("--score-threshold", type=float, default=0.5, help="Min detection confidence")
    parser.add_argument("--max-detections", type=int, default=0, help="Max number of detections (0 = all)")
    parser.add_argument("--disable-nms", action="store_true", help="Disable Non-Max Suppression")
    parser.add_argument("--iou-threshold", type=float, default=0.5, help="IOU threshold for NMS")
    parser.add_argument("--iou-with-min", action="store_true", help="Use min area instead of union")
    parser.add_argument("input", help="Input image or video file")
    args = parser.parse_args()

    main(args)
