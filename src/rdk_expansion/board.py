"""High-level expansion board API."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from types import SimpleNamespace
from typing import Any

from .adc import ADS1115
from .buses import ResourceRegistry, open_i2c_bus, open_spi, open_uart
from .config import BoardConfig
from .exceptions import HardwareNotFound
from .gpio import (
    ActiveOutput,
    Button,
    Buzzer,
    GpioBackend,
    PigpioBackend,
    RelayOutput,
    Servo,
)
from .models import Capability
from .power import INA226


class ExpansionBoard:
    """Raspberry Pi 4 support package for the V1.0 expansion board."""

    BCM = {
        "key0": 26,
        "key1": 6,
        "key2": 5,
        "buzzer": 19,
        "relay1": 20,
        "relay2": 21,
        "servo0": 12,
        "servo1": 13,
    }

    def __init__(
        self,
        config: BoardConfig | None = None,
        *,
        gpio_backend: GpioBackend | None = None,
        i2c_factory: Callable[[int], Any] | None = None,
    ):
        self.config = config or BoardConfig.load()
        self._gpio = gpio_backend
        self._gpio_error: HardwareNotFound | None = None
        if self._gpio is None:
            try:
                self._gpio = PigpioBackend(
                    self.config.gpio.pigpio_host,
                    self.config.gpio.pigpio_port,
                )
            except HardwareNotFound as exc:
                self._gpio_error = exc
        self._i2c_factory = i2c_factory
        self._owned_buses: list[Any] = []
        self._resources = ResourceRegistry()
        self._closed = False
        self._buttons: SimpleNamespace | None = None
        self._buzzer: Buzzer | None = None
        self._relays: tuple[RelayOutput, RelayOutput] | None = None
        self._servos: tuple[Servo, Servo] | None = None
        self._adc: ADS1115 | None = None
        self._power: INA226 | None = None
        if self._gpio is not None:
            self._initialize_safe_outputs()

    @classmethod
    def open(
        cls,
        config_path: str | None = None,
        *,
        overrides: Mapping[str, Any] | None = None,
        gpio_backend: GpioBackend | None = None,
        i2c_factory: Callable[[int], Any] | None = None,
    ) -> "ExpansionBoard":
        return cls(
            BoardConfig.load(config_path, overrides),
            gpio_backend=gpio_backend,
            i2c_factory=i2c_factory,
        )

    def __enter__(self) -> "ExpansionBoard":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def _require_gpio(self) -> GpioBackend:
        if self._gpio is None:
            raise self._gpio_error or HardwareNotFound("GPIO backend is unavailable")
        return self._gpio

    def _initialize_safe_outputs(self) -> None:
        """Claim every actuator pin and establish the documented safe state."""
        _ = self.buzzer
        _ = self.relays
        _ = self.servos

    def _open_owned_i2c(self, bus_number: int) -> Any:
        if self._i2c_factory is not None:
            bus = self._i2c_factory(bus_number)
        else:
            bus = open_i2c_bus("i2c5" if bus_number == 1 else "i2c0")
        self._owned_buses.append(bus)
        return bus

    @property
    def buttons(self) -> SimpleNamespace:
        if self._buttons is None:
            gpio = self._require_gpio()
            debounce = self.config.gpio.debounce_ms
            self._buttons = SimpleNamespace(
                key0=Button(gpio, self.BCM["key0"], debounce),
                key1=Button(gpio, self.BCM["key1"], debounce),
                key2=Button(gpio, self.BCM["key2"], debounce),
            )
        return self._buttons

    @property
    def buzzer(self) -> Buzzer:
        if self._buzzer is None:
            self._buzzer = Buzzer(
                self._require_gpio(), self.BCM["buzzer"], active_level=1, safe_level=0
            )
        return self._buzzer

    @property
    def relays(self) -> tuple[RelayOutput, RelayOutput]:
        if self._relays is None:
            gpio = self._require_gpio()
            self._relays = (
                RelayOutput(gpio, self.BCM["relay1"], active_level=0, safe_level=1),
                RelayOutput(gpio, self.BCM["relay2"], active_level=0, safe_level=1),
            )
        return self._relays

    @property
    def servos(self) -> tuple[Servo, Servo]:
        if self._servos is None:
            gpio = self._require_gpio()
            cfg = self.config.servo
            self._servos = tuple(
                Servo(
                    gpio,
                    self.BCM[f"servo{index}"],
                    cfg.min_pulse_us[index],
                    cfg.max_pulse_us[index],
                    cfg.min_angle[index],
                    cfg.max_angle[index],
                )
                for index in range(2)
            )  # type: ignore[assignment]
        return self._servos

    @property
    def adc(self) -> ADS1115:
        if self._adc is None:
            self._adc = ADS1115(
                self._open_owned_i2c(self.config.adc.bus), self.config.adc
            )
        return self._adc

    @property
    def power(self) -> INA226:
        if self._power is None:
            self._power = INA226(
                self._open_owned_i2c(self.config.ina226.bus), self.config.ina226
            )
        return self._power

    def open_i2c(self, name: str, *, allow_reserved_i2c0: bool = False) -> Any:
        if self._i2c_factory is not None:
            if name == "i2c5":
                return self._i2c_factory(1)
            if name == "i2c0" and allow_reserved_i2c0:
                return self._i2c_factory(0)
        return open_i2c_bus(name, allow_reserved_i2c0=allow_reserved_i2c0)

    def open_spi(
        self, name: str, *, max_speed_hz: int = 1_000_000, mode: int = 0
    ) -> Any:
        return open_spi(
            name,
            self._resources,
            self._gpio,
            max_speed_hz=max_speed_hz,
            mode=mode,
        )

    def open_uart(self, name: str, **serial_kwargs: Any) -> Any:
        return open_uart(name, **serial_kwargs)

    def capabilities(self) -> tuple[Capability, ...]:
        gpio_status = "supported" if self._gpio is not None else "unavailable"
        gpio_detail = "" if self._gpio is not None else str(self._gpio_error)
        return (
            Capability("gpio", gpio_status, gpio_detail),
            Capability("pwm", gpio_status, gpio_detail),
            Capability("i2c5", "supported", "/dev/i2c-1 (Pi I2C1)"),
            Capability("i2c0", "disabled", "BCM0/1 HAT ID EEPROM bus"),
            Capability("spi1a.cs0", "supported", "/dev/spidev0.0"),
            Capability("spi1a.cs1", "supported", "/dev/spidev0.1"),
            Capability("spi1b.cs2", gpio_status, "manual CS on BCM24"),
            Capability("uart1", "supported", "/dev/serial0"),
            Capability("uart7", "unsupported", "BCM17/27 are not a Pi 4 UART pair"),
            Capability("uart2", "unsupported", "BCM22/25 are not a Pi 4 UART pair"),
            Capability("uart6", "unsupported", "BCM23/16 are not a Pi 4 UART pair"),
            Capability("rc", "unsupported", "depends on UART7_RX_SW"),
            Capability("can", "passive-only", "not connected to the host header"),
            Capability("fan", "fixed-power", "5V_SERVO, no software control"),
        )

    def close(self) -> None:
        if self._closed:
            return
        if self._servos is not None:
            for servo in self._servos:
                servo.close()
        if self._relays is not None:
            for relay in self._relays:
                relay.close()
        if self._buzzer is not None:
            self._buzzer.close()
        if self._buttons is not None:
            for name in ("key0", "key1", "key2"):
                getattr(self._buttons, name).close()
        for bus in self._owned_buses:
            bus.close()
        self._owned_buses.clear()
        if self._gpio is not None:
            self._gpio.close()
        self._closed = True
