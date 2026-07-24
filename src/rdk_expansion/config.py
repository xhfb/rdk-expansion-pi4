"""Configuration loading and validation."""

from __future__ import annotations

import copy
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .exceptions import UnsafeConfiguration


DEFAULTS: dict[str, Any] = {
    "gpio": {
        "pigpio_host": None,
        "pigpio_port": None,
        "debounce_ms": 20,
    },
    "adc": {
        "bus": 1,
        "address": 0x48,
        "full_scale_v": 4.096,
        "data_rate_sps": 128,
        "divider_scale": 4.9,
        "gain": [1.0, 1.0, 1.0, 1.0],
        "offset_v": [0.0, 0.0, 0.0, 0.0],
        "timeout_s": 0.1,
    },
    "ina226": {
        "bus": 1,
        "address": 0x40,
        "shunt_ohm": 0.01,
        "current_lsb_a": 0.00025,
        "averaging": 16,
        "conversion_time_us": 1100,
    },
    "servo": {
        "frequency_hz": 50,
        "min_pulse_us": [1000, 1000],
        "max_pulse_us": [2000, 2000],
        "min_angle": [0.0, 0.0],
        "max_angle": [180.0, 180.0],
    },
}


def _deep_merge(base: dict[str, Any], update: Mapping[str, Any]) -> dict[str, Any]:
    for key, value in update.items():
        if isinstance(value, Mapping) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = copy.deepcopy(value)
    return base


def _load_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _four(values: Any, name: str) -> tuple[float, float, float, float]:
    if not isinstance(values, (list, tuple)) or len(values) != 4:
        raise UnsafeConfiguration(f"{name} must contain exactly four values")
    return tuple(float(value) for value in values)  # type: ignore[return-value]


def _two_int(values: Any, name: str) -> tuple[int, int]:
    if not isinstance(values, (list, tuple)) or len(values) != 2:
        raise UnsafeConfiguration(f"{name} must contain exactly two values")
    return (int(values[0]), int(values[1]))


def _two_float(values: Any, name: str) -> tuple[float, float]:
    if not isinstance(values, (list, tuple)) or len(values) != 2:
        raise UnsafeConfiguration(f"{name} must contain exactly two values")
    return (float(values[0]), float(values[1]))


@dataclass(frozen=True, slots=True)
class AdcConfig:
    bus: int = 1
    address: int = 0x48
    full_scale_v: float = 4.096
    data_rate_sps: int = 128
    divider_scale: float = 4.9
    gain: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0)
    offset_v: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    timeout_s: float = 0.1


@dataclass(frozen=True, slots=True)
class Ina226Config:
    bus: int = 1
    address: int = 0x40
    shunt_ohm: float = 0.01
    current_lsb_a: float = 0.00025
    averaging: int = 16
    conversion_time_us: int = 1100

    @property
    def calibration(self) -> int:
        return round(0.00512 / (self.current_lsb_a * self.shunt_ohm))

    @property
    def power_lsb_w(self) -> float:
        return 25.0 * self.current_lsb_a


@dataclass(frozen=True, slots=True)
class ServoConfig:
    frequency_hz: int = 50
    min_pulse_us: tuple[int, int] = (1000, 1000)
    max_pulse_us: tuple[int, int] = (2000, 2000)
    min_angle: tuple[float, float] = (0.0, 0.0)
    max_angle: tuple[float, float] = (180.0, 180.0)


@dataclass(frozen=True, slots=True)
class GpioConfig:
    pigpio_host: str | None = None
    pigpio_port: int | None = None
    debounce_ms: int = 20


