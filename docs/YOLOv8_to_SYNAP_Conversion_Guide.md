
# YOLOv8 to SyNAP Conversion Guide for Synaptics Astra SL1680

This document explains step-by-step how to convert a trained YOLOv8 model into a `.synap` format compatible with the Synaptics Astra SL1680 board and run inference successfully.

---

## 🧭 Overview

**Goal:** Convert YOLOv8 model (`.pt`) → ONNX → `.synap` (for NPU inference on Astra SL1680).  
**Tools Used:**
- Ultralytics YOLOv8
- Docker with SyNAP Toolkit
- Astra SL1680 Board CLI (`synap_cli`, `synap_cli_od`)

---

## 🧩 1. Export YOLOv8 Model to ONNX

From your training directory (e.g., `crosswalk`):

```bash
yolo export model=runs/train/traffic_yolov82/weights/best.pt format=onnx imgsz=640
```

✅ This creates:
```
runs/train/traffic_yolov82/weights/best.onnx
```

---

## ⚙️ 2. Pull the SyNAP Toolkit Docker Image

On your macOS or Linux system:

```bash
docker pull ghcr.io/synaptics-synap/toolkit:3.1.0
```

---

## 🧰 3. Create a `synap` Alias for Easy Use

For macOS / Linux (bash or zsh):

```bash
alias synap='docker run --platform linux/amd64 -i --rm -u $(id -u):$(id -g) -v $HOME:$HOME -w $(pwd) ghcr.io/synaptics-synap/toolkit:3.1.0'
```

To make it permanent:

```bash
echo "alias synap='docker run --platform linux/amd64 -i --rm -u \$(id -u):\$(id -g) -v \$HOME:\$HOME -w \$(pwd) ghcr.io/synaptics-synap/toolkit:3.1.0'" >> ~/.zshrc
source ~/.zshrc
```

Verify the alias works:

```bash
synap help
```

You should see the SyNAP command list.

---

## 🧠 4. Create YOLO Metadata File

Create a file `yolo_meta.yaml` next to your ONNX model:

```yaml
delegate: npu
data_layout: nhwc

inputs:
  - name: images
    shape: [1, 640, 640, 3]
    format: rgb
    scale: 255
    means: [0, 0, 0]

outputs:
  - name: output0
    type: yolo
    format: detect
    anchors:
      - [10,13, 16,30, 33,23]
      - [30,61, 62,45, 59,119]
      - [116,90, 156,198, 373,326]
    num_classes: 5   # Walk, Don't Walk, Red, Yellow, Green
    stride: [8, 16, 32]

quantization:
  data_type: uint8
  scheme: asymmetric_affine
  mode: standard
```

---

## ⚙️ 5. Convert ONNX → SYNAP Format

From your ONNX model directory:

```bash
synap convert --model best.onnx --meta yolo_meta.yaml --target sl1680 --out-dir synap_output
```

🕒 Note: On Apple Silicon (M1/M2), Docker uses x86 emulation, which can be slow.  
You can monitor conversion progress using:

```bash
nohup synap convert --model best.onnx --meta yolo_meta.yaml --target sl1680 --out-dir synap_output > synap_log.txt 2>&1 &
tail -f synap_log.txt
```

✅ Output Folder:

```
synap_output/
 ├── model.synap
 ├── model_info.txt
 └── cache/
```

---

## 🚀 6. Deploy on Astra SL1680 Board

### 6.1 Copy the Model

```bash
scp synap_output/model.synap root@sl1680:~/Code_Testing/wearable-navigation/rf_v1/
```

### 6.2 Run Basic Inference

```bash
synap_cli -m rf_v1/model.synap green.jpg
```

Expected output:
```
Predict #0: 13.8 ms
Inference timings: load: 31.22  init: 10.4  mean: 13.8
```

### 6.3 Run Object Detection (YOLO)

```bash
synap_cli_od -m rf_v1/model.synap walk_sign.jpg --out result.jpg
```

✅ Output:
```
Detected 1 object: class=Walk conf=0.98 (x1,y1,x2,y2)
```
and `result.jpg` will show bounding boxes.

---

## 🧩 7. Troubleshooting

| Issue | Cause | Solution |
|-------|--------|-----------|
| `Error, model not found` | Wrong working directory | `cd` into correct folder or use full path |
| `Failed to initialize detector` | Missing YOLO meta file | Reconvert with `yolo_meta.yaml` |
| Docker freezing on Mac | x86 emulation overhead | Increase Docker RAM to 8GB, CPUs to 8, or use x86 Linux |
| `Input file not found` | Image not in working dir | Copy image to same folder as model |

---

## ✅ Example Directory Structure

```
/Users/prateeksharanjan/Desktop/CapstoneCode/Traffic-Light-Detection-Color-Classification/crosswalk/
│
├── runs/train/traffic_yolov82/weights/
│   ├── best.pt
│   ├── best.onnx
│   ├── yolo_meta.yaml
│   └── synap_output/
│       ├── model.synap
│       ├── model_info.txt
│       └── cache/
│
└── test_images/
    ├── walk_sign.jpg
    ├── red.jpg
    ├── yellow.jpg
    ├── green.jpg
    └── dont_walk.jpg
```

---

## 🧾 Notes

- If running on **Mac M1**, expect long conversion times due to Rosetta emulation.
- For faster conversion, use an **x86 Linux system** (UCI Penglai or similar).
- Always verify model inputs/outputs with `synap_cli -m model.synap random` before real inference.

---

**Author:** Prateeksha Ranjan  
**Date:** November 2025  
**Project:** AI-Powered Wearable Navigation System for Visually Impaired Individuals (UCI + Synaptics)
