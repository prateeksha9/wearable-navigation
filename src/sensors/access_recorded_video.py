from ultralytics import YOLO
import cv2

# path to your trained YOLOv8n model
MODEL_PATH = "/home/root/Code_Testing/wearable-navigation/models/yolov8n.pt"
model = YOLO(MODEL_PATH)
print("✅ YOLOv8n loaded for post-processing")

def run_inference_on_clip(filename: str):
    print(f"🔎 Running YOLOv8n inference on {filename} ...")
    results = model.predict(source=filename, save=True, project="runs/detect", name="astra_batch")
    print(f"✅ Inference complete — outputs saved to {results[0].save_dir}")

# inside main()
            record_clip(raw_file)
            run_inference_on_clip(raw_file)
            count += 1
