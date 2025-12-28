# Edge-AI Navigation Assistant on Synaptics Astra SL1680 (VS680 NPU)

A wearable navigation and safety assistant for visually impaired users built on the **Synaptics Astra SL1680 (VS680 NPU)** edge-AI platform. The system fuses **on-device vision (3 INT8 models)**, **ultrasonic ranging**, and an **MPU6050 IMU fall detector** into a single wearable prototype that runs **offline, fully on-device**, and in real time.

> “Feels like a cane, thinks like an AI camera.”

---

## Authors
- **Yash Daniel Ingle**
- **Hridya Satish Pisharady**
- **Prateeksha Ranjan**

---

## Table of Contents
- [1. Abstract](#1-abstract)
- [2. Motivation](#2-motivation)
- [3. What the System Does](#3-what-the-system-does)
- [4. High-Level System Behavior](#4-high-level-system-behavior)
- [5. System Architecture](#5-system-architecture)
- [6. Finite State Machine](#6-finite-state-machine)
- [7. Hardware](#7-hardware)
  - [7.1 Hardware at a Glance](#71-hardware-at-a-glance)
  - [7.2 Bill of Materials](#72-bill-of-materials)
  - [7.3 GPIO Map (Verified)](#73-gpio-map-verified)
- [8. Software Stack](#8-software-stack)
- [9. Repository Structure (Abstract)](#9-repository-structure-abstract)
- [10. Vision Models](#10-vision-models)
  - [10.1 Model Responsibilities](#101-model-responsibilities)
  - [10.2 Model Overview (Walk-Sign Branch)](#102-model-overview-walk-sign-branch)
  - [10.3 Datasets & Training Workflow](#103-datasets--training-workflow)
  - [10.4 Conversion Environment (Docker Setup)](#104-conversion-environment-docker-setup)
- [11. Astra Board Setup + Deployment (Step-by-Step Commands)](#11-astra-board-setup--deployment-step-by-step-commands)
  - [11.1 Find Board IP (Host PC)](#111-find-board-ip-host-pc)
  - [11.2 SSH into Astra](#112-ssh-into-astra)
  - [11.3 Wi-Fi Setup on Astra (Commands)](#113-wi-fi-setup-on-astra-commands)
  - [11.4 Verify Camera + USB](#114-verify-camera--usb)
  - [11.5 Copy Model Artifacts to Astra (SCP)](#115-copy-model-artifacts-to-astra-scp)
  - [11.6 Verify Model Files on Astra](#116-verify-model-files-on-astra)
  - [11.7 Run Sanity Inference Tests (synap_cli)](#117-run-sanity-inference-tests-synap_cli)
  - [11.8 Run Object-Detection Image Test (synap_cli_od)](#118-run-object-detection-image-test-synap_cli_od)
  - [11.9 Run Your Full Pipeline (Project Code)](#119-run-your-full-pipeline-project-code)
  - [11.10 Optional: Benchmark Run Commands](#1110-optional-benchmark-run-commands)
- [12. Sensors & Feedback](#12-sensors--feedback)
  - [12.1 Ultrasonic Obstacle Alerts (HC-SR04)](#121-ultrasonic-obstacle-alerts-hc-sr04)
  - [12.2 IMU Fall Detection + SOS (Twilio)](#122-imu-fall-detection--sos-twilio)
  - [12.3 Haptics / Buzzer / Optional Audio](#123-haptics--buzzer--optional-audio)
- [13. Benchmarking (Raspberry Pi vs Astra NPU)](#13-benchmarking-raspberry-pi-vs-astra-npu)
- [14. Demo](#14-demo)
- [15. Branch Purpose: `Walk-Sign`](#15-branch-purpose-walk-sign)
- [16. File Reference Summary](#16-file-reference-summary)
- [17. Troubleshooting](#17-troubleshooting)
- [18. Roadmap / Future Work](#18-roadmap--future-work)
- [19. Credits](#19-credits)

---

## 1. Abstract

Visually impaired users often depend on a white cane, which is reliable for detecting ground-level obstacles but does not provide higher-level context like **traffic signals**, **crosswalk states**, or **dynamic hazards** (bikes/vehicles). This project builds a **wearable edge-AI assistant** that adds that missing semantic understanding using a head-mounted camera and on-device inference on the **Synaptics Astra SL1680 (VS680 NPU)**.

The system integrates:
- **3 on-device vision models (INT8)**
- **HC-SR04 ultrasonic ranging** for near-field obstacle safety
- **MPU6050 IMU** for **fall detection**
- **Haptic vibration + audible buzzer** for feedback
- **Twilio SMS SOS** for emergency notification after fall confirmation

All core logic runs **fully on-device**, enabling operation **offline**.

---

## 2. Motivation

The white cane is excellent for:
- detecting curbs, steps, and small obstacles near the ground

But it cannot provide:
- traffic light state (red/yellow/green)
- pedestrian “walk/don’t-walk” signal status
- dynamic hazards and intent cues (approaching bikes/cars)
- mid-level obstacles (truck edges, signboards)

This project addresses these gaps using **vision + sensors + decision logic**, without relying on the cloud.

---

## 3. What the System Does

### A) Vision (3 parallel models, on-device)
From a head-mounted camera stream, three **INT8** models run on Astra NPU to:
- detect **traffic light** state (RED / YELLOW / GREEN)
- recognize **pedestrian signal** state (WALK / DON’T WALK)
- detect **surroundings objects** (people/vehicles/obstacles)

### B) Ultrasonic proximity (near-field safety)
A chest-mounted **HC-SR04**:
- measures distance to obstacles in front of the user
- triggers **haptic vibration** when too close

### C) IMU fall detection + SOS
A wearable **MPU6050**:
- streams acceleration via I²C
- detects a fall-like pattern (free-fall → impact → jerk)
- triggers:
  - **local emergency buzzer**
  - **Twilio SOS SMS** to a preconfigured contact

### D) Feedback
- **Vibration motor**: obstacle proximity cues + navigation cues
- **Buzzer**: loud emergency event (fall confirmed)
- **Optional audio**: spoken semantic cues (traffic/walk state)

---

## 4. High-Level System Behavior

1. The **camera** streams video to Astra SL1680.  
2. Three **vision models** run frame-by-frame and output:
   - traffic light status  
   - pedestrian signal status  
   - surroundings objects  
3. The **ultrasonic sensor** measures distance continuously.  
4. The **IMU** streams motion data and detects fall patterns.  
5. An **FSM** fuses:
   - vision outputs
   - ultrasonic distance
   - IMU fall state  
6. The system triggers feedback patterns:
   - vibration for proximity
   - optional audio for semantics
   - buzzer + SOS SMS on fall confirmation

---

## 5. System Architecture

> Place your images in `assets/images/` and keep these relative links.

- Poster overview  
  ![Poster overview](assets/images/poster_p01.png)

- Layered architecture (sensing → ML → fusion → feedback)  
  ![Architecture](assets/images/report_p09.png)

- Wearable module placement on body  
  ![Wearable system architecture](assets/images/report_p08.png)

---

## 6. Finite State Machine

FSM prevents noisy signals from causing unsafe behavior.

Typical states:
- **WALKING / IDLE**: normal sensing and monitoring
- **OBSTACLE**: ultrasonic threshold triggers vibration patterns
- **CROSSING**: walk + traffic validated, provide safe crossing cue
- **EMERGENCY**: fall detected → buzzer + SOS

![FSM](assets/images/report_p19.png)

---

## 7. Hardware

### 7.1 Hardware at a Glance
- **Synaptics Astra SL1680 (VS680 NPU)**: main compute + NPU inference
- **Head-mounted camera (USB UVC)**: user-view video stream
- **HC-SR04 ultrasonic sensor**: near-field obstacle distance
- **MPU6050 IMU (I²C)**: fall detection
- **Vibration motor**: haptic feedback
- **Buzzer**: emergency audible alert
- **Battery pack + vest integration**: wearable form-factor

### 7.2 Bill of Materials

| Component | Example | Purpose |
|---|---|---|
| Edge AI board | Synaptics Astra SL1680 | Runs inference + fuses sensors |
| Camera | USB UVC webcam | Head-mounted scene input |
| Ultrasonic | HC-SR04 | Distance-to-obstacle sensing |
| IMU | MPU6050 | Fall detection via acceleration |
| Haptics | ERM/LRA + driver | Vibration cues |
| Buzzer | Active buzzer | Emergency alert |
| Power | Battery pack | Portable power |
| Wearable mount | Vest | Secure placement and wiring |

### 7.3 GPIO Map (Verified)

Validated mapping:
> `GPIO number = gpiochip_base + line_offset`

| Function | GPIO |
|---|---:|
| Ultrasonic TRIG | 426 |
| Ultrasonic ECHO | 485 |
| Haptic motor control | 484 |
| Buzzer output | 450 |
| Debug LED | 423 |

---

## 8. Software Stack

### On-device (Astra SL1680)
- **OS**: Synaptics Yocto Linux BSP
- **Runtime**: SyNAP runtime (`.synap` NPU binaries)
- **Vision pipeline**: camera → preprocess → inference → postprocess → FSM
- **Sensors**:
  - GPIO (ultrasonic, haptics, buzzer)
  - I²C (MPU6050)
- **Comms**: Twilio SMS (SOS)

### Development / Training (Host PC)
- **Roboflow**: dataset labeling and export
- **YOLOv8**: training
- **TFLite INT8**: export optimized model
- **Docker (SyNAP SDK)**: conversion to `.synap`
- **Python + OpenCV**: inference pipeline, overlays, benchmarking

---

## 9. Repository Structure (Abstract)

wearable-navigation/
├── README.md
├── assets/ # images, diagrams, demo media
├── docs/ # report/poster + supporting documents
├── models/ # .synap models + labels + metadata
├── src/ # vision + sensors + FSM + feedback + SMS
├── scripts/ # setup + deployment + benchmarking helpers
└── Walk-Sign/ # dedicated model conversion template (branch/dir)

---

## 10. Vision Models

### 10.1 Model Responsibilities
This project uses **three smaller models** rather than one large model because it improves:
- modular debugging (each model has a clear purpose)
- deployment flexibility (swap one model without retraining everything)
- compute stability (tight control on NPU usage and latency)

Models:
1. **Traffic Light**: red/yellow/green  
2. **Walk-Sign**: walk/don’t-walk + crosswalk related classes  
3. **Surroundings**: general objects (people, vehicles, obstacles)  

---

### 10.2 Model Overview (Walk-Sign Branch)

**Base model:** `capstone-synap_v1.tflite` (Roboflow export, trained on traffic/crosswalk images)  
**Converted model:** `model.synap` generated using Synaptics SDK tools inside Docker  
**Input shape:** `224 × 224 × 3` (RGB, INT8)  
**Output tensor:** `[1, 11, 1029]` — detection head (raw bounding boxes + confidence)  

**Labels (9 classes):**
- Crosswalk  
- Don’t Walk  
- Green  
- Red  
- Traffic Signal  
- Walk  
- Yellow  
- Null  

---

### 10.3 Datasets & Training Workflow

Typical workflow:
1. collect + label images in Roboflow  
2. train YOLOv8 (traffic / walk-signal / surroundings)  
3. export to **INT8 TFLite**  
4. convert TFLite → `.synap`  
5. deploy and validate on Astra (image tests + live video)

![Dataset + training flow](assets/images/report_p16.png)

---

### 10.4 Conversion Environment (Docker Setup)

#### 1️⃣ Launch the Synaptics SDK Docker image

```bash
docker run -it --rm \
  -v D:/Synap:/workspace \
  synapticsas/synap-sdk:1.7 \
  /bin/bash



## 2️⃣ Inside Docker – Convert `.tflite` → `.synap`

Inside the Synaptics SDK Docker container, convert the INT8 TFLite model into a VS680-compatible `.synap` binary.

```bash
cd /workspace
synap convert \
  --model capstone-synap_v1.tflite \
  --target VS680 \
  --out-dir out/rf_v1

This generates the following artifacts inside out/rf_v1/:

    model.synap

    model_info.txt

    (optional) labels.txt

11. Astra Board Setup + Deployment (Step-by-Step Commands)

    Replace placeholders like <BOARD_IP> and <SSID> with your actual values.

11.1 SSH into Astra

ssh root@<BOARD_IP>

11.2 Wi-Fi Setup on Astra

Bring up the Wi-Fi interface and obtain an IP address.

ip link set wlan0 up
wpa_supplicant -B -i wlan0 -c /etc/wpa_supplicant.conf
udhcpc -i wlan0

Verify connectivity:

ip addr show wlan0
ping -c 3 8.8.8.8

11.3 Copy Models to Astra

From the host PC, copy the converted model directory to the Astra board:

scp -r out/rf_v1 root@<BOARD_IP>:/home/root/models/

11.4 Sanity Test (On Astra)

On the Astra board, verify inference works.

cd /home/root/models/rf_v1

# Run inference with random input
synap_cli -m model.synap random

# Run object-detection inference on a test image
synap_cli_od -m model.synap red.jpg --out red_out.jpg

If needed, copy the output image back to the host:

scp root@<BOARD_IP>:/home/root/models/rf_v1/red_out.jpg .

12. Sensors & Feedback

    Ultrasonic sensor → haptic proximity alerts

    IMU (MPU6050) → fall detection → buzzer + SMS (Twilio)

    Optional audio → semantic feedback (traffic light / walk signal)

13. Benchmarking

Benchmark results and plots are documented in the project report and included in the assets/images/ directory.
14. Demo

🎥 Demo video:
PASTE_YOUR_DEMO_VIDEO_LINK_HERE
15. Branch Purpose: Walk-Sign

The Walk-Sign branch is dedicated to:

    Hosting Synaptics model artifacts (.synap)

    Demonstrating end-to-end conversion and deployment

    Providing a reusable template for future object-detection models on Astra

16. Troubleshooting

    Reconvert the model if you see “Unknown object detection format”

    Verify GPIO export/unexport if sensors do not respond

    Check camera availability at /dev/video0

17. Roadmap / Future Work

    GStreamer-based live camera pipeline

    Improved fall detection tuning

    Custom PCB and enclosure

    Field testing with visually impaired users

18. Credits
Project Team

    Prateeksha Ranjan

    Hridya Satish Pisharady

    Yash Daniel Ingle

Advisors

    Prof. Salma Elmalaki

    Prof. Quoc-Viet Dang

    Sauryadeep Pal (Synaptics AI Solutions Engineer)

University of California, Irvine — MECPS Capstone
