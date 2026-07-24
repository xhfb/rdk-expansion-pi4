"""Raw Linux bus factories and shared-resource handling."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from .exceptions import HardwareNotFound, ResourceBusy, UnsupportedOnHost
from .gpio import GpioBackend


class ResourceRegistry:
    def __init__(self):
        self._lock = threading.Lock()
        self._resources: set[str] = set()

    def acquire(self, resource: str) -> Callable[[], None]:
        with self._lock:
            if resource in self._resources:
                raise ResourceBusy(f"resource is already open: {resource}")
            self._resources.add(resource)

        def release() -> None:
            with self._lock:
                self._resources.discard(resource)

        return release


class ManagedHandle:
    def __init__(self, handle: Any, release: Callable[[], None]):
        self._handle = handle
        self._release = release
        self._closed = False

    def __getattr__(self, name: str) -> Any:
        return getattr(self._handle, name)

    def __enter__(self) -> "ManagedHandle":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        try:
            self._handle.close()
        finally:
            self._release()
            self._closed = True


class ManualCsSpi:
    def __init__(self, spi: Any, gpio: GpioBackend, cs_bcm: int):
        self.spi = spi
        self.gpio = gpio
        self.cs_bcm = cs_bcm
        self.gpio.setup_output(cs_bcm, 1)
        try:
            self.spi.no_cs = True
        except (AttributeError, OSError) as exc:
            self.spi.close()
            raise HardwareNotFound(
                "kernel spidev does not support no_cs required for SPI CS2"
            ) from exc

    def xfer2(self, data: list[int], speed_hz: int = 0, delay_usec: int = 0) -> list[int]:
        self.gpio.write(self.cs_bcm, 0)
        try:
            return self.spi.xfer2(data, speed_hz, delay_usec)
        finally:
            self.gpio.write(self.cs_bcm, 1)

    def close(self) -> None:
        self.gpio.write(self.cs_bcm, 1)
        self.spi.close()


def open_i2c_bus(name: str, *, allow_reserved_i2c0: bool = False) -> Any:
    if name == "i2c5":
        bus_number = 1
    elif name == "i2c0":
        if not allow_reserved_i2c0:
            raise UnsupportedOnHost(
                "i2c0 uses Raspberry Pi HAT ID EEPROM pins BCM0/1 and is disabled"
            )
        bus_number = 0
    else:
        raise ValueError(f"unknown board I2C interface: {name}")
    try:
        from smbus2 import SMBus

        return SMBus(bus_number)
    except (ImportError, FileNotFoundError, PermissionError, OSError) as exc:
        raise HardwareNotFound(f"cannot open /dev/i2c-{bus_number}: {exc}") from exc


def open_uart(name: str, **serial_kwargs: Any) -> Any:
    if name != "uart1":
        raise UnsupportedOnHost(f"{name} is not a hardware UART on Raspberry Pi 4")
    try:
        import serial

        kwargs = {"baudrate": 115200, "timeout": 1.0, **serial_kwargs}
        return serial.Serial("/dev/serial0", **kwargs)
    except (ImportError, FileNotFoundError, PermissionError, OSError) as exc:
        raise HardwareNotFound(f"cannot open /dev/serial0: {exc}") from exc


def open_spi(
    name: str,
    registry: ResourceRegistry,
    gpio: GpioBackend | None = None,
    *,
    max_speed_hz: int = 1_000_000,
    mode: int = 0,
) -> ManagedHandle:
    mapping = {
        "spi1a.cs0": ("spi0.cs0", 0, 0, None),
        "spi1a.cs1": ("spi0.cs1", 0, 1, None),
        "spi1b.cs0": ("spi0.cs0", 0, 0, None),
        "spi1b.cs2": ("spi0.cs2-manual", 0, 0, 24),
    }
    if name not in mapping:
        raise ValueError(f"unknown board SPI interface: {name}")
    resource, bus, device, manual_cs = mapping[name]
    release = registry.acquire(resource)
    try:
        import spidev

        spi = spidev.SpiDev()
        spi.open(bus, device)
        spi.max_speed_hz = max_speed_hz
        spi.mode = mode
        handle: Any = spi
        if manual_cs is not None:
            if gpio is None:
                spi.close()
                raise HardwareNotFound("pigpiod is required for manual SPI CS2")
            handle = ManualCsSpi(spi, gpio, manual_cs)
        return ManagedHandle(handle, release)
    except Exception:
        release()
        raise
