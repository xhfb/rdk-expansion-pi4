"""GPIO devices implemented through the pigpio daemon."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any, Protocol

from .exceptions import HardwareNotFound, UnsafeConfiguration


class GpioBackend(Protocol):
    def setup_input(self, bcm: int, pull_down: bool = True) -> None: ...
    def setup_output(self, bcm: int, initial: int) -> None: ...
    def read(self, bcm: int) -> int: ...
    def write(self, bcm: int, level: int) -> None: ...
    def set_glitch_filter(self, bcm: int, microseconds: int) -> None: ...
    def add_callback(self, bcm: int, callback: Callable[[int], None]) -> Any: ...
    def set_servo_pulsewidth(self, bcm: int, pulse_us: int) -> None: ...
    def close(self) -> None: ...


class PigpioBackend:
    """Thin, testable wrapper around ``pigpio.pi``."""

    def __init__(self, host: str | None = None, port: int | None = None):
        try:
            import pigpio
        except ImportError as exc:
            raise HardwareNotFound("python pigpio module is not installed") from exc
        args: list[Any] = []
        if host is not None:
            args.append(host)
        if port is not None:
            if host is None:
                args.append("localhost")
            args.append(port)
        self._pigpio = pigpio
        self._client = pigpio.pi(*args)
        if not self._client.connected:
            self._client.stop()
            raise HardwareNotFound(
                "pigpiod is unavailable; run: sudo systemctl enable --now pigpiod"
            )
        self._callbacks: list[Any] = []

    def setup_input(self, bcm: int, pull_down: bool = True) -> None:
        self._client.set_mode(bcm, self._pigpio.INPUT)
        pud = self._pigpio.PUD_DOWN if pull_down else self._pigpio.PUD_OFF
        self._client.set_pull_up_down(bcm, pud)

    def setup_output(self, bcm: int, initial: int) -> None:
        self._client.write(bcm, int(bool(initial)))
        self._client.set_mode(bcm, self._pigpio.OUTPUT)
        self._client.write(bcm, int(bool(initial)))

    def read(self, bcm: int) -> int:
        return int(self._client.read(bcm))

    def write(self, bcm: int, level: int) -> None:
        self._client.write(bcm, int(bool(level)))

    def set_glitch_filter(self, bcm: int, microseconds: int) -> None:
        self._client.set_glitch_filter(bcm, microseconds)

    def add_callback(self, bcm: int, callback: Callable[[int], None]) -> Any:
        token = self._client.callback(
            bcm,
            self._pigpio.EITHER_EDGE,
            lambda gpio, level, tick: callback(int(level)) if level in (0, 1) else None,
        )
        self._callbacks.append(token)
        return token

    def set_servo_pulsewidth(self, bcm: int, pulse_us: int) -> None:
        result = self._client.set_servo_pulsewidth(bcm, pulse_us)
        if result < 0:
            raise HardwareNotFound(f"pigpio rejected servo pulse on BCM{bcm}: {result}")

    def close(self) -> None:
        for callback in self._callbacks:
            try:
                callback.cancel()
            except Exception:
                # A Button may already have cancelled its pigpio callback.
                pass
        self._callbacks.clear()
        self._client.stop()


class Button:
    def __init__(self, backend: GpioBackend, bcm: int, debounce_ms: int = 20):
        self.backend = backend
        self.bcm = bcm
        self._press_event = threading.Event()
        self._callback: Callable[["Button"], None] | None = None
        backend.setup_input(bcm, pull_down=True)
        backend.set_glitch_filter(bcm, debounce_ms * 1000)
        self._token = backend.add_callback(bcm, self._changed)
        self._closed = False

    @property
    def is_pressed(self) -> bool:
        return bool(self.backend.read(self.bcm))

    @property
    def when_pressed(self) -> Callable[["Button"], None] | None:
        return self._callback

    @when_pressed.setter
    def when_pressed(self, callback: Callable[["Button"], None] | None) -> None:
        self._callback = callback

    def _changed(self, level: int) -> None:
        if level == 1:
            self._press_event.set()
            if self._callback is not None:
                self._callback(self)

    def wait_for_press(self, timeout: float | None = None) -> bool:
        self._press_event.clear()
        return self._press_event.wait(timeout)

    def close(self) -> None:
        if not self._closed and hasattr(self._token, "cancel"):
            self._token.cancel()
        self._closed = True


class ActiveOutput:
    def __init__(
        self,
        backend: GpioBackend,
        bcm: int,
        active_level: int,
        safe_level: int,
    ):
        self.backend = backend
        self.bcm = bcm
        self.active_level = int(bool(active_level))
        self.safe_level = int(bool(safe_level))
        backend.setup_output(bcm, self.safe_level)

    @property
    def is_active(self) -> bool:
        return self.backend.read(self.bcm) == self.active_level

    def on(self) -> None:
        self.backend.write(self.bcm, self.active_level)

    def off(self) -> None:
        self.backend.write(self.bcm, self.safe_level)

    def close(self) -> None:
        self.off()


class Buzzer(ActiveOutput):
    def beep(self, seconds: float = 0.2) -> None:
        if seconds <= 0:
            raise UnsafeConfiguration("beep duration must be positive")
        self.on()
        try:
            time.sleep(seconds)
        finally:
            self.off()


class RelayOutput(ActiveOutput):
    """Active-low host control for a 3.3V active-high relay-module signal."""


class Servo:
    def __init__(
        self,
        backend: GpioBackend,
        bcm: int,
        min_pulse_us: int,
        max_pulse_us: int,
        min_angle: float,
        max_angle: float,
    ):
        self.backend = backend
        self.bcm = bcm
        self.min_pulse_us = min_pulse_us
        self.max_pulse_us = max_pulse_us
        self.min_angle = min_angle
        self.max_angle = max_angle
        self._pulse_us = 0
        backend.set_servo_pulsewidth(bcm, 0)

    @property
    def pulse_us(self) -> int:
        return self._pulse_us

    def set_pulse_us(self, pulse_us: int) -> None:
        if not self.min_pulse_us <= pulse_us <= self.max_pulse_us:
            raise UnsafeConfiguration(
                f"servo pulse must be {self.min_pulse_us}..{self.max_pulse_us}us"
            )
        self.backend.set_servo_pulsewidth(self.bcm, pulse_us)
        self._pulse_us = pulse_us

    def set_angle(self, angle: float) -> None:
        if not self.min_angle <= angle <= self.max_angle:
            raise UnsafeConfiguration(
                f"servo angle must be {self.min_angle}..{self.max_angle} degrees"
            )
        ratio = (angle - self.min_angle) / (self.max_angle - self.min_angle)
        pulse = round(self.min_pulse_us + ratio * (self.max_pulse_us - self.min_pulse_us))
        self.set_pulse_us(pulse)

    def disable(self) -> None:
        self.backend.set_servo_pulsewidth(self.bcm, 0)
        self._pulse_us = 0

    def close(self) -> None:
        self.disable()
