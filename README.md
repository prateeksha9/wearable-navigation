# Edge-AI Navigation Assistant on Synaptics Astra SL1680

This project is a wearable navigation and safety assistant for visually impaired users, built on the **Synaptics Astra SL1680 (VS680 NPU)** edge-AI platform. It combines embedded computer vision, ultrasonic distance sensing, and IMU-based fall detection into a single, fully on-device system. The aim is to **enhance**, not replace, the white cane by adding scene understanding and safety alerts.

---

## Project Overview

Visually impaired users often rely on a white cane, which is excellent for detecting obstacles at ground level but offers no information about:

- Traffic lights and their current state  
- Pedestrian crossing signals  
- Moving vehicles, bikes, and other dynamic obstacles  
- Overhead or mid-level obstacles (e.g., signboards, edges of trucks, etc.)

This project addresses those gaps by using a **head-mounted camera** connected to the Astra SL1680 board, running multiple AI models on the NPU to understand the environment in real time. The system then provides **intuitive feedback** through a **vibration motor** (and optionally audio) and can trigger an **SOS alert** if a fall is detected.

---

## What the System Does

At a high level, the wearable system:

- Uses a **camera** to capture the user’s surroundings and runs **three vision models** on the Astra’s NPU to:
  - Detect the state of **traffic lights** (e.g., red / yellow / green)
  - Recognize **pedestrian signals** (e.g., WALK / DON’T WALK)
  - Identify critical objects in the **surroundings** (e.g., people, vehicles, obstacles)

- Uses an **ultrasonic distance sensor** on the vest to:
  - Measure the distance to near-field obstacles directly in front of the user
  - Trigger haptic feedback when the user is too close to an obstacle

- Uses an **IMU sensor** on the vest to:
  - Monitor motion and orientation
  - Detect potential **fall events** based on sudden changes in acceleration and movement

- Uses a **vibration motor and buzzer**:
  - To indicate obstacle proximity and navigation cues
  - To signal when it is unsafe or safe to cross a street
  - To give distinct patterns for special events (e.g., fall detected), where the **buzzer sounds loudly** to alert nearby people

- Can send an **SOS alert** via **Twilio SMS** if a fall is detected and not canceled:
  - A **text message** is sent to a **preconfigured emergency contact or close connection**
  - At the same time, the **buzzer goes off** to alert people nearby that the user may need help

All of this runs **locally on the Astra SL1680 board**, so the system can operate **offline** and does not need a continuous internet connection for its core navigation behavior.

---

## Hardware at a Glance

The main hardware components in the project are:

- **Synaptics Astra SL1680 (VS680) board**  
  The central embedded AI platform that runs the vision models on its NPU and coordinates all sensors and outputs.

- **Head-mounted camera**  
  Mounted on a cap, visor, or headband and connected to Astra. It provides a live video feed aligned with the user’s view.

- **Ultrasonic distance sensor**  
  Mounted on the vest and facing forward, it measures the distance to obstacles in front of the user to give short-range safety information.

- **IMU sensor**  
  Firmly attached to the vest, it tracks motion and orientation. Its data is used to infer whether the user has fallen.

- **Vibration motor and buzzer**  
  The vibration motor provides discreet haptic feedback for navigation and proximity alerts. The buzzer provides **audible alerts**, especially during **fall events**, so that people nearby are alerted while the system sends an SOS SMS to the emergency contact.

- **Battery pack and wiring inside a vest**  
  Powers the Astra board, camera, sensors, and feedback devices, and is all integrated into a wearable vest-form factor.

---

## High-Level System Behavior

1. The **camera** streams video to the Astra SL1680.  
2. The **three vision models** run on the NPU, frame by frame, and output:
   - Traffic light status  
   - Pedestrian signal status  
   - Surroundings / objects of interest  

3. The **ultrasonic sensor** continuously measures distance in front of the user and identifies when something is too close.  

4. The **IMU** continuously reports motion data, which is used to detect patterns that look like a fall (e.g., sudden impact followed by little movement).  

5. A **finite state machine (FSM)** combines:
   - The outputs of the three vision models  
   - Ultrasonic distance  
   - IMU-based motion / fall state  

   and decides what “state” the system is in (e.g., normal walking, near obstacle, waiting to cross, safe to cross, fall detected).

6. Based on the current state, the system activates the **vibration motor** (and buzzer/audio) with different patterns. In the case of a **fall detected and confirmed**:
   - The **buzzer is activated** to draw attention from people nearby.  
   - An **SOS SMS is sent via Twilio** to a configured emergency contact, providing a remote alert that the user may need help.

This design keeps inference and decision-making **on the edge**, enabling faster and more reliable responses than a cloud-dependent solution.

---

## Synaptics Astra SL1680 Board Layout

*(Add your own image file link below – for example an exported board layout / top view of the Astra board)*

![Synaptics Astra SL1680 Board Layout]()

---

## Final Assembled Circuit (Soldered)

*(Add your own image file link below – for example the fully soldered circuit or assembly in your project)*

![Final Assembled Circuit]()

---

## Wearable Vest with Integrated System

*(Add your own image file link below – for example a photo of the vest being worn or laid out flat with components visible)*

![Wearable Vest Front View]()

---

## System FSM Diagram

*(Add your own image file link below – for example the finite state machine diagram exported from your poster or slides)*

![System FSM Diagram]()

---

## Demo Video

*(Paste your demo video URL in the link below)*

[👉 Watch the demo video here](PASTE_YOUR_DEMO_VIDEO_LINK_HERE)

---

## Credits

**Project Team**  
- Prateeksha Ranjan  
- Hridya Satish Pisharady  
- Yash Daniel Ingle  

**Advisors / Mentors**  
- Prof. Salma Elmalaki  
- Prof. Quoc-Viet Dang  
- Sauryadeep Pal (Synaptics AI Solutions Engineer)  

Project completed as part of the MECPS capstone at the University of California, Irvine.
```
