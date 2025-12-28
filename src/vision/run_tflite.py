import os
import cv2
import numpy as np
import tflite_runtime.interpreter as tflite


# -------------------------------------------------------------------
# Paths
# -------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODEL_DIR = os.path.join(BASE_DIR, "tflite_models")
VIDEO_PATH = os.path.join(BASE_DIR, "src", "videos", "traffic_signal.mp4")

INPUT_H = 224
INPUT_W = 224

# Detection threshold
SCORE_THRESH = 0.25


# -------------------------------------------------------------------
# Utility functions
# -------------------------------------------------------------------
def load_labels(path):
    with open(path, "r") as f:
        return [line.strip() for line in f.readlines()]


def load_model(tflite_path):
    interpreter = tflite.Interpreter(tflite_path)
    interpreter.allocate_tensors()
    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()
    return interpreter, input_details, output_details


def decode_yolo_output(output, input_size=(INPUT_W, INPUT_H)):
    """
    output: (A, N) where
        A = 4 + num_classes
        N = num_boxes

    First 4 rows: bbox (cx, cy, w, h)
    Remaining rows: class scores (num_classes, N)
    """
    attrs, num_boxes = output.shape
    if attrs < 5:
        raise ValueError(f"Unexpected YOLO attrs dim: {attrs}")

    # (N, 4)
    boxes_xywh = output[0:4, :].T

    # (num_classes, N)
    class_scores = output[4:, :]

    # Per box: best class and score
    class_ids = np.argmax(class_scores, axis=0)          # (N,)
    scores = np.max(class_scores, axis=0)                # (N,)

    # Convert (cx, cy, w, h) to normalized (x1, y1, x2, y2)
    cx = boxes_xywh[:, 0].astype(np.float32)
    cy = boxes_xywh[:, 1].astype(np.float32)
    w = boxes_xywh[:, 2].astype(np.float32)
    h = boxes_xywh[:, 3].astype(np.float32)

    # Heuristic: if values look like pixels, normalize to [0,1]
    if max(cx.max(), cy.max(), w.max(), h.max()) > 2.0:
        cx /= input_size[0]
        cy /= input_size[1]
        w /= input_size[0]
        h /= input_size[1]

    x1 = cx - w / 2.0
    y1 = cy - h / 2.0
    x2 = cx + w / 2.0
    y2 = cy + h / 2.0

    boxes_xyxy = np.stack([x1, y1, x2, y2], axis=1)      # (N, 4)
    return boxes_xyxy, class_ids, scores


def run_model(interpreter, input_details, output_details, frame):
    # Preprocess input
    h, w = input_details[0]['shape'][1:3]

    # Resize and convert BGR -> RGB (YOLO usually trained on RGB)
    resized = cv2.resize(frame, (w, h))
    resized = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)

    # Quantized uint8 input, scale is 1/255, TFLite handles that
    input_data = np.expand_dims(resized, axis=0).astype(np.uint8)

    interpreter.set_tensor(input_details[0]['index'], input_data)
    interpreter.invoke()

    # All your models have a single output tensor (YOLO-style)
    out_tensor = interpreter.get_tensor(output_details[0]['index'])[0]  # (A, N)
    boxes, class_ids, scores = decode_yolo_output(out_tensor)
    return boxes, class_ids, scores


def draw(frame, boxes, class_ids, scores, labels, color):
    H, W, _ = frame.shape

    for i, score in enumerate(scores):
        if score < SCORE_THRESH:
            continue

        x1, y1, x2, y2 = boxes[i]

        # Clip to [0,1]
        x1 = max(0.0, min(1.0, x1))
        x2 = max(0.0, min(1.0, x2))
        y1 = max(0.0, min(1.0, y1))
        y2 = max(0.0, min(1.0, y2))

        # Scale to frame coords
        X1 = int(x1 * W)
        X2 = int(x2 * W)
        Y1 = int(y1 * H)
        Y2 = int(y2 * H)

        if X2 <= X1 or Y2 <= Y1:
            continue

        cls_idx = int(class_ids[i])
        cls_name = labels[cls_idx] if 0 <= cls_idx < len(labels) else f"id{cls_idx}"

        cv2.rectangle(frame, (X1, Y1), (X2, Y2), color, 2)
        cv2.putText(
            frame,
            f"{cls_name} {score:.2f}",
            (X1, max(0, Y1 - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            color,
            2,
        )

    return frame


# -------------------------------------------------------------------
# Load all models
# -------------------------------------------------------------------
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

for key, cfg in MODELS.items():
    print("Loading", key)
    interpreter, inp, out_details = load_model(cfg["model"])
    labels = load_labels(cfg["labels"])
    loaded[key] = (interpreter, inp, out_details, labels)


# -------------------------------------------------------------------
# Video setup
# -------------------------------------------------------------------
cap = cv2.VideoCapture(VIDEO_PATH)

if not cap.isOpened():
    print("Cannot open video:", VIDEO_PATH)
    raise SystemExit

frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
fps = cap.get(cv2.CAP_PROP_FPS) or 20.0

fourcc = cv2.VideoWriter_fourcc(*"mp4v")
out = cv2.VideoWriter("output_demo.mp4", fourcc, fps, (frame_width, frame_height))

print("Processing video...")


# -------------------------------------------------------------------
# Inference loop (NO GUI, just write video)
# -------------------------------------------------------------------
frame_idx = 0

while True:
    ret, frame = cap.read()
    if not ret:
        break

    for key, cfg in MODELS.items():
        interpreter, inp, out_details, labels = loaded[key]
        boxes, ids, scores = run_model(interpreter, inp, out_details, frame)
        frame = draw(frame, boxes, ids, scores, labels, cfg["color"])

    out.write(frame)
    frame_idx += 1
    if frame_idx % 50 == 0:
        print(f"Processed {frame_idx} frames...", end="\r")

cap.release()
out.release()

print("\nDone! Output saved as output_demo.mp4")
