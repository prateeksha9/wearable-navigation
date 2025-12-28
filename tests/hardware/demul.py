#!/usr/bin/env python3
"""
Wearable Navigation – Multithreaded GPIO Demo

- Uses sysfs GPIO on Astra SL1680
- Pins used (edit as needed):
    * BUZZER_PIN      -> GPIO 426
    * LEFT_HAPTIC_PIN -> GPIO 484
    * RIGHT_HAPTIC_PIN-> GPIO 485

Threads:
    - heartbeat_thread: pulses BUZZER every 1 second
    - left_haptic_thread: short pulse every 3 seconds
    - right_haptic_thread: short pulse every 5 seconds

All GPIO exports are:
    - cleaned on startup (if stale)
    - idempotent and tolerant to EBUSY
"""

import os
import errno
import time
import threading
import signal
import sys

# ===================== GPIO CONFIG =====================

GPIO_BASE_PATH = "/sys/class/gpio"
EXPORT_PATH    = os.path.join(GPIO_BASE_PATH, "export")
UNEXPORT_PATH  = os.path.join(GPIO_BASE_PATH, "unexport")

# Edit these to match your wiring
BUZZER_PIN       = 426
LEFT_HAPTIC_PIN  = 484
RIGHT_HAPTIC_PIN = 485

ALL_PINS = [BUZZER_PIN, LEFT_HAPTIC_PIN, RIGHT_HAPTIC_PIN]

# Global stop flag
running = True

# Simple lock to avoid concurrent writes to same sysfs file
gpio_lock = threading.Lock()


# ===================== GPIO HELPERS =====================

def gpio_path(pin: int, name: str = "") -> str:
    base = os.path.join(GPIO_BASE_PATH, f"gpio{pin}")
    return base if not name else os.path.join(base, name)


def export_gpio(pin: int):
    """
    Idempotent export:
    - If gpioX already exists: skip
    - If export gives EBUSY: treat as 'already exported'
    """
    path = gpio_path(pin)
    if os.path.exists(path):
        print(f"[GPIO INIT] GPIO {pin} already exported, skipping.")
        return

    try:
        with open(EXPORT_PATH, "w") as f:
            f.write(str(pin))
        print(f"[GPIO INIT] GPIO {pin} exported successfully.")
    except OSError as e:
        if e.errno == errno.EBUSY:
            print(f"[GPIO INIT] GPIO {pin} export EBUSY (already in use?), continuing.")
        else:
            print(f"[GPIO ERROR] Failed to export GPIO {pin}: {e}")
            raise


def unexport_gpio(pin: int):
    """
    Safe unexport:
    - If gpioX doesn't exist: skip
    - Ignore EINVAL (not exported) errors
    """
    path = gpio_path(pin)
    if not os.path.exists(path):
        # nothing to do
        return

    try:
        with open(UNEXPORT_PATH, "w") as f:
            f.write(str(pin))
        print(f"[CLEANUP] Unexported GPIO {pin}")
    except OSError as e:
        # Some kernels throw EINVAL if pin is not exported
        if e.errno in (errno.EINVAL, errno.ENOENT):
            print(f"[CLEANUP] GPIO {pin} not exported (EINVAL/ENOENT), skipping.")
        else:
            print(f"[CLEANUP ERROR] Failed to unexport GPIO {pin}: {e}")


def set_gpio_direction(pin: int, direction: str):
    """
    direction: "in" or "out"
    """
    dir_path = gpio_path(pin, "direction")
    try:
        with open(dir_path, "w") as f:
            f.write(direction)
        print(f"[GPIO INIT] GPIO {pin} direction set to {direction}")
    except OSError as e:
        print(f"[GPIO ERROR] Failed to set direction on GPIO {pin}: {e}")
        # Decide if you want to raise here; for demo we just log.


def write_gpio_value(pin: int, value: int):
    """
    value: 0 or 1
    Thread-safe write.
    """
    val_path = gpio_path(pin, "value")
    try:
        with gpio_lock:
            with open(val_path, "w") as f:
                f.write("1" if value else "0")
    except OSError as e:
        print(f"[GPIO ERROR] Failed to write value to GPIO {pin}: {e}")


