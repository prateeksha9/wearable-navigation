from pathlib import Path
from typing import Final
import time

import gpiod
from gpiod.line import Direction, Value

TRIG: Final = 10
ECHO: Final = 37


def get_address_info_sl1680(gpio_id: int) -> tuple[str, int]:
    if not isinstance(gpio_id, int):
        raise TypeError(f"GPIO ID must be an integer, not {type(gpio_id)}")
    if 0 <= gpio_id < 32:
        return "f7e82400", gpio_id
    elif 32 <= gpio_id < 64:
        return "f7e80800", gpio_id - 32
    elif 64 <= gpio_id < 96:
        return "f7e80c00", gpio_id - 64
    raise ValueError(f"Invalid GPIO ID '{gpio_id}'")


def get_gpio_chip(address: str) -> str:
    devs: list[str] = [str(p) for p in Path("/dev").glob("gpio*")]
    for dev in devs:
        with gpiod.Chip(dev) as chip:
            info = chip.get_info()
            if address in info.label:
                return dev
    raise ValueError(f"GPIO chip for label '{address}' not found")


def get_gpio_info(gpio_id: int) -> tuple[str, int]:
    address, line = get_address_info_sl1680(gpio_id)
    dev = get_gpio_chip(address)
    return dev, line


class GPIO:

    def __init__(self, chip: str, line: int):
        self.chip = chip
        self.line = line

    def read(self) -> Value:
        with gpiod.request_lines(self.chip, config={self.line: gpiod.LineSettings(direction=Direction.INPUT)}) as req:
            value = req.get_value(self.line)
            return value

    def write(self, value: Value):
        with gpiod.request_lines(self.chip, config={self.line: gpiod.LineSettings(direction=Direction.OUTPUT)}) as req:
            req.set_value(self.line, value)

    def set_high(self):
        self.write(Value.ACTIVE)

    def set_low(self):
        self.write(Value.INACTIVE)

    def pulse_high(self, duration_sec: float):
        with gpiod.request_lines(self.chip, config={self.line: gpiod.LineSettings(direction=Direction.OUTPUT)}) as req:
            req.set_value(self.line, Value.ACTIVE)
            time.sleep(duration_sec)
            req.set_value(self.line, Value.INACTIVE)

    def wait_for_value(self, target_value: Value, timeout: float) -> int | None:
        deadline = time.monotonic_ns() + int(timeout * 1e9)
        with gpiod.request_lines(self.chip, config={self.line: gpiod.LineSettings(direction=Direction.INPUT)}) as req:
            while time.monotonic_ns() < deadline:
                if req.get_value(self.line) == target_value:
                    return time.monotonic_ns()
        return None


if __name__ == "__main__":
    trig_chip, trig_line = get_gpio_info(TRIG)
    echo_chip, echo_line = get_gpio_info(ECHO)
    trig = GPIO(trig_chip, trig_line)
    echo = GPIO(echo_chip, echo_line)

    while True:
        try:
            print("[DEBUG] Ensuring trigger is low")
            trig.set_low()

            print("[DEBUG] Sending 10µs trigger pulse")
            trig.pulse_high(10e-6)

            print("[DEBUG] Waiting for Echo to go HIGH")
            start = echo.wait_for_value(Value.ACTIVE, timeout=0.2)
            if start is None:
                print("[ERROR] Timeout waiting for Echo to go HIGH")
            else:
                print(f"[DEBUG] Echo went HIGH at {start} ns")

            print("[DEBUG] Waiting for Echo to go LOW")
            end = echo.wait_for_value(Value.INACTIVE, timeout=0.2)
            if end is None:
                print("[ERROR] Timeout waiting for Echo to go LOW")
            else:
                print(f"[DEBUG] Echo went LOW at {end} ns")

            duration_sec = (end - start) / 1e9
            print(f"[DEBUG] Pulse duration: {duration_sec:.6f} seconds")

            distance_cm = (duration_sec * 34300) / 2
            print(distance_cm)

        except KeyboardInterrupt:
            print(f"Exiting ...")