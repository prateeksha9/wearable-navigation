#!/usr/bin/env python3
"""
Dual Synap Model Inference (Sequential)
Runs two .synap models on the same image or video.
Example use:
  - Model 1: Traffic light detection
  - Model 2: Pedestrian walk sign detection
"""

import json
import cv2
import time
from pathlib import Path
from synap import Network
from synap.preprocessor import Preprocessor
from synap.postprocessor import Detector


def load_model(model_path, score_thr=0.5):
    model_file = Path(model_path)
    net = Network(model_file)
    pre = Preprocessor()
    det = Detector(score_thr, 0, True, 0.5, False)
    return net, pre, det


def run_model(net, pre, det, frame, labels):
    tmp = "/tmp/frame.jpg"
    cv2.imwrite(tmp, frame)
    rect = pre.assign(net.inputs, tmp)
    outputs = net.predict()
    result = det.process(outputs, rect)
    annotated = frame.copy()
    for item in result.items:
        bb = item.bounding_box
        x, y = int(bb.origin.x), int(bb.origin.y)
        w, h = int(bb.size.x), int(bb.size.y)
        label = labels[item.class_index] if labels and item.class_index < len(labels) else f"class_{item.class_index}"
        cv2.rectangle(annotated, (x, y), (x + w, y + h), (0, 255, 0), 2)
        cv2.putText(annotated, label, (x, max(y - 10, 20)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    return annotated


def main():
    # Paths to your two models + label files
    model1 = "models/traffic_v3/model.synap"
    labels1 = json.load(open("models/traffic_v3/traffic_labels.json"))["labels"]
    model2 = "models/walksign_v6/model.synap"
    labels2 = json.load(open("models/walksign_v6/traffic_labels.json"))["labels"]

    net1, pre1, det1 = load_model(model1)
    net2, pre2, det2 = load_model(model2)

    cap = cv2.VideoCapture("src/videos/traffic_signal.mp4")
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    out = cv2.VideoWriter("src/videos/dual_result.mp4", cv2.VideoWriter_fourcc(*'mp4v'), fps, (w, h))

    frame_id = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame1 = run_model(net1, pre1, det1, frame, labels1)
        frame2 = run_model(net2, pre2, det2, frame1, labels2)
        out.write(frame2)
        frame_id += 1
        if frame_id % int(fps) == 0:
            print(f"⏱️  Processed {frame_id} frames...")

    cap.release()
    out.release()
    print("✅ Saved dual-model annotated video → src/videos/dual_result.mp4")


if __name__ == "__main__":
    main()
