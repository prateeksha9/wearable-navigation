
# for Synaptics Astra (Yocto Linux)
# - Uses smbus2 for I2C
# - Prints "FALL DETECTED" vs "OK"
# - No button logic / HTTP / WiFi

import os
import time
import math

# Try smbus2 first (what we cloned on Astra); fall back to smbus if present
try:
    from smbus2 import SMBus
except ImportError:
    from smbus2 import SMBus  # type: ignore

# ---------------------------
# I2C CONFIG
# ---------------------------
#I2C_BUS = int(os.getenv("I2C_BUS", "1"))   # adjust if needed after ls /dev/i2c-*
I2C_BUS = 0
MPU_ADDR = 0x68                            # AD0=GND -> 0x68, AD0=VCC -> 0x69

# ---------------------------
# MPU6050 REGISTERS
# ---------------------------
PWR_MGMT_1     = 0x6B
SMPLRT_DIV     = 0x19
CONFIG         = 0x1A
GYRO_CONFIG    = 0x1B
ACCEL_CONFIG   = 0x1C
INT_STATUS     = 0x3A
ACCEL_XOUT_H   = 0x3B
TEMP_OUT_H     = 0x41
GYRO_XOUT_H    = 0x43
WHO_AM_I       = 0x75

# ---------------------------
# CONSTANTS / CALIB / SCALE
# ---------------------------
ACCEL_SF = 16384.0   # LSB/g for ±2g
GYRO_SF  = 131.0     # LSB/(deg/s) for ±250 dps

# Sampling
FS_HZ = 100.0         # 100 Hz loop
DT    = 1.0 / FS_HZ

# Fall detection thresholds (tune on real data)
FREEFALL_G         = 0.5         # magnitude below this -> likely free fall
IMPACT_G           = 2.5         # impact spike
FREEFALL_TO_IMPACT = 0.7         # seconds allowed from freefall to impact
COOLDOWN_SEC       = 2.0         # avoid repeated triggers
JERK_THRESH_GPS    = 15.0        # g/s: backup trigger (sudden change)

# Print pacing
STATUS_EVERY_SEC   = 1.0

def read_word_2c(bus, addr, reg_h):
    """Read two registers and convert to signed 16-bit."""
    hi = bus.read_byte_data(addr, reg_h)
    lo = bus.read_byte_data(addr, reg_h + 1)
    val = (hi << 8) | lo
    if val & 0x8000:
        val -= 65536
    return val

def mpu_init(bus):
    # Wake up device
    bus.write_byte_data(MPU_ADDR, PWR_MGMT_1, 0x00)   # clear sleep
    time.sleep(0.05)

    # Set sample rate to 1kHz / (1 + SMPLRT_DIV) -> 100Hz when SMPLRT_DIV = 9
    bus.write_byte_data(MPU_ADDR, SMPLRT_DIV, 9)

    # DLPF config: 0x03 (~44Hz accel BW, 42Hz gyro BW) for smoother readings
    bus.write_byte_data(MPU_ADDR, CONFIG, 0x03)

    # Gyro ±250 dps
    bus.write_byte_data(MPU_ADDR, GYRO_CONFIG, 0x00)

    # Accel ±2g
    bus.write_byte_data(MPU_ADDR, ACCEL_CONFIG, 0x00)

    # Verify WHO_AM_I (should read 0x68)
    who = bus.read_byte_data(MPU_ADDR, WHO_AM_I)
    if who != 0x68:
        print(f"[WARN] Unexpected WHO_AM_I: 0x{who:02X}, expected 0x68")
    else:
        print("[OK] MPU6050 WHO_AM_I = 0x68")

def read_accel_gyro(bus):
    # Raw accelerometer (g's after scaling)
    ax = read_word_2c(bus, MPU_ADDR, ACCEL_XOUT_H) / ACCEL_SF
    ay = read_word_2c(bus, MPU_ADDR, ACCEL_XOUT_H + 2) / ACCEL_SF
    az = read_word_2c(bus, MPU_ADDR, ACCEL_XOUT_H + 4) / ACCEL_SF

    # Raw gyro (deg/s after scaling) – kept in case you want orientation thresholds later
    gx = read_word_2c(bus, MPU_ADDR, GYRO_XOUT_H) / GYRO_SF
    gy = read_word_2c(bus, MPU_ADDR, GYRO_XOUT_H + 2) / GYRO_SF
    gz = read_word_2c(bus, MPU_ADDR, GYRO_XOUT_H + 4) / GYRO_SF

    return ax, ay, az, gx, gy, gz

def magnitude3(x, y, z):
    return math.sqrt(x*x + y*y + z*z)

def main():
    print("[INFO] Opening I2C bus:", I2C_BUS)
    with SMBus(I2C_BUS) as bus:
        mpu_init(bus)

        # Priming values for jerk calculation (Δacc/Δt)
        prev_ax = prev_ay = prev_az = 0.0
        prev_time = time.monotonic()

        state = "idle"
        freefall_start = 0.0
        cooldown_until = 0.0
        last_status = 0.0

        while True:
            loop_start = time.monotonic()

            ax, ay, az, gx, gy, gz = read_accel_gyro(bus)
            a_mag = magnitude3(ax, ay, az)  # in g

            # Jerk (g/s)
            jerk_x = (ax - prev_ax) / DT
            jerk_y = (ay - prev_ay) / DT
            jerk_z = (az - prev_az) / DT
            jerk_mag = magnitude3(jerk_x, jerk_y, jerk_z)

            prev_ax, prev_ay, prev_az = ax, ay, az

            now = loop_start

            # Cooldown: suppress repeated triggers briefly
            if now < cooldown_until:
                # Minimal output spam; still print OK periodically
                pass
            else:
                if state == "idle":
                    # Detect entry to free-fall
                    if a_mag < FREEFALL_G:
                        state = "freefall"
                        freefall_start = now
                    # Backup jerk-based trigger (impact-y change)
                    elif jerk_mag > JERK_THRESH_GPS and a_mag > 1.5:
                        print("FALL DETECTED (jerk trigger)")
                        cooldown_until = now + COOLDOWN_SEC

                elif state == "freefall":
                    # If impact soon after freefall -> fall
                    if a_mag > IMPACT_G and (now - freefall_start) <= FREEFALL_TO_IMPACT:
                        print("FALL DETECTED (freefall→impact)")
                        cooldown_until = now + COOLDOWN_SEC
                        state = "idle"  # reset state machine
                    # Timeout: no impact, return to idle
                    elif (now - freefall_start) > FREEFALL_TO_IMPACT:
                        state = "idle"

            # Status line every second
            if (now - last_status) >= STATUS_EVERY_SEC:
                if now >= cooldown_until:
                    print(f"OK | a_mag={a_mag:.2f} g | jerk={jerk_mag:.1f} g/s | state={state}")
                else:
                    print(f"COOLDOWN | a_mag={a_mag:.2f} g | jerk={jerk_mag:.1f} g/s")
                last_status = now

            # Sleep to maintain ~FS_HZ
            elapsed = time.monotonic() - loop_start
            to_sleep = DT - elapsed
            if to_sleep > 0:
                time.sleep(to_sleep)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[INFO] Stopped.")

