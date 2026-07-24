"""INA226 total-input power monitor driver."""

from __future__ import annotations

from typing import Protocol

from .config import Ina226Config
from .exceptions import HardwareNotFound
from .models import PowerSample


class I2cWordBus(Protocol):
    def read_i2c_block_data(self, address: int, register: int, length: int) -> list[int]: ...
    def write_i2c_block_data(
        self, address: int, register: int, data: list[int]
    ) -> None: ...
    def close(self) -> None: ...


class INA226:
    REG_CONFIG = 0x00
    REG_SHUNT_VOLTAGE = 0x01
    REG_BUS_VOLTAGE = 0x02
    REG_POWER = 0x03
    REG_CURRENT = 0x04
    REG_CALIBRATION = 0x05
    REG_MASK_ENABLE = 0x06

    CONFIG_RESERVED = 0x4000
    MODE_CONTINUOUS_SHUNT_BUS = 0b111
    MASK_MATH_OVERFLOW = 1 << 2
    AVERAGING_CODES = {
        1: 0b000,
        4: 0b001,
        16: 0b010,
        64: 0b011,
        128: 0b100,
        256: 0b101,
        512: 0b110,
        1024: 0b111,
    }
    CONVERSION_TIME_CODES = {
        140: 0b000,
        204: 0b001,
        332: 0b010,
        588: 0b011,
        1100: 0b100,
        2116: 0b101,
        4156: 0b110,
        8244: 0b111,
    }

    def __init__(self, bus: I2cWordBus, config: Ina226Config):
        self.bus = bus
        self.config = config
        self.configure()

    def _write_u16(self, register: int, value: int) -> None:
        try:
            self.bus.write_i2c_block_data(
                self.config.address, register, [(value >> 8) & 0xFF, value & 0xFF]
            )
        except OSError as exc:
            raise HardwareNotFound(
                f"INA226 not responding at 0x{self.config.address:02x}"
            ) from exc

    def _read_u16(self, register: int) -> int:
        try:
            data = self.bus.read_i2c_block_data(self.config.address, register, 2)
        except OSError as exc:
            raise HardwareNotFound(
                f"INA226 not responding at 0x{self.config.address:02x}"
            ) from exc
        if len(data) != 2:
            raise HardwareNotFound("INA226 returned an incomplete register value")
        return (data[0] << 8) | data[1]

    @staticmethod
    def _signed(value: int) -> int:
        return value - 0x10000 if value & 0x8000 else value

    def configure(self) -> None:
        average_code = self.AVERAGING_CODES[self.config.averaging]
        conversion_code = self.CONVERSION_TIME_CODES[self.config.conversion_time_us]
        config_register = (
            self.CONFIG_RESERVED
            | (average_code << 9)
            | (conversion_code << 6)
            | (conversion_code << 3)
            | self.MODE_CONTINUOUS_SHUNT_BUS
        )
        self._write_u16(self.REG_CONFIG, config_register)
        self._write_u16(self.REG_CALIBRATION, self.config.calibration)

    def read(self) -> PowerSample:
        shunt_raw = self._signed(self._read_u16(self.REG_SHUNT_VOLTAGE))
        bus_raw = self._read_u16(self.REG_BUS_VOLTAGE)
        current_raw = self._signed(self._read_u16(self.REG_CURRENT))
        power_raw = self._read_u16(self.REG_POWER)
        mask = self._read_u16(self.REG_MASK_ENABLE)
        return PowerSample(
            bus_volts=bus_raw * 0.00125,
            shunt_volts=shunt_raw * 0.0000025,
            current_amps=current_raw * self.config.current_lsb_a,
            power_watts=power_raw * self.config.power_lsb_w,
            math_overflow=bool(mask & self.MASK_MATH_OVERFLOW),
            address=self.config.address,
        )
