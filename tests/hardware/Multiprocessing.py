import time
import multiprocessing as mp
from pathlib import Path
import gpiod
from gpiod.line import Direction, Value
from smbus2 import SMBus
import math

# ---------------- GPIO MAP -----------------
TRIG = 10
ECHO = 37
MOTOR = 36
BUZZER = 39

# -------- libgpiod helpers ----------
def get_chip_and_line(gpio_id):
    if 0 <= gpio_id < 32:
        addr = "f7e82400"
        line = gpio_id
    elif 32 <= gpio_id < 64:
        addr = "f7e80800"
        line = gpio_id - 32
    elif 64 <= gpio_id < 96:
        addr = "f7e80c00"
        line = gpio_id - 64
    else:
        raise ValueError("invalid gpio")

    for dev in Path("/dev").glob("gpiochip*"):
        with gpiod.Chip(str(dev)) as chip:
            if addr in chip.get_info().label:
                return str(dev), line

    raise RuntimeError("chip not found")

class GPIO:
    def __init__(self, gpio_id, direction):
        chip, line = get_chip_and_line(gpio_id)
        cfg = { line: gpiod.LineSettings(direction=direction) }
        self.req = gpiod.request_lines(chip, config=cfg)
        self.line = line
        self.chip = chip
        self.req.set_value(self.line, Value.INACTIVE)

    def read(self):
        return self.req.get_value(self.line)

    def write(self, val):
        self.req.set_value(self.line, val)

    def pulse(self, us):
        self.write(Value.ACTIVE)
        time.sleep(us/1_000_000)
        self.write(Value.INACTIVE)

# -----------------------------------------------------------
# PROCESS 1 — Ultrasonic + Motor
# -----------------------------------------------------------
def ultrasonic_process(queue, pause_flag):

    trig = GPIO(TRIG, Direction.OUTPUT)
    echo = GPIO(ECHO, Direction.INPUT)
    motor = GPIO(MOTOR, Direction.OUTPUT)

    while True:

        if pause_flag.value == 1:
            motor.write(Value.INACTIVE)
            time.sleep(0.1)
            continue

        trig.write(Value.INACTIVE)
        time.sleep(0.01)
        trig.pulse(10)

        start = time.time()
        timeout = start + 0.2
        while echo.read() == 0:
            if time.time() > timeout:
                queue.put(("ultra", None))
                break
        else:
            t1 = time.time()
            timeout = t1 + 0.2
            while echo.read() == 1:
                if time.time() > timeout:
                    t1 = None
                    break
            t2 = time.time()

            if t1 is None:
                queue.put(("ultra", None))
            else:
                dist = ((t2 - t1) * 34300) / 2
                queue.put(("ultra", dist))

                if dist < 20:
                    motor.write(Value.ACTIVE)
                else:
                    motor.write(Value.INACTIVE)

        time.sleep(0.1)

# -----------------------------------------------------------
# PROCESS 2 — MPU6050 + Buzzer
# -----------------------------------------------------------
def mpu_process(queue, pause_flag):

    bus = SMBus(0)
    MPU = 0x68
    bus.write_byte_data(MPU, 0x6B, 0)

    buzzer = GPIO(BUZZER, Direction.OUTPUT)

    prev = (0,0,0)

    while True:
        ax = read_word(bus, 0x3B)/16384.0
        ay = read_word(bus, 0x3D)/16384.0
        az = read_word(bus, 0x3F)/16384.0

        mag = math.sqrt(ax*ax + ay*ay + az*az)

        if mag < 0.3:        # freefall
            queue.put(("fall", "freefall"))
        if mag > 3.0:        # impact
            buzzer.write(Value.ACTIVE)
            pause_flag.value = 1
            time.sleep(3)
            buzzer.write(Value.INACTIVE)
            time.sleep(15)
            pause_flag.value = 0

        time.sleep(0.01)

def read_word(bus, reg):
    hi = bus.read_byte_data(0x68, reg)
    lo = bus.read_byte_data(0x68, reg+1)
    v = (hi<<8) | lo
    return v - 65536 if v>=0x8000 else v

# -----------------------------------------------------------
# PROCESS 3 — MAIN FSM
# -----------------------------------------------------------
if __name__ == "__main__":

    queue = mp.Queue()
    pause_flag = mp.Value('i', 0)

    p1 = mp.Process(target=ultrasonic_process, args=(queue, pause_flag))
    p2 = mp.Process(target=mpu_process, args=(queue, pause_flag))

    p1.start()
    p2.start()

    try:
        while True:
            src, data = queue.get()
            print("[EVENT]", src, data)

    except KeyboardInterrupt:
        p1.terminate()
        p2.terminate()
        print("Clean exit")