@dataclass(frozen=True, slots=True)
class BoardConfig:
    gpio: GpioConfig = field(default_factory=GpioConfig)
    adc: AdcConfig = field(default_factory=AdcConfig)
    ina226: Ina226Config = field(default_factory=Ina226Config)
    servo: ServoConfig = field(default_factory=ServoConfig)

    @classmethod
    def load(
        cls,
        explicit_path: str | Path | None = None,
        overrides: Mapping[str, Any] | None = None,
    ) -> "BoardConfig":
        merged = copy.deepcopy(DEFAULTS)
        _deep_merge(merged, _load_toml(Path("/etc/rdk-expansion/config.toml")))
        _deep_merge(
            merged,
            _load_toml(Path.home() / ".config" / "rdk-expansion" / "config.toml"),
        )
        if explicit_path is not None:
            _deep_merge(merged, _load_toml(Path(explicit_path)))
        if overrides:
            _deep_merge(merged, overrides)
        return cls.from_mapping(merged)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "BoardConfig":
        gpio_raw = raw["gpio"]
        adc_raw = raw["adc"]
        ina_raw = raw["ina226"]
        servo_raw = raw["servo"]
        adc = AdcConfig(
            bus=int(adc_raw["bus"]),
            address=int(adc_raw["address"]),
            full_scale_v=float(adc_raw["full_scale_v"]),
            data_rate_sps=int(adc_raw["data_rate_sps"]),
            divider_scale=float(adc_raw["divider_scale"]),
            gain=_four(adc_raw["gain"], "adc.gain"),
            offset_v=_four(adc_raw["offset_v"], "adc.offset_v"),
            timeout_s=float(adc_raw["timeout_s"]),
        )
        ina = Ina226Config(
            bus=int(ina_raw["bus"]),
            address=int(ina_raw["address"]),
            shunt_ohm=float(ina_raw["shunt_ohm"]),
            current_lsb_a=float(ina_raw["current_lsb_a"]),
            averaging=int(ina_raw["averaging"]),
            conversion_time_us=int(ina_raw["conversion_time_us"]),
        )
        servo = ServoConfig(
            frequency_hz=int(servo_raw["frequency_hz"]),
            min_pulse_us=_two_int(servo_raw["min_pulse_us"], "servo.min_pulse_us"),
            max_pulse_us=_two_int(servo_raw["max_pulse_us"], "servo.max_pulse_us"),
            min_angle=_two_float(servo_raw["min_angle"], "servo.min_angle"),
            max_angle=_two_float(servo_raw["max_angle"], "servo.max_angle"),
        )
        gpio = GpioConfig(
            pigpio_host=gpio_raw.get("pigpio_host"),
            pigpio_port=(
                int(gpio_raw["pigpio_port"])
                if gpio_raw.get("pigpio_port") is not None
                else None
            ),
            debounce_ms=int(gpio_raw["debounce_ms"]),
        )
        cls._validate(adc, ina, servo, gpio)
        return cls(gpio=gpio, adc=adc, ina226=ina, servo=servo)

    @staticmethod
    def _validate(
        adc: AdcConfig,
        ina: Ina226Config,
        servo: ServoConfig,
        gpio: GpioConfig,
    ) -> None:
        if adc.address != 0x48:
            raise UnsafeConfiguration("ADS1115 address must be fixed at 0x48 for V1")
        if adc.data_rate_sps != 128 or adc.full_scale_v != 4.096:
            raise UnsafeConfiguration("V1 ADC defaults require 128SPS and ±4.096V")
        if adc.divider_scale <= 0 or any(gain <= 0 for gain in adc.gain):
            raise UnsafeConfiguration("ADC divider and gains must be positive")
        if not 1 <= ina.calibration <= 0xFFFF:
            raise UnsafeConfiguration("INA226 calibration register is out of range")
        if ina.averaging not in {1, 4, 16, 64, 128, 256, 512, 1024}:
            raise UnsafeConfiguration("unsupported INA226 averaging value")
        if ina.conversion_time_us not in {140, 204, 332, 588, 1100, 2116, 4156, 8244}:
            raise UnsafeConfiguration("unsupported INA226 conversion time")
        if gpio.debounce_ms < 0:
            raise UnsafeConfiguration("GPIO debounce must be non-negative")
        if servo.frequency_hz != 50:
            raise UnsafeConfiguration("pigpio servo output is fixed at 50Hz")
        for index in range(2):
            if not 500 <= servo.min_pulse_us[index] < servo.max_pulse_us[index] <= 2500:
                raise UnsafeConfiguration(f"invalid servo {index} pulse range")
            if servo.min_angle[index] >= servo.max_angle[index]:
                raise UnsafeConfiguration(f"invalid servo {index} angle range")
