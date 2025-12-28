import os, time, math, threading, signal, sys, errno
from smbus2 import SMBus

# ----------------- GPIO DEFINITIONS -----------------
TRIG_GPIO   = 426
ECHO_GPIO   = 485
MOTOR_GPIO  = 484
BUZZER_GPIO = 487

# Concurrency primitives
sem = threading.Semaphore(1)
stop_event = threading.Event()
pause_ultrasonic = threading.Event()
lock = threading.Lock()          # for obstacle_detected / last_seen
gpio_lock = threading.Lock()     # for GPIO sysfs writes
obstacle_detected = False
last_seen = 0

# ----------------- PATH HELPERS -----------------
def gpio_path(pin):
    return f"/sys/class/gpio/gpio{pin}"

EXPORT_PATH   = "/sys/class/gpio/export"
UNEXPORT_PATH = "/sys/class/gpio/unexport"

# ----------------- GPIO HELPERS -----------------
def export_gpio(pin):
    """
    Idempotent + EBUSY-safe export:
    - If /sys/class/gpio/gpioN exists -> skip
    - If export returns EBUSY -> treat as 'already exported'
    """
    path = gpio_path(pin)

    # Already exported
    if os.path.exists(path):
        print(f"[GPIO INIT] GPIO {pin} already exported, skipping.")
        return path

    try:
        with open(EXPORT_PATH, "w") as f:
            f.write(str(pin))
        # Give sysfs a moment to create the directory
        time.sleep(0.05)
    except OSError as e:
        if e.errno == errno.EBUSY:
            # Some other consumer already exported it
            print(f"[GPIO INIT] GPIO {pin} export EBUSY (already in use?), continuing.")
        else:
            print(f"[GPIO ERROR] Failed to export GPIO {pin}: {e}")
            raise

    if os.path.exists(path):
        print(f"[GPIO INIT] GPIO {pin} exported successfully.")
    else:
        print(f"[GPIO WARN] GPIO {pin} export attempted but path not found yet.")

    return path


def unexport_gpio(pin):
    """
    Safe unexport:
    - If gpioN dir doesn't exist -> skip
    - Ignore EINVAL/ENOENT (already unexported)
    """
    path = gpio_path(pin)
    if not os.path.exists(path):
        return

    try:
        with open(UNEXPORT_PATH, "w") as f:
            f.write(str(pin))
        time.sleep(0.02)
        print(f"[GPIO CLEANUP] GPIO {pin} unexported.")
    except OSError as e:
        if e.errno in (errno.EINVAL, errno.ENOENT):
            print(f"[GPIO CLEANUP] GPIO {pin} already unexported (EINVAL/ENOENT), skipping.")
        else:
            print(f"[GPIO CLEANUP ERROR] Failed to unexport GPIO {pin}: {e}")


def set_direction(pin, dirn):
    dir_path = os.path.join(gpio_path(pin), "direction")
    try:
        with open(dir_path, "w") as f:
            f.write(dirn)
        # print(f"[GPIO INIT] GPIO {pin} direction set to {dirn}")
    except OSError as e:
        print(f"[GPIO ERROR] Failed to set direction on GPIO {pin}: {e}")


def write_value(pin, val):
    val_path = os.path.join(gpio_path(pin), "value")
    try:
        with gpio_lock:
            with open(val_path, "w") as f:
                f.write(str(val))
    except OSError as e:
        print(f"[GPIO ERROR] Failed to write value to GPIO {pin}: {e}")


def read_value(pin):
    val_path = os.path.join(gpio_path(pin), "value")
    try:
        with open(val_path) as f:
            return f.read().strip()
    except OSError as e:
        print(f"[GPIO ERROR] Failed to read value from GPIO {pin}: {e}")
        return "0"


# ============================================================
# ==== TARGETED GPIO CLEANUP BEFORE EXPORTING OUR PINS =======
# ============================================================
def force_unexport_all():
    """
    Only unexport *our* pins at startup, not every gpioX on the system.
    """
    for pin in (TRIG_GPIO, ECHO_GPIO, MOTOR_GPIO, BUZZER_GPIO):
        if os.path.exists(gpio_path(pin)):
            try:
                with open(UNEXPORT_PATH, "w") as f:
                    f.write(str(pin))
                print(f"[CLEANUP INIT] Unexported stale GPIO {pin}")
            except Exception as e:
                print(f"[WARN INIT] Could not unexport {pin}: {e}")

# Call the targeted cleanup once at startup
force_unexport_all()
# ============================================================
# ============================================================


# ----------------- ULTRASONIC + HAPTIC -----------------
def measure(trig, echo):
    set_direction(trig, "out")
    set_direction(echo, "in")

    write_value(trig, 0)
    time.sleep(0.05)
    write_value(trig, 1)
    time.sleep(0.00001)
    write_value(trig, 0)

    t0 = time.time()
    while read_value(echo) == "0":
        if time.time() - t0 > 0.2:
            return None
    start = time.time()

    while read_value(echo) == "1":
        if time.time() - start > 0.2:
            return None
    end = time.time()

    return (end - start) * 17150  # cm


