"""Value types returned by the public API."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AdcSample:
    channel: int
    raw: int
    adc_volts: float
    input_volts: float
    address: int = 0x48


@dataclass(frozen=True, slots=True)
class PowerSample:
    bus_volts: float
    shunt_volts: float
    current_amps: float
    power_watts: float
    math_overflow: bool
    address: int = 0x40


@dataclass(frozen=True, slots=True)
class Capability:
    name: str
    status: str
    detail: str = ""

