# Walk-Sign Branch — Wearable Navigation (AI Traffic Light & Crosswalk Detection)

This branch hosts the **Walk-Sign** project — a lightweight object-detection model trained on traffic lights and pedestrian signals for use on the **Synaptics Astra Board** (VS680 NPU platform).
It demonstrates how to convert a TensorFlow-Lite model (`.tflite`) from Roboflow into Synaptics’ `.synap` format and deploy it on-device for real-time inference.

---

## 📁 Repository Structure

```
wearable-navigation/
└── Walk-Sign/
    ├── rf_v1/
    │   ├── cache/                # Auto-generated temp folder by Synap converter
    │   ├── labels.txt            # Class labels used by the model
    │   ├── model.synap           # Final compiled model for Astra (NPU binary)
    │   └── model_info.txt        # Metadata: input/output shapes, quantization, formats
    ├── don't_walk.jpg            # Test image – pedestrian “Don’t Walk” signal
    ├── green.jpg                 # Test image – green traffic light
    ├── red.jpg                   # Test image – red traffic light
    ├── walk_sign.jpg             # Test image – “Walk” sign
    └── yello.jpg                 # Test image – yellow light
```

---

## 🧠 Model Overview

* **Base model:** `capstone-synap_v1.tflite` (Roboflow export, trained on traffic/crosswalk images)
* **Converted model:** `model.synap` generated using Synaptics SDK tools inside Docker
* **Input shape:** 224 × 224 × 3 (RGB, INT8)
* **Output tensor:** `[1, 11, 1029]` — detection head (raw bounding boxes + confidence)
* **Labels:** 9 classes

  ```
  Crosswalk  
  Don’t Walk  
  Green  
  Red  
  Traffic Signal  
  Walk  
  Yellow  
  Null
  ```

---

## 🧰 Conversion Environment (Docker Setup)

### **1️⃣ Launch the Synaptics SDK Docker image**

> Used to run the `synap convert` utility inside a clean SDK environment.

```bash
docker run -it --rm \
  -v D:/Synap:/workspace \
  synapticsas/synap-sdk:1.7 \
  /bin/bash
```

### **2️⃣ Inside Docker – Convert `.tflite` → `.synap`**

```bash
cd /workspace
synap convert \
  --model capstone-synap_v1.tflite \
  --target VS680 \
  --out-dir out/rf_v1
```

This creates the compiled **model.synap** and metadata file **model_info.txt** under `/workspace/out/rf_v1/`.

---

## 💾 Deployment Instructions (on Astra Board)

### **1️⃣ Copy model and test images**

Copy the folder `rf_v1` to the Astra board (via SSH, SCP, or VS Code remote):

```bash
scp -r out/rf_v1 root@192.168.137.207:/home/root/models/
```

Verify on board:

```bash
cd ~/models/rf_v1
ls -lh
```

### **2️⃣ Run inference test**

Quick sanity check using random input:

```bash
synap_cli -m model.synap random
```

Expected output → inference time summary and tensor stats.

### **3️⃣ Run on an image**

```bash
synap_cli_od -m model.synap red.jpg --out red_out.jpg
```

*(If SDK throws “Unknown object detection format”, reconversion with proper OD metadata YAML is required.)*

---

## ⚙️ SDK Compatibility Notes

* **Astra Board #1 (SDK 1.2)**

  * Once a model is flashed, the NPU cannot be reflashed again.
  * Keep this unit as-is (don’t overwrite working demo).

* **Astra Board #2 (Repaired unit, SDK 1.7)**

  * Fully compatible with re-flashing `.synap` models.
  * Use this device for all future testing, model updates, and performance evaluation.

---

## 🧩 File Reference Summary

| File             | Description                                                  |
| ---------------- | ------------------------------------------------------------ |
| `model.synap`    | Compiled Synaptics binary (runnable on Astra NPU).           |
| `model_info.txt` | Model metadata: input/output details, layer info, precision. |
| `labels.txt`     | Human-readable class names matching dataset.                 |
| `*.jpg`          | Sample test images for validation.                           |
| `cache/`         | Temporary build data created during conversion.              |

---

## 🧪 Testing Example (on Board)

```bash
cd ~/models/rf_v1

# Run raw inference
synap_cli -m model.synap random

# Run with image
synap_cli_od -m model.synap walk_sign.jpg --out walk_out.jpg

# View result image via SCP or VS Code download
```

---

## 🧾 Branch Purpose

The **`Walk-Sign` branch** is dedicated to:

* Hosting the converted **Synaptics model artifacts**
* Demonstrating end-to-end conversion and deployment steps
* Providing a ready-to-clone template for other object-detection models on Astra

---

## 🚀 Quick-Start Summary

```bash
# 1. Clone repo and switch branch
git clone https://github.com/prateeksha9/wearable-navigation.git
cd wearable-navigation
git checkout Walk-Sign

# 2. Copy rf_v1 folder to Astra
scp -r rf_v1 root@<board-ip>:/home/root/models/

# 3. SSH into Astra and test
ssh root@<board-ip>
cd ~/models/rf_v1
synap_cli -m model.synap random
synap_cli_od -m model.synap red.jpg --out result.jpg
```

---

### ✍️ Maintainer

**Author:** Yash Ingle
**Project:** MECPS Capstone — *Synaptics Astra Board Vision Integration*
**Branch:** `Walk-Sign`
**Purpose:** Traffic Light & Pedestrian Signal Detection for Wearable Navigation
