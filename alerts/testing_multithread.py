# combined_ultrasonic_mpu6050_pi_extended.py
import RPi.GPIO as GPIO
import smbus2, math, time, csv, datetime, threading, statistics, psutil, os

# --- GPIO pins (BCM numbering) ---
TRIG, ECHO, MOTOR, BUZZER = 23, 24, 18, 25

# --- MPU6050 parameters ---
MPU_ADDR = 0x68
ACCEL_XOUT_H = 0x3B
PWR_MGMT_1 = 0x6B
ACCEL_SCALE = 16384.0
DT = 0.01
FREEFALL_G, IMPACT_G = 0.15, 5
JERK_THRESH_GPS = 80.0
COOLDOWN_SEC = 2.0
MIN_FREEFALL_TIME = 0.20

# --- Global control ---
stop_event = threading.Event()
lock = threading.Lock()
fall_detected = False
cooldown_until = 0

# --- GPIO setup ---
GPIO.setmode(GPIO.BCM)
for p in (TRIG, MOTOR, BUZZER):
    GPIO.setup(p, GPIO.OUT)
GPIO.setup(ECHO, GPIO.IN)
GPIO.output(TRIG, GPIO.LOW)
GPIO.output(MOTOR, GPIO.LOW)
GPIO.output(BUZZER, GPIO.LOW)
time.sleep(1)

# --- I2C setup ---
bus = smbus2.SMBus(1)
bus.write_byte_data(MPU_ADDR, PWR_MGMT_1, 0)

# --- Log setup ---
log = open("multithread_full_metrics_log.csv", "w", newline="")
writer = csv.writer(log)
writer.writerow([
    "timestamp", "distance_cm", "motor_state",
    "a_mag_g", "jerk_gps", "fsm_state",
    "loop_time_ms", "sample_rate_Hz", "jitter_ms",
    "cpu_load_%", "mem_usage_MB", "cpu_temp_C"
])

loop_times = []

# -------------------------
#  NEW FUNCTION: 3 SECOND ALARM + SMS
# -------------------------
def buzzer_alarm_and_sms():
    # 1) Run buzzer for 3 seconds
    GPIO.output(BUZZER, 1)
    time.sleep(3)
    GPIO.output(BUZZER, 0)

    print("[ALERT] Buzzer finished, sending SMS...")

    # Path to send_sms.py
    sms_path = "/home/prateeksha/Desktop/wearable-navigation/wearable-navigation/src/alerts/send_sms.py"

    # Path to your virtual environment python (IMPORTANT)
    venv_python = "/home/prateeksha/Desktop/wearable-navigation/wearable-navigation/twilio-env/bin/python3"

    # Execute send_sms.py inside the venv
    os.system(f"{venv_python} {sms_path}")

    print("[ALERT] SMS script executed")


# -------------------------
#  System Helpers
# -------------------------
def get_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return float(f.read()) / 1000.0
    except:
        return 0.0

def measure_distance():
    GPIO.output(TRIG, True)
    time.sleep(0.00001)
    GPIO.output(TRIG, False)
    start = time.time()
    stop = start
    while GPIO.input(ECHO) == 0:
        start = time.time()
    while GPIO.input(ECHO) == 1:
        stop = time.time()
    return (stop - start) * 17150

def read_accel():
    def rw(r):
        h = bus.read_byte_data(MPU_ADDR, r)
        l = bus.read_byte_data(MPU_ADDR, r + 1)
        v = (h << 8) + l
        return v - 65536 if v >= 0x8000 else v
    ax = rw(ACCEL_XOUT_H) / ACCEL_SCALE
    ay = rw(ACCEL_XOUT_H + 2) / ACCEL_SCALE
    az = rw(ACCEL_XOUT_H + 4) / ACCEL_SCALE
    return ax, ay, az

# -------------------------
#  THREAD 1: ULTRASONIC
# -------------------------
def ultrasonic_thread():
    global fall_detected
    while not stop_event.is_set():
        t1 = time.time()
        dist = measure_distance()
        motor_state = int(dist < 20 and not fall_detected)
        GPIO.output(MOTOR, motor_state)

        t2 = time.time()
        loop_time = (t2 - t1) * 1000
        loop_times.append(loop_time)
        if len(loop_times) > 10:
            loop_times.pop(0)
        avg = statistics.mean(loop_times)
        jitter = max(loop_times) - min(loop_times)
        rate = 1000 / avg if avg > 0 else 0

        cpu_load = psutil.cpu_percent(interval=None)
        mem_usage = psutil.virtual_memory().used / (1024 * 1024)
        cpu_temp = get_temp()

        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        writer.writerow([
            ts, round(dist, 2), motor_state, "", "", "",
            round(loop_time, 2), round(rate, 2), round(jitter, 2),
            round(cpu_load, 2), round(mem_usage, 2), round(cpu_temp, 2)
        ])
        log.flush()

        print(f"[DATA] {ts} | {dist:6.2f}cm | loop {loop_time:5.2f}ms | "
              f"CPU {cpu_load:5.1f}% | Temp {cpu_temp:5.1f}°C | Mem {mem_usage:6.1f}MB")
        time.sleep(0.1)

# -------------------------
#  THREAD 2: MPU6050
# -------------------------
def mpu_thread():
    global fall_detected, cooldown_until
    prev_ax = prev_ay = prev_az = 0
    state = "idle"

    while not stop_event.is_set():
        ax, ay, az = read_accel()
        a_mag = math.sqrt(ax**2 + ay**2 + az**2)
        jx = (ax - prev_ax) / DT
        jy = (ay - prev_ay) / DT
        jz = (az - prev_az) / DT
        jerk = math.sqrt(jx**2 + jy**2 + jz**2)
        prev_ax, prev_ay, prev_az = ax, ay, az

        now = time.monotonic()
        if now < cooldown_until:
            time.sleep(DT)
            continue

        # ---- FREEFALL LOGIC ----
        if state == "idle" and a_mag < FREEFALL_G:
            state = "freefall"
            start = now
            print("[MPU] Freefall suspected...")
        elif state == "freefall":
            if (now - start) >= MIN_FREEFALL_TIME and a_mag < FREEFALL_G:
                print("FREEFALL CONFIRMED, WAITING FOR IMPACT")

            if a_mag > IMPACT_G and (now - start) <= 1.0:
                print("[MPU] Impact confirmed! Fall detected.")
                fall_detected = True
                buzzer_alarm_and_sms()
                cooldown_until = now + COOLDOWN_SEC
                state = "idle"
                time.sleep(1.5)
                fall_detected = False

            elif (now - start) > 1.0:
                state = "idle"

        # ---- JERK DETECTION ----
        elif jerk > JERK_THRESH_GPS and a_mag > 2:
            print("[MPU] Sudden jerk detected!")
            fall_detected = True
            buzzer_alarm_and_sms()
            cooldown_until = now + COOLDOWN_SEC
            time.sleep(1.5)
            fall_detected = False

        time.sleep(DT)

# -------------------------
#  MAIN PROGRAM
# -------------------------
try:
    th1 = threading.Thread(target=ultrasonic_thread)
    th2 = threading.Thread(target=mpu_thread)
    th1.start()
    th2.start()

    while True:
        time.sleep(1)

except KeyboardInterrupt:
    print("\n[EXIT] stopped by user.")

finally:
    stop_event.set()
    th1.join()
    th2.join()
    GPIO.output(MOTOR, 0)
    GPIO.output(BUZZER, 0)
    GPIO.cleanup()
    log.close()
    print("[CLEANUP] GPIO released and log saved.")
