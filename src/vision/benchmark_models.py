import os
import cv2
import time
import argparse
import numpy as np
import tflite_runtime.interpreter as tflite
import psutil


# ==========================================================
# Paths / constants
# ==========================================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODEL_DIR = os.path.join(BASE_DIR, "tflite_models")
VIDEO_DIR = os.path.join(BASE_DIR, "src", "videos")

INPUT_W = 224
INPUT_H = 224
SCORE_THRESH = 0.25


# ==========================================================
# Load labels
# ==========================================================
def load_labels(path):
    with open(path, "r") as f:
        return [line.strip() for line in f.readlines()]


# ==========================================================
# Load TFLite model
# ==========================================================
def load_model(path):
    interpreter = tflite.Interpreter(path)
    interpreter.allocate_tensors()
    inp = interpreter.get_input_details()
    outp = interpreter.get_output_details()
    return interpreter, inp, outp


# ==========================================================
# YOLO decoder (matches your TFLite export)
# ==========================================================
def decode_yolo_output(output, input_size=(INPUT_W, INPUT_H)):
    """
    output shape: (A, N)
    first 4 -> cx, cy, w, h
    rest -> class logits
    """
    attrs, N = output.shape

    boxes_xywh = output[0:4, :].T  # (N, 4)
    class_logits = output[4:, :]   # (num_classes, N)

    class_ids = np.argmax(class_logits, axis=0)
    scores = np.max(class_logits, axis=0)

    cx = boxes_xywh[:, 0].astype(np.float32)
    cy = boxes_xywh[:, 1].astype(np.float32)
    w = boxes_xywh[:, 2].astype(np.float32)
    h = boxes_xywh[:, 3].astype(np.float32)

    # Normalize if in pixel space
    mx = max(cx.max(), cy.max(), w.max(), h.max())
    if mx > 2.0:
        cx /= input_size[0]
        cy /= input_size[1]
        w /= input_size[0]
        h /= input_size[1]

    x1 = cx - w / 2
    y1 = cy - h / 2
    x2 = cx + w / 2
    y2 = cy + h / 2

    boxes = np.stack([x1, y1, x2, y2], axis=1)
    return boxes, class_ids, scores


# ==========================================================
# Inference on one frame
# ==========================================================
def run_model(interpreter, inp, outp, frame):
    h, w = inp[0]["shape"][1:3]

    resized = cv2.resize(frame, (w, h))
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)

    tensor = np.expand_dims(rgb, axis=0).astype(np.uint8)
    interpreter.set_tensor(inp[0]["index"], tensor)
    interpreter.invoke()

    out = interpreter.get_tensor(outp[0]["index"])[0]
    boxes, ids, scores = decode_yolo_output(out)
    return boxes, ids, scores


