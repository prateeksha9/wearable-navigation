#!/usr/bin/env python3
"""
Inference script for Synaptics Astra SL1680 (.synap models)
Supports:
 - Object detection inference on one or more images
 - Label descriptions from a JSON file (e.g., {"labels": ["Green", "Red", "Yellow"]})
 - Optional OpenCV visualization (bounding boxes + class labels)

Usage:
    python3 src/vision/infer_synap.py \
        -m models/traffic_v3/model.synap \
        --labels models/traffic_v3/traffic_labels.json \
        sample_images/yellow.jpg
"""

import json
import sys
import time
from pathlib import Path
import cv2

# SyNAP Python API (preinstalled on Astra SDK)
from synap import Network
from synap.preprocessor import Preprocessor
from synap.postprocessor import Detector, to_json_str


def draw_results(image_path, result, labels):
    """Draw bounding boxes and class labels on the image."""
    img = cv2.imread(image_path)
    if img is None:
        print(f"⚠️  Could not read image {image_path}")
        return

    for item in result.items:
        bb = item.bounding_box
        x, y = int(bb.origin.x), int(bb.origin.y)
        w, h = int(bb.size.x), int(bb.size.y)
        conf = item.confidence
        label = labels[item.class_index] if labels and item.class_index < len(labels) else f"class_{item.class_index}"

        cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 0), 2)
        cv2.putText(img, f"{label} ({conf:.2f})", (x, max(y - 10, 20)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

    out_path = str(Path(image_path).with_name(Path(image_path).stem + "_result.jpg"))
    cv2.imwrite(out_path, img)
    print(f"🖼️  Saved annotated image: {out_path}")


def main(args):
    model_file = Path(args.model)
    if not model_file.exists():
        raise FileNotFoundError(f"❌ Model file '{args.model}' not found")

    # Load labels from JSON
    labels = None
    if args.labels:
        labels_path = Path(args.labels)
        if not labels_path.exists():
            print(f"⚠️  Labels file '{args.labels}' not found")
        else:
            with open(labels_path, "r") as f:
                try:
                    labels = json.load(f).get("labels", [])
                except Exception as e:
                    print(f"⚠️  Failed to parse labels file: {e}")

    print(f"\n📦 Loading model: {model_file}")
    network = Network(model_file)
    preprocessor = Preprocessor()
    detector = Detector(
        args.score_threshold,
        args.max_detections,
        not args.disable_nms,
        args.iou_threshold,
        args.iou_with_min
    )

    for image_path in args.inputs:
        print(f"\n📷 Processing: {image_path}")
        t0 = time.time()
        assigned_rect = preprocessor.assign(network.inputs, image_path)
        t_pre = (time.time() - t0) * 1000

        t1 = time.time()
        outputs = network.predict()
        t_inf = (time.time() - t1) * 1000

        t2 = time.time()
        result = detector.process(outputs, assigned_rect)
        t_post = (time.time() - t2) * 1000

        total = t_pre + t_inf + t_post
        print(f"⚙️  Detection time: {total:.2f} ms (pre: {t_pre:.2f}, inf: {t_inf:.2f}, post: {t_post:.2f})")

        print("#   Score  Class   Position        Size   Description")
        for i, item in enumerate(result.items):
            bb = item.bounding_box
            desc = labels[item.class_index] if labels and item.class_index < len(labels) else f"class_{item.class_index}"
            print(f"{i:<3}  {item.confidence:.2f} {item.class_index:>6}  "
                  f"{bb.origin.x:>4},{bb.origin.y:>4}   {bb.size.x:>4},{bb.size.y:>4}  {desc}")

        if args.save_output:
            draw_results(image_path, result, labels)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Inference script for .synap object detection models")
    parser.add_argument("-m", "--model", required=True, help="Path to .synap model file")
    parser.add_argument("--labels", help="Path to JSON file with labels (e.g. {'labels': ['Green','Red','Yellow']})")
    parser.add_argument("--score-threshold", type=float, default=0.5, help="Minimum detection confidence threshold")
    parser.add_argument("--max-detections", type=int, default=0, help="Maximum number of detections (0 = all)")
    parser.add_argument("--disable-nms", action="store_true", help="Disable non-max suppression")
    parser.add_argument("--iou-threshold", type=float, default=0.5, help="IOU threshold for NMS")
    parser.add_argument("--iou-with-min", action="store_true", help="Use min area instead of union for IOU")
    parser.add_argument("--save-output", action="store_true", help="Save annotated image(s) with results")
    parser.add_argument("inputs", nargs="+", help="Path(s) to input image(s)")
    args = parser.parse_args()

    main(args)
