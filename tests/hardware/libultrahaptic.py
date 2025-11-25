from pathlib import Path
import time
import csv
import gpiod
from gpiod.line import Direction, Value

TRIG = 10
ECHO = 37
MOTOR = 39  # <-- this will fail on Astra

def get_address_info(gpio_id):
    if 0 <= gpio_id < 32:
        return "f7e82400", gpio_id
    elif 32 <= gpio_id < 64:
        return "f7e80800", gpio_id - 32
    elif 64 <= gpio_id < 96:
        return "f7e80c00", gpio_id - 64
    else:
        raise ValueError("Invalid GPIO")

def get_gpio_chip(address):
    for dev in Path("/dev").glob("gpio*"):
        with gpiod.Chip(str(dev)) as chip:
            if address in chip.get_info().label:
                return str(dev)
    raise RuntimeError("Chip not found")

def get_gpio(gpio_id):
    address, line = get_address_info(gpio_id)
    chip = get_gpio_chip(address)
    return chip, line

class GPIO:
    def __init__(self, chip, line):
        self.chip = chip
        self.line = line

    def write(self, val):
        try:
            with gpiod.request_lines(
                self.chip,
                config={self.line: gpiod.LineSettings(direction=Direction.OUTPUT)}
            ) as req:
                req.set_value(self.line, val)
        except Exception as e:
            print(f"[ERROR] MOTOR GPIO FAILED: {e}")

    def read(self):
        with gpiod.request_lines(
            self.chip,
            config={self.line: gpiod.LineSettings(direction=Direction.INPUT)}
        ) as req:
            return req.get_value(self.line)

    def pulse(self, duration):
        with gpiod.request_lines(
            self.chip,
            config={self.line: gpiod.LineSettings(direction=Direction.OUTPUT)}
        ) as req:
            req.set_value(self.line, Value.ACTIVE)
            time.sleep(duration)
            req.set_value(self.line, Value.INACTIVE)

    def wait_for(self, target, timeout):
        deadline = time.monotonic_ns() + int(timeout * 1e9)
        with gpiod.request_lines(
            self.chip,
            config={self.line: gpiod.LineSettings(direction=Direction.INPUT)}
        ) as req:
            while time.monotonic_ns() < deadline:
                if req.get_value(self.line) == target:
                    return time.monotonic_ns()
        return None

def measure_distance(trig, echo):
    trig.write(Value.INACTIVE)
    time.sleep(0.01)

    trig.pulse(10e-6)
    start = echo.wait_for(Value.ACTIVE, 0.2)
    if start is None:
        return None
    end = echo.wait_for(Value.INACTIVE, 0.2)
    if end is None:
        return None
    dt = (end - start) / 1e9
    return (dt * 34300) / 2


# ---------------------------------------------------
# MAIN
# ---------------------------------------------------
trig_chip, trig_line = get_gpio(TRIG)
echo_chip, echo_line = get_gpio(ECHO)
motor_chip, motor_line = get_gpio(MOTOR)

trig = GPIO(trig_chip, trig_line)
echo = GPIO(echo_chip, echo_line)
motor = GPIO(motor_chip, motor_line)

csv_file = open("ultra_motor_libgpiod.csv", "w", newline="")
w = csv.writer(csv_file)
w.writerow(["timestamp", "distance_cm", "motor_state"])

print("[INFO] Running ultrasonic + motor (may fail)...")

try:
    while True:
        dist = measure_distance(trig, echo)
        ts = time.strftime("%H:%M:%S")

        if dist and dist < 20:
            motor.write(Value.ACTIVE)
            state = 1
        else:
            motor.write(Value.INACTIVE)
            state = 0

        w.writerow([ts, dist if dist else "None", state])
        csv_file.flush()

        print(f"{ts} dist={dist}, motor={state}")

        time.sleep(0.1)

except KeyboardInterrupt:
    print("Stopping...")

finally:
    csv_file.close()
    print("[INFO] CSV saved.")