def ultrasonic_loop():
    global obstacle_detected, last_seen
    set_direction(MOTOR_GPIO, "out")
    motor_state = False

    while not stop_event.is_set():
        if not pause_ultrasonic.is_set():
            with sem:
                d = measure(TRIG_GPIO, ECHO_GPIO)

            if d:
                print(f"[ULTRASONIC] {d:.1f} cm")
                with lock:
                    if d < 20:
                        obstacle_detected = True
                        last_seen = time.time()
                    elif time.time() - last_seen > 1.5:
                        obstacle_detected = False
            else:
                print("[ULTRASONIC] timeout")

            with lock:
                active = obstacle_detected

            if active and not motor_state:
                write_value(MOTOR_GPIO, 1)
                motor_state = True
                print("[MOTOR] ON")
            elif not active and motor_state:
                write_value(MOTOR_GPIO, 0)
                motor_state = False
                print("[MOTOR] OFF")

        else:
            write_value(MOTOR_GPIO, 0)
            print("[ULTRASONIC] Paused after fall detection.")

        time.sleep(0.2)

    write_value(MOTOR_GPIO, 0)
    print("[MOTOR] forced OFF")


# ----------------- MPU6050 + BUZZER -----------------
MPU_ADDR = 0x68
I2C_BUS = 0
PWR_MGMT_1 = 0x6B
ACCEL_XOUT_H = 0x3B

ACCEL_SCALE = 16384.0
DT = 0.01
FREEFALL_G = 0.3
IMPACT_G = 3.0
JERK_THRESH_GPS = 30.0  # unused but kept for future
FREEFALL_TO_IMPACT = 1.0
COOLDOWN_SEC = 2.0

def export_buzzer():
    export_gpio(BUZZER_GPIO)
    set_direction(BUZZER_GPIO, "out")

def beep_buzzer(duration=3):
    print("[BUZZER] Beeping...")
    write_value(BUZZER_GPIO, 1)
    time.sleep(duration)
    write_value(BUZZER_GPIO, 0)
    print("[BUZZER] Done.")

def read_word(bus, reg):
    hi = bus.read_byte_data(MPU_ADDR, reg)
    lo = bus.read_byte_data(MPU_ADDR, reg+1)
    val = (hi << 8) + lo
    return val - 65536 if val >= 0x8000 else val

def get_accel(bus):
    ax = read_word(bus, ACCEL_XOUT_H)   / ACCEL_SCALE
    ay = read_word(bus, ACCEL_XOUT_H+2) / ACCEL_SCALE
    az = read_word(bus, ACCEL_XOUT_H+4) / ACCEL_SCALE
    return ax, ay, az

def magnitude(x,y,z):
    return math.sqrt(x*x + y*y + z*z)

def mpu6050_loop():
    export_buzzer()

    with SMBus(I2C_BUS) as bus:
        bus.write_byte_data(MPU_ADDR, PWR_MGMT_1, 0)

        prev_ax = prev_ay = prev_az = 0
        cooldown_until = 0
        state = "idle"
        freefall_start = 0

        print("[START] MPU + Buzzer Fall Detection Running...")

        while not stop_event.is_set():

            with sem:
                ax, ay, az = get_accel(bus)

            a_mag = magnitude(ax, ay, az)
            jx = (ax - prev_ax) / DT
            jy = (ay - prev_ay) / DT
            jz = (az - prev_az) / DT
            jerk = magnitude(jx, jy, jz)  # currently unused, kept for tuning
            prev_ax, prev_ay, prev_az = ax, ay, az

            now = time.monotonic()

            if now < cooldown_until:
                time.sleep(DT)
                continue

            if state == "idle" and a_mag < FREEFALL_G:
                state = "freefall"
                freefall_start = now
                print("[DETECT] Freefall suspected...")

            elif state == "freefall":
                if a_mag > IMPACT_G and (now - freefall_start) <= FREEFALL_TO_IMPACT:
                    print("[FALL] Impact confirmed — Fall detected!")
                    beep_buzzer(duration=3)
                    pause_ultrasonic.set()
                    cooldown_until = now + COOLDOWN_SEC
                    state = "idle"
                    print("[SYSTEM] Ultrasonic paused for 15 seconds...")
                    time.sleep(15)
                    pause_ultrasonic.clear()
                    print("[SYSTEM] Ultrasonic resumed.")
                elif (now - freefall_start) > FREEFALL_TO_IMPACT:
                    state = "idle"

            time.sleep(DT)

    unexport_gpio(BUZZER_GPIO)


# ----------------- CLEANUP HANDLER -----------------
def cleanup(sig=None, frame=None):
    print("\n[CLEANUP] Stopping threads and unexporting GPIOs...")
    stop_event.set()

    for pin in (TRIG_GPIO, ECHO_GPIO, MOTOR_GPIO, BUZZER_GPIO):
        try:
            write_value(pin, 0)
        except Exception:
            pass
        unexport_gpio(pin)

    print("[CLEANUP] All GPIOs unexported. Exiting safely.")
    sys.exit(0)

signal.signal(signal.SIGINT, cleanup)


# ----------------- MAIN EXECUTION -----------------
if __name__ == "__main__":
    print("[SYSTEM] Starting Wearable Navigation System...")

    # Export our GPIOs once (idempotent, EBUSY-safe)
    for pin in (TRIG_GPIO, ECHO_GPIO, MOTOR_GPIO, BUZZER_GPIO):
        export_gpio(pin)

    t1 = threading.Thread(target=ultrasonic_loop, daemon=True)
    t2 = threading.Thread(target=mpu6050_loop, daemon=True)
    t1.start()
    t2.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        cleanup()
