#dless Roboflow inference on Synaptics Astra AI (GStreamer NV12 appsink)
# - Camera: /dev/video6 (NV12)
# - No GUI (console-only)
# - Uses Roboflow inference SDK with temp-file JPEG uploads for compatibility

import os, time, cv2, tempfile, collections, signal, sys
from inference_sdk import InferenceHTTPClient

# ---------- User settings ----------
MODEL_ID = "traffic-light-detection-ozcos/1"
CAM_DEVICE = "/dev/video6"        # confirmed working on your board
REQUEST_W, REQUEST_H = 640, 480   # adjust if you need different res
REQUEST_FPS = 30                  # target; actual may vary
UPLOAD_MAX_WIDTH = 480            # downscale upload; keep capture native
JPEG_QUALITY = 80                 # 60–85 typical
MAX_INFER_FPS = 12                # cap cloud calls to smooth console + save bandwidth
CONF_THRESH = 0.45                # ignore low-confidence boxes
SMOOTH_WINDOW = 8                 # moving window of top-class
SMOOTH_MIN_COUNT = 3              # require >= N hits in window
CLASSES = ("Red", "Yellow", "Green")
# -----------------------------------

API_KEY = os.environ.get("ROBOFLOW_API_KEY")
if not API_KEY:
    raise SystemExit("ROBOFLOW_API_KEY not set")

client = InferenceHTTPClient(
    api_url="https://serverless.roboflow.com",
    api_key=API_KEY
)

def gst_pipeline_nv12(device, w, h, fps):
    """
    Build a GStreamer pipeline pulling NV12 from /dev/video6 and converting to BGR.
    """
    return (
        f"v4l2src device={device} ! "
        f"video/x-raw,format=NV12,width={w},height={h},framerate={fps}/1 ! "
        f"videoconvert ! appsink drop=true sync=false"
    )

def open_cam_gst(device, w, h, fps):
    pipe = gst_pipeline_nv12(device, w, h, fps)
    cap = cv2.VideoCapture(pipe, cv2.CAP_GSTREAMER)
    if not cap.isOpened():
        raise SystemExit("GStreamer camera open failed (check /dev node, caps, OpenCV GStreamer build)")
    return cap

def shrink(img, max_w):
    h, w = img.shape[:2]
    if w <= max_w:
        return img
    scale = max_w / w
    return cv2.resize(img, (int(w*scale), int(h*scale)), interpolation=cv2.INTER_AREA)

def encode_jpeg(img, quality=80):
    ok, jpg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return jpg.tobytes() if ok else None

def smooth_state(history, classes, min_count):
    counts = {k: 0 for k in classes}
    for v in history:
        if v in counts:
            counts[v] += 1
    if not counts:
        return ""
    cls, cnt = max(counts.items(), key=lambda x: x[1])
    return cls if cnt >= min_count else ""

def main():
    cap = open_cam_gst(CAM_DEVICE, REQUEST_W, REQUEST_H, REQUEST_FPS)

    # FPS meters
    cam_t0 = time.time(); cam_frames = 0; cam_fps = 0.0
    net_t0 = time.time(); net_frames = 0; net_fps = 0.0
    min_infer_interval = 1.0 / MAX_INFER_FPS

    history = collections.deque(maxlen=SMOOTH_WINDOW)
    last_infer_time = 0.0
    last_print = 0.0
    last_state = ""

    print("[INFO] Roboflow traffic-light (Astra/NV12, headless) starting…")
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                # brief reopen on glitch
                try: cap.release()
                except: pass
                time.sleep(0.2)
                cap = open_cam_gst(CAM_DEVICE, REQUEST_W, REQUEST_H, REQUEST_FPS)
                continue

            # camera FPS meter
            cam_frames += 1
            now = time.time()
            if now - cam_t0 >= 1.0:
                cam_fps = cam_frames / (now - cam_t0)
                cam_t0 = now
                cam_frames = 0

            # downscale just for upload (keep capture native)
            send_frame = shrink(frame, UPLOAD_MAX_WIDTH)

            # rate-limit inferences
            preds = []
            if (now - last_infer_time) >= min_infer_interval:
                jpg_bytes = encode_jpeg(send_frame, JPEG_QUALITY)
                if jpg_bytes is None:
                    continue

                # temp-file path for max compatibility with SDK
                tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
                try:
                    tmp.write(jpg_bytes); tmp.flush(); tmp.close()
                    res = client.infer(tmp.name, model_id=MODEL_ID)
                finally:
                    try: os.unlink(tmp.name)
                    except: pass

                preds = [p for p in res.get("predictions", []) if p.get("confidence", 0.0) >= CONF_THRESH]
                last_infer_time = now

                # net FPS meter
                net_frames += 1
                if now - net_t0 >= 1.0:
                    net_fps = net_frames / (now - net_t0)
                    net_t0 = now
                    net_frames = 0

                # update smoothing buffer with the top class (if any)
                if preds:
                    top = max(preds, key=lambda p: p["confidence"])
                    history.append(top.get("class", ""))
                else:
                    history.append("")

            # compute smoothed state
            state = smooth_state(history, CLASSES, SMOOTH_MIN_COUNT)

            # print on state change OR every 0.5s for a heartbeat
            if state != last_state or (now - last_print) >= 0.5:
                print(f"CamFPS={cam_fps:4.1f}  InferFPS={net_fps:4.1f}  State={state or '—'}  UploadW={UPLOAD_MAX_WIDTH}  JPEGq={JPEG_QUALITY}", end="\r")
                last_print = now
                last_state = state

    except KeyboardInterrupt:
        pass
    finally:
        try: cap.release()
        except: pass
        print("\n[INFO] Stopped.")

# Graceful SIGTERM for service mode
def _sigterm(_sig, _frm):
    raise KeyboardInterrupt
signal.signal(signal.SIGTERM, _sigterm)

if __name__ == "__main__":
    main()

