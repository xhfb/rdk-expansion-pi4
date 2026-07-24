"""ADS1115 single-ended voltage input driver."""

from __future__ import annotations

import time
from typing import Protocol

from .config import AdcConfig
from .exceptions import HardwareNotFound
from .models import AdcSample


class I2cBus(Protocol):
    def read_i2c_block_data(self, address: int, register: int, length: int) -> list[int]: ...
    def write_i2c_block_data(
        self, address: int, register: int, data: list[int]
    ) -> None: ...
    def read_byte(self, address: int) -> int: ...
    def close(self) -> None: ...


class ADS1115:
    REG_CONVERSION = 0x00
    REG_CONFIG = 0x01
    PGA_4_096 = 0b001
    DR_128 = 0b100

    def __init__(self, bus: I2cBus, config: AdcConfig):
        self.bus = bus
        self.config = config

    def _write_u16(self, register: int, value: int) -> None:
        try:
            self.bus.write_i2c_block_data(
                self.config.address, register, [(value >> 8) & 0xFF, value & 0xFF]
            )
        except OSError as exc:
            raise HardwareNotFound(
                f"ADS1115 not responding at 0x{self.config.address:02x}"
            ) from exc

    def _read_u16(self, register: int) -> int:
        try:
            data = self.bus.read_i2c_block_data(self.config.address, register, 2)
        except OSError as exc:
            raise HardwareNotFound(
                f"ADS1115 not responding at 0x{self.config.address:02x}"
            ) from exc
        if len(data) != 2:
            raise HardwareNotFound("ADS1115 returned an incomplete register value")
        return (data[0] << 8) | data[1]

    @staticmethod
    def _signed(value: int) -> int:
        return value - 0x10000 if value & 0x8000 else value

    def _conversion_config(self, channel: int) -> int:
        mux = 0b100 + channel
        return (
            (1 << 15)
            | (mux << 12)
            | (self.PGA_4_096 << 9)
            | (1 << 8)
            | (self.DR_128 << 5)
            | 0b11
        )

    def read(self, channel: int) -> AdcSample:
        if channel not in range(4):
            raise ValueError("ADS1115 channel must be 0..3")
        self._write_u16(self.REG_CONFIG, self._conversion_config(channel))
        deadline = time.monotonic() + self.config.timeout_s
        interval = min(0.002, 1.0 / self.config.data_rate_sps)
        while time.monotonic() < deadline:
            if self._read_u16(self.REG_CONFIG) & 0x8000:
                break
            time.sleep(interval)
        else:
            raise TimeoutError("ADS1115 single-shot conversion timed out")
        raw = self._signed(self._read_u16(self.REG_CONVERSION))
        adc_volts = raw * self.config.full_scale_v / 32768.0
        input_volts = (
            adc_volts * self.config.divider_scale * self.config.gain[channel]
            + self.config.offset_v[channel]
        )
        return AdcSample(
            channel=channel,
            raw=raw,
            adc_volts=adc_volts,
            input_volts=input_volts,
            address=self.config.address,
        )

    def read_all(self) -> tuple[AdcSample, AdcSample, AdcSample, AdcSample]:
        return tuple(self.read(channel) for channel in range(4))  # type: ignore[return-value]

    @staticmethod
    def scan(bus: I2cBus) -> list[int]:
        found: list[int] = []
        for address in range(0x48, 0x4C):
            try:
                bus.read_byte(address)
            except OSError:
                continue
            found.append(address)
        return found