def init_gpio_pins():
    """
    Full init:
    - Clean up stale exports
    - Export pins (idempotent)
    - Set as outputs
    - Initialize to low
    """
    print("[SYSTEM] GPIO cleanup & init starting...")

    # Cleanup stale ones first
    for pin in ALL_PINS:
        if os.path.exists(gpio_path(pin)):
            print(f"[CLEANUP INIT] Unexporting stale GPIO {pin}")
            unexport_gpio(pin)

    # Export and configure
    for pin in ALL_PINS:
        export_gpio(pin)
        set_gpio_direction(pin, "out")
        write_gpio_value(pin, 0)

    print("[SYSTEM] GPIO init complete.")


def cleanup_all():
    """
    Called on shutdown: turn off outputs and unexport pins.
    """
    print("[SYSTEM] Cleanup starting...")

    for pin in ALL_PINS:
        write_gpio_value(pin, 0)
        unexport_gpio(pin)

    print("[SYSTEM] Cleanup done.")


# ===================== THREAD FUNCTIONS =====================

def heartbeat_thread():
    """
    Pulses buzzer (or LED) at 1 Hz to show system is alive.
    """
    print("[THREAD] Heartbeat thread started.")
    state = 0
    while running:
        state ^= 1
        write_gpio_value(BUZZER_PIN, state)
        time.sleep(1.0)

    # Ensure off on exit
    write_gpio_value(BUZZER_PIN, 0)
    print("[THREAD] Heartbeat thread exiting.")


def left_haptic_thread():
    """
    Example: short pulse every 3 seconds.
    Replace with your real navigation logic.
    """
    print("[THREAD] Left haptic thread started.")
    while running:
        # simulate a short haptic pulse
        write_gpio_value(LEFT_HAPTIC_PIN, 1)
        time.sleep(0.2)
        write_gpio_value(LEFT_HAPTIC_PIN, 0)
        # rest
        for _ in range(30):
            if not running:
                break
            time.sleep(0.1)

    write_gpio_value(LEFT_HAPTIC_PIN, 0)
    print("[THREAD] Left haptic thread exiting.")


def right_haptic_thread():
    """
    Example: short pulse every 5 seconds.
    Replace with your real navigation logic.
    """
    print("[THREAD] Right haptic thread started.")
    while running:
        write_gpio_value(RIGHT_HAPTIC_PIN, 1)
        time.sleep(0.2)
        write_gpio_value(RIGHT_HAPTIC_PIN, 0)
        # rest
        for _ in range(50):
            if not running:
                break
            time.sleep(0.1)

    write_gpio_value(RIGHT_HAPTIC_PIN, 0)
    print("[THREAD] Right haptic thread exiting.")


# ===================== SIGNAL HANDLING =====================

def signal_handler(signum, frame):
    global running
    print(f"\n[SIGNAL] Caught signal {signum}, shutting down...")
    running = False


# ===================== MAIN =====================

def main():
    global running

    print("[SYSTEM] Starting Wearable Navigation System (demo multithread)...")

    # Register Ctrl+C handler
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # GPIO init (idempotent, EBUSY-safe)
    init_gpio_pins()

    # Start threads
    threads = []
    threads.append(threading.Thread(target=heartbeat_thread, daemon=True))
    threads.append(threading.Thread(target=left_haptic_thread, daemon=True))
    threads.append(threading.Thread(target=right_haptic_thread, daemon=True))

    for t in threads:
        t.start()

    # Main loop just waits until running == False
    try:
        while running:
            time.sleep(0.5)
    finally:
        # Join threads
        print("[SYSTEM] Joining threads...")
        running = False
        for t in threads:
            t.join(timeout=1.0)

        # Cleanup GPIO
        cleanup_all()
        print("[SYSTEM] Exit complete.")


if __name__ == "__main__":
    # Allow running as script:
    # (myenv) python3 tests/hardware/demultithread.py
    try:
        main()
    except KeyboardInterrupt:
        # Redundant, but safe
        print("\n[MAIN] KeyboardInterrupt - exiting.")
        running = False
        cleanup_all()
        sys.exit(0)
