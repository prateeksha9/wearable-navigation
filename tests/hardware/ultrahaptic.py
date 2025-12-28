import os
import time
import threading

# ✅ GPIO assignments
TRIG_GPIO = 426     # TRIG of Ultrasonic
ECHO_GPIO = 485     # ECHO of Ultrasonic
MOTOR_GPIO = 484    # GPIO controlling the haptic motor via NPN transistor

def export_gpio(pin):
    gpio_path = f"/sys/class/gpio/gpio{pin}"
    if not os.path.exists(gpio_path):
        try:
            with open("/sys/class/gpio/export", "w") as f:
                f.write(str(pin))
            time.sleep(0.1)  # Give the system time to export
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
        # print(f"[DEBUG] Wrote value {value} to {pin_path}")
    except Exception as e:
        print(f"[ERROR] Failed to write value: {e}")

def read_value(pin_path):
    try:
        with open(os.path.join(pin_path, "value"), "r") as f:
            return f.read().strip()
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

    write_value(trig_path, 0)
    time.sleep(0.05)

    write_value(trig_path, 1)
    time.sleep(0.00001)
    write_value(trig_path, 0)

    timeout = time.time() + 0.2
    while read_value(echo_path) == "0":
        if time.time() > timeout:
            return None
    pulse_start = time.time()

    timeout = time.time() + 0.2
    while read_value(echo_path) == "1":
        if time.time() > timeout:
            return None
    pulse_end = time.time()

    pulse_duration = pulse_end - pulse_start
    distance_cm = (pulse_duration * 34300) / 2
    return distance_cm

# ✅ Motor Control Thread
def control_motor(stop_event):
    motor_path = export_gpio(MOTOR_GPIO)
    set_direction(motor_path, "out")

    cooldown = 1.5  # seconds to rest motor after activation
    active = False

    while not stop_event.is_set():
        distance = measure_distance()
        if distance is None:
            print("[INFO] No object detected")
        elif distance < 20:
            print(f"[INFO] Object at {distance:.2f} cm — motor ON")
            write_value(motor_path, 1)
            active = True
        else:
            if active:
                print(f"[INFO] Object moved away — motor OFF, cooldown for {cooldown}s")
                write_value(motor_path, 0)
                active = False
                time.sleep(cooldown)
            else:
                write_value(motor_path, 0)
                print(f"[INFO] Distance {distance:.2f} cm — motor remains OFF")

        time.sleep(0.3)

# ✅ Main loop
if __name__ == "__main__":
    stop_event = threading.Event()
    try:
        motor_thread = threading.Thread(target=control_motor, args=(stop_event,))
        motor_thread.start()
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n[INFO] Stopping program...")

    finally:
        stop_event.set()
        motor_thread.join()
        unexport_gpio(TRIG_GPIO)
        unexport_gpio(ECHO_GPIO)
        unexport_gpio(MOTOR_GPIO)
        print("[INFO] GPIOs successfully unexported.")

