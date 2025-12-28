import os
import time

# ✅ GPIO assignments from verified mapping
TRIG_GPIO = 426  # GPIO10 → Pin 12
ECHO_GPIO = 485  # GPIO37 → Pin 22

def export_gpio(pin):
    gpio_path = f"/sys/class/gpio/gpio{pin}"
    if not os.path.exists(gpio_path):
        try:
            with open("/sys/class/gpio/export", "w") as f:
                f.write(str(pin))
            time.sleep(0.1)  # Give time to create files
            print(f"[INFO] Exported GPIO {pin}")
        except Exception as e:
            print(f"[ERROR] Could not export GPIO {pin}: {e}")
            return None
    return gpio_path

def unexport_gpio(pin):
    gpio_path = f"/sys/class/gpio/gpio{pin}"
    if os.path.exists(gpio_path):
        try:
            with open("/sys/class/gpio/unexport", "w") as f:
                f.write(str(pin))
            print(f"[INFO] Unexported GPIO {pin}")
        except Exception as e:
            print(f"[ERROR] Could not unexport GPIO {pin}: {e}")

def set_direction(pin_path, direction):
    try:
        with open(os.path.join(pin_path, "direction"), "w") as f:
            f.write(direction)
        print(f"[DEBUG] Set direction of {pin_path} to {direction}")
    except Exception as e:
        print(f"[ERROR] Failed to set direction: {e}")

def write_value(pin_path, value):
    try:
        with open(os.path.join(pin_path, "value"), "w") as f:
            f.write(str(value))
        print(f"[DEBUG] Wrote value {value} to {pin_path}")
    except Exception as e:
        print(f"[ERROR] Failed to write value: {e}")

def read_value(pin_path):
    try:
        with open(os.path.join(pin_path, "value"), "r") as f:
            val = f.read().strip()
        return val
    except Exception as e:
        print(f"[ERROR] Failed to read value: {e}")
        return "0"

def measure_distance():
    trig_path = export_gpio(TRIG_GPIO)
    echo_path = export_gpio(ECHO_GPIO)

    if not trig_path or not echo_path:
        return None

    set_direction(trig_path, "out")
    set_direction(echo_path, "in")

    print("[DEBUG] Ensuring trigger is low")
    write_value(trig_path, 0)
    time.sleep(0.05)

    print("[DEBUG] Sending 10µs trigger pulse")
    write_value(trig_path, 1)
    time.sleep(0.00001)
    write_value(trig_path, 0)

    print("[DEBUG] Waiting for Echo to go HIGH")
    timeout = time.time() + 0.2
    while read_value(echo_path) == "0":
        if time.time() > timeout:
            print("[ERROR] Timeout waiting for Echo to go HIGH")
            return None
    pulse_start = time.time()
    print(f"[DEBUG] Echo went HIGH at {pulse_start:.6f}")

    print("[DEBUG] Waiting for Echo to go LOW")
    timeout = time.time() + 0.2
    while read_value(echo_path) == "1":
        if time.time() > timeout:
            print("[ERROR] Timeout waiting for Echo to go LOW")
            return None
    pulse_end = time.time()
    print(f"[DEBUG] Echo went LOW at {pulse_end:.6f}")

    pulse_duration = pulse_end - pulse_start
    print(f"[DEBUG] Pulse duration: {pulse_duration:.6f} seconds")

    distance_cm = (pulse_duration * 34300) / 2
    return distance_cm

# ✅ Main loop with cleanup
if __name__ == "__main__":
    try:
        while True:
            print("\n[INFO] Starting ultrasonic measurement...")
            distance = measure_distance()
            if distance is None:
                print("[RESULT] ❌ No object detected (timeout).")
            else:
                print(f"[RESULT] ✅ Object detected at {distance:.2f} cm")
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n[INFO] Measurement stopped by user.")

    finally:
        print("[INFO] Cleaning up GPIOs...")
        unexport_gpio(TRIG_GPIO)
        unexport_gpio(ECHO_GPIO)
        print("[INFO] GPIOs successfully unexported.")

