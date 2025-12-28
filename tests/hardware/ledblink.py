import gpiod
import time

# Replace with the correct line name for GPIO37 (get via `gpioinfo`)
GPIO_LINE_NAME = "GPIO37"   # Adjust this based on label seen in gpioinfo
CHIP_PATH = "/dev/gpiochip485"

def blink_led(duration=0.5, blinks=5):
    try:
        chip = gpiod.Chip(CHIP_PATH)
        line = chip.find_line(GPIO_LINE_NAME)

        if not line:
            print(f"[ERROR] Could not find GPIO line: {GPIO_LINE_NAME}")
            return

        line.request(consumer="led_blink", type=gpiod.LINE_REQ_DIR_OUT, default_vals=[0])
        print(f"[INFO] Blinking LED on {GPIO_LINE_NAME}")

        for _ in range(blinks):
            line.set_value(1)
            time.sleep(duration)
            line.set_value(0)
            time.sleep(duration)

        print(f"[SUCCESS] Done blinking {GPIO_LINE_NAME}")
        line.release()

    except Exception as e:
        print(f"[EXCEPTION] {e}")

if __name__ == "__main__":
    blink_led()