# ==========================================================
# Draw boxes (only for video export)
# ==========================================================
def draw(frame, boxes, ids, scores, labels, color):
    H, W, _ = frame.shape
    for i, score in enumerate(scores):
        if score < SCORE_THRESH:
            continue

        x1, y1, x2, y2 = boxes[i]
        x1 = max(0.0, min(1.0, x1)); x2 = max(0.0, min(1.0, x2))
        y1 = max(0.0, min(1.0, y1)); y2 = max(0.0, min(1.0, y2))

        X1 = int(x1 * W); X2 = int(x2 * W)
        Y1 = int(y1 * H); Y2 = int(y2 * H)

        if X2 <= X1 or Y2 <= Y1:
            continue

        cls = labels[int(ids[i])]
        cv2.rectangle(frame, (X1, Y1), (X2, Y2), color, 2)
        cv2.putText(frame, f"{cls} {score:.2f}", (X1, max(0, Y1 - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
    return frame


# ==========================================================
# Benchmark runner
# ==========================================================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", type=str, default="traffic_signal.mp4")
    parser.add_argument("--frames", type=int, default=300)
    parser.add_argument("--save-video", action="store_true")
    parser.add_argument("--dump", type=str, default=None)
    args = parser.parse_args()

    video_path = os.path.join(VIDEO_DIR, args.video)
    if not os.path.exists(video_path):
        raise FileNotFoundError(video_path)

    # -------------------------------
    # Load 3 models
    # -------------------------------
    MODELS = {
        "surroundings": {
            "model": os.path.join(MODEL_DIR, "surroundings_v2.tflite"),
            "labels": os.path.join(MODEL_DIR, "surroundings_v2.txt"),
            "color": (0, 255, 0),
        },
        "traffic": {
            "model": os.path.join(MODEL_DIR, "Traffic_v3.tflite"),
            "labels": os.path.join(MODEL_DIR, "traffic_v3.txt"),
            "color": (0, 0, 255),
        },
        "walksign": {
            "model": os.path.join(MODEL_DIR, "walksign_v6.tflite"),
            "labels": os.path.join(MODEL_DIR, "walk_sign_v6.txt"),
            "color": (255, 200, 0),
        },
    }

    loaded = {}
    cold_start_begin = time.time()

    for key, cfg in MODELS.items():
        print("Loading", key)
        inter, inp, outp = load_model(cfg["model"])
        labels = load_labels(cfg["labels"])
        loaded[key] = (inter, inp, outp, labels)

    cold_start_time = time.time() - cold_start_begin
    print(f"\nCold start load time: {cold_start_time:.3f} sec\n")

    # -------------------------------
    # Setup video IO
    # -------------------------------
    cap = cv2.VideoCapture(video_path)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 20.0

    if args.save_video:
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter("benchmark_output.mp4", fourcc, fps, (w, h))
    else:
        out = None

    # -------------------------------
    # Benchmark loop
    # -------------------------------
    latencies = []
    per_model_lat = {k: [] for k in loaded.keys()}
    dump_lines = []

    start_total = time.time()
    frame_count = 0

    print("Running benchmark...")

    while frame_count < args.frames:
        ret, frame = cap.read()
        if not ret:
            break

        frame_start = time.time()

        # Run 3 models
        for name, cfg in loaded.items():
            inter, inp, outp, labels = cfg

            t0 = time.time()
            boxes, ids, scores = run_model(inter, inp, outp, frame)
            t1 = time.time()

            per_model_lat[name].append(t1 - t0)

            if out:
                frame = draw(frame, boxes, ids, scores, labels, MODELS[name]["color"])

            if args.dump:
                dump_lines.append(
                    f"{frame_count},{name},{ids.tolist()},{scores.tolist()}"
                )

        frame_end = time.time()
        latencies.append(frame_end - frame_start)

        if out:
            out.write(frame)

        frame_count += 1
        if frame_count % 20 == 0:
            print(f"Processed {frame_count}/{args.frames} frames...", end="\r")

    total_time = time.time() - start_total
    fps_final = frame_count / total_time
    avg_lat = np.mean(latencies)
    p95_lat = np.percentile(latencies, 95)

    print("\n==== RESULTS ====")
    print(f"Frames processed: {frame_count}")
    print(f"FPS: {fps_final:.2f}")
    print(f"Avg latency: {avg_lat*1000:.2f} ms")
    print(f"P95 latency: {p95_lat*1000:.2f} ms")

    print("\nPer-model avg latencies:")
    for name in per_model_lat:
        if len(per_model_lat[name]) > 0:
            print(f"{name}: {np.mean(per_model_lat[name])*1000:.2f} ms")

    # -------------------------------
    # System metrics
    # -------------------------------
    cpu = psutil.cpu_percent()
    print(f"\nSystem CPU load: {cpu}%")

    if hasattr(psutil, "sensors_temperatures"):
        temps = psutil.sensors_temperatures()
        if temps:
            print("Temperatures:", temps)

    # -------------------------------
    # Save dump file
    # -------------------------------
    if args.dump:
        with open(args.dump, "w") as f:
            f.write("\n".join(dump_lines))
        print(f"Results saved to {args.dump}")

    if out:
        out.release()
        print("Video saved to benchmark_output.mp4")


if __name__ == "__main__":
    main()
