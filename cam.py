import os, time, cv2, tempfile, collections, math
from inference_sdk import InferenceHTTPClient

API_KEY = os.environ.get("ROBOFLOW_API_KEY")
if not API_KEY:
    raise SystemExit("ROBOFLOW_API_KEY not set")

client = InferenceHTTPClient(
    api_url="https://serverless.roboflow.com",
    api_key=API_KEY
)

# ---------- Tuning knobs ----------
MODEL_ID = "traffic-light-detection-ozcos/1"

CAM_INDEX = 0
REQUEST_W, REQUEST_H = 640, 480    # usually higher FPS at 640x480
REQUEST_FPS = 30                   # webcam target; may be ignored by some cams
USE_MJPEG = True                   # MJPEG often gives much better FPS

DISPLAY = True                     # show window
UPLOAD_MAX_WIDTH = 480             # downscale *upload* only (keep preview native)
JPEG_QUALITY = 80                  # 60–85 sweet spot
MAX_INFER_FPS = 12                 # cap cloud calls for smoother UI
CONF_THRESH = 0.45                 # ignore very low confidence boxes

# temporal smoothing (moving window voting)
SMOOTH_WINDOW = 8                  # frames to keep
SMOOTH_MIN_COUNT = 3               # require >= N mentions of the same class
CLASSES = ("Red", "Yellow", "Green")

# drawing
COLORS = {
    "Red":    (0,   0, 255),
    "Yellow": (0, 255, 255),
    "Green":  (0, 255,   0)
}
BOX_THICK = 2
TEXT_SCALE = 0.6
TEXT_THICK = 2
# ----------------------------------


def open_cam(index=0):
    cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)  # CAP_DSHOW avoids some lag on Windows
    if USE_MJPEG:
        fourcc = cv2.VideoWriter_fourcc(*"MJPG")
        cap.set(cv2.CAP_PROP_FOURCC, fourcc)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  REQUEST_W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, REQUEST_H)
    cap.set(cv2.CAP_PROP_FPS, REQUEST_FPS)
    if not cap.isOpened():
        raise SystemExit("Webcam not found")
    return cap

def shrink(img, max_w):
    h, w = img.shape[:2]
    if w <= max_w:
        return img
    scale = max_w / w
    return cv2.resize(img, (int(w*scale), int(h*scale)), interpolation=cv2.INTER_AREA)

def draw_label(bg, x1, y1, text, color):
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, TEXT_SCALE, TEXT_THICK)
    cv2.rectangle(bg, (x1, max(0, y1 - th - 6)), (x1 + tw + 6, y1), color, -1)
    cv2.putText(bg, text, (x1 + 3, max(0, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, TEXT_SCALE, (0, 0, 0), TEXT_THICK)

def overlay_fps(img, fps, net_fps, state_text):
    msg = f"Cam FPS: {fps:.1f} | Infer FPS: {net_fps:.1f} | State: {state_text}"
    cv2.putText(img, msg, (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (30,30,30), 3)
    cv2.putText(img, msg, (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (230,230,230), 1)

cap = open_cam(CAM_INDEX)

# FPS meters
cam_t0 = time.time()
cam_frames = 0
cam_fps = 0.0

net_t0 = time.time()
net_frames = 0
net_fps = 0.0
min_infer_interval = 1.0 / MAX_INFER_FPS

# smoothing buffers
history = collections.deque(maxlen=SMOOTH_WINDOW)

try:
    last_infer_time = 0.0
    while True:
        ok, frame = cap.read()
        if not ok:
            # try to reopen if camera glitch
            try:
                cap.release()
            except:
                pass
            time.sleep(0.2)
            cap = open_cam(CAM_INDEX)
            continue

        cam_frames += 1
        if time.time() - cam_t0 >= 1.0:
            cam_fps = cam_frames / (time.time() - cam_t0)
            cam_t0 = time.time()
            cam_frames = 0

        # resize for upload
        show_frame = frame  # keep native for display
        send_frame = shrink(frame, UPLOAD_MAX_WIDTH)

        now = time.time()
        do_infer = (now - last_infer_time) >= min_infer_interval

        preds = []
        if do_infer:
            # JPEG encode to bytes (fast, no temp file thrash)
            ok_enc, jpg = cv2.imencode(".jpg", send_frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
            if not ok_enc:
                continue

            # most compatible path: write temp file then call infer(path)
            tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
            try:
                tmp.write(jpg.tobytes())
                tmp.flush()
                tmp.close()

                res = client.infer(tmp.name, model_id=MODEL_ID)
            finally:
                try:
                    os.unlink(tmp.name)
                except:
                    pass

            preds = [p for p in res.get("predictions", []) if p.get("confidence", 0.0) >= CONF_THRESH]
            last_infer_time = now

            net_frames += 1
            if time.time() - net_t0 >= 1.0:
                net_fps = net_frames / (time.time() - net_t0)
                net_t0 = time.time()
                net_frames = 0

            # update smoothing buffer with the *top* class if any
            if preds:
                top = max(preds, key=lambda p: p["confidence"])
                history.append(top.get("class", ""))
            else:
                history.append("")

        # compute smoothed state
        counts = {k: 0 for k in CLASSES}
        for v in history:
            if v in counts:
                counts[v] += 1
        smoothed_state = ""
        if counts:
            cls, cnt = max(counts.items(), key=lambda x: x[1])
            smoothed_state = cls if cnt >= SMOOTH_MIN_COUNT else ""

        # draw predictions (map from upload coords to display coords)
        if preds:
            sx, sy = send_frame.shape[1], send_frame.shape[0]
            dx, dy = show_frame.shape[1], show_frame.shape[0]
            scale_x = dx / sx
            scale_y = dy / sy

            for p in preds:
                x, y, w, h = p["x"], p["y"], p["width"], p["height"]
                x1 = int((x - w / 2) * scale_x)
                y1 = int((y - h / 2) * scale_y)
                x2 = int((x + w / 2) * scale_x)
                y2 = int((y + h / 2) * scale_y)
                cls = p.get("class", "object")
                conf = p.get("confidence", 0.0)
                color = COLORS.get(cls, (0, 0, 0))
                cv2.rectangle(show_frame, (x1, y1), (x2, y2), color, BOX_THICK)
                draw_label(show_frame, x1, y1, f"{cls} {conf:.2f}", color)

        # overlay FPS + state
        overlay_fps(show_frame, cam_fps, net_fps, smoothed_state or "—")

        if DISPLAY:
            cv2.imshow("Traffic Light Detection", show_frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            elif key == ord("d"):  # toggle display
                DISPLAY = not DISPLAY
            elif key == ord("-"):  # reduce upload width
                UPLOAD_MAX_WIDTH = max(240, UPLOAD_MAX_WIDTH - 40)
            elif key == ord("="):  # increase upload width
                UPLOAD_MAX_WIDTH = min(960, UPLOAD_MAX_WIDTH + 40)
            elif key == ord("["):  # lower JPEG quality
                JPEG_QUALITY = max(40, JPEG_QUALITY - 5)
            elif key == ord("]"):  # raise JPEG quality
                JPEG_QUALITY = min(95, JPEG_QUALITY + 5)

except KeyboardInterrupt:
    pass
finally:
    try:
        cap.release()
    except:
        pass
    if DISPLAY:
        cv2.destroyAllWindows()
