"""Command-line diagnostics and board controls."""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
from pathlib import Path
from typing import Any

from .board import ExpansionBoard
from .exceptions import RdkExpansionError


PINOUT = (
    ("I2C5", "3/5", "BCM2/3", "/dev/i2c-1"),
    ("UART1", "8/10", "BCM14/15", "/dev/serial0"),
    ("UART7", "11/13", "BCM17/27", "unsupported"),
    ("UART2", "15/22", "BCM22/25", "unsupported"),
    ("UART6", "16/36", "BCM23/16", "unsupported"),
    ("SPI MOSI/MISO/SCLK", "19/21/23", "BCM10/9/11", "SPI0"),
    ("SPI CS0/CS1/CS2", "24/26/18", "BCM8/7/24", "SPI0/manual"),
    ("I2C0", "27/28", "BCM0/1", "disabled: HAT ID"),
    ("KEY2/KEY1/KEY0", "29/31/37", "BCM5/6/26", "active high"),
    ("PWM0/PWM1", "32/33", "BCM12/13", "pigpio servo"),
    ("BUZZ", "35", "BCM19", "active high"),
    ("RELAY1/RELAY2", "38/40", "BCM20/21", "host active low"),
)


def _model() -> str:
    path = Path("/proc/device-tree/model")
    if not path.exists():
        return "unknown"
    return path.read_bytes().rstrip(b"\0").decode("utf-8", "replace")


def _group_names() -> set[str]:
    try:
        import grp
    except ImportError:
        return set()
    try:
        return {grp.getgrgid(gid).gr_name for gid in os.getgroups()}
    except (AttributeError, KeyError, PermissionError):
        return set()


def _scan_i2c(bus: Any, addresses: list[int]) -> list[int]:
    found: list[int] = []
    for address in addresses:
        try:
            bus.read_byte(address)
        except OSError:
            continue
        found.append(address)
    return found


def cmd_doctor(args: argparse.Namespace) -> int:
    expected_devices = (
        "/dev/i2c-1",
        "/dev/spidev0.0",
        "/dev/spidev0.1",
        "/dev/serial0",
    )
    report: dict[str, Any] = {
        "model": _model(),
        "architecture": platform.machine(),
        "kernel": platform.release(),
        "python": platform.python_version(),
        "devices": {},
        "device_access": {},
        "groups": sorted(_group_names()),
        "i2c_addresses": [],
        "capabilities": [],
        "checks": {},
        "warnings": [
            "ADS1115 ADDR must be tied to GND before validation",
            "5V_SYS directly feeds host pins 2/4; use only one host power source",
            "DC007 and XT30 must not be powered simultaneously on current V1",
        ],
    }
    for device in expected_devices:
        report["devices"][device] = Path(device).exists()
        report["device_access"][device] = os.access(device, os.R_OK | os.W_OK)
    with ExpansionBoard.open(args.config) as board:
        report["capabilities"] = [
            {"name": cap.name, "status": cap.status, "detail": cap.detail}
            for cap in board.capabilities()
        ]
        try:
            bus = board.open_i2c("i2c5")
        except RdkExpansionError as exc:
            report["warnings"].append(str(exc))
        else:
            try:
                report["i2c_addresses"] = [
                    f"0x{address:02x}"
                    for address in _scan_i2c(bus, [0x40, 0x48, 0x49, 0x4A, 0x4B])
                ]
            finally:
                bus.close()
    capabilities = {item["name"]: item["status"] for item in report["capabilities"]}
    report["checks"] = {
        "raspberry_pi_4": "Raspberry Pi 4" in report["model"],
        "aarch64": report["architecture"] == "aarch64",
        "tested_kernel": report["kernel"] == "6.12.47+rpt-rpi-v8",
        "python_3_11_plus": sys.version_info >= (3, 11),
        "required_devices": all(report["devices"].values()),
        "device_permissions": all(report["device_access"].values()),
        "pigpiod": capabilities.get("gpio") == "supported",
        "ina226_0x40": "0x40" in report["i2c_addresses"],
        "ads1115_0x48": "0x48" in report["i2c_addresses"],
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"model: {report['model']}")
        print(f"architecture: {report['architecture']}")
        print(f"kernel: {report['kernel']}")
        print(f"python: {report['python']}")
        for device, exists in report["devices"].items():
            access = report["device_access"][device]
            print(
                f"{device}: {'present' if exists else 'missing'}, "
                f"{'read/write' if access else 'no access'}"
            )
        print("groups:", ", ".join(report["groups"]) or "(none)")
        print("i2c:", ", ".join(report["i2c_addresses"]) or "(none detected)")
        for cap in report["capabilities"]:
            detail = f" - {cap['detail']}" if cap["detail"] else ""
            print(f"{cap['name']}: {cap['status']}{detail}")
        for warning in report["warnings"]:
            print(f"WARNING: {warning}")
        for check, passed in report["checks"].items():
            print(f"check {check}: {'PASS' if passed else 'FAIL'}")
    return 0 if all(report["checks"].values()) else 2


def cmd_pinout(args: argparse.Namespace) -> int:
    print(f"{'Board signal':24} {'Physical':10} {'Pi 4 BCM':14} Linux/status")
    for signal, physical, bcm, status in PINOUT:
        print(f"{signal:24} {physical:10} {bcm:14} {status}")
    return 0


def cmd_self_test(args: argparse.Namespace) -> int:
    with ExpansionBoard.open(args.config) as board:
        for cap in board.capabilities():
            print(f"{cap.name}: {cap.status} {cap.detail}".rstrip())
        bus = board.open_i2c("i2c5")
        try:
            found = _scan_i2c(bus, [0x40, 0x48, 0x49, 0x4A, 0x4B])
        finally:
            bus.close()
        print("i2c detected:", " ".join(f"0x{x:02x}" for x in found) or "none")
        if 0x40 not in found:
            print("FAIL: INA226 0x40 not detected")
        if 0x48 not in found:
            print("FAIL: ADS1115 0x48 not detected; verify ADDR is tied to GND")
        if args.actuate:
            print("actuation: buzzer, relays, servo centres")
            board.buzzer.beep(0.1)
            for relay in board.relays:
                relay.on()
                time.sleep(0.1)
                relay.off()
            for servo in board.servos:
                servo.set_angle(90)
                time.sleep(0.2)
                servo.disable()
    return 0 if 0x40 in found and 0x48 in found else 1


def cmd_monitor(args: argparse.Namespace) -> int:
    with ExpansionBoard.open(args.config) as board:
        for _ in range(args.count):
            sample = board.power.read()
            print(
                f"bus={sample.bus_volts:.4f}V "
                f"shunt={sample.shunt_volts * 1000:.3f}mV "
                f"current={sample.current_amps:.4f}A "
                f"power={sample.power_watts:.4f}W "
                f"overflow={sample.math_overflow}"
            )
            if args.count > 1:
                time.sleep(args.interval)
    return 0


def cmd_adc(args: argparse.Namespace) -> int:
    channels = range(4) if args.all else (args.channel,)
    with ExpansionBoard.open(args.config) as board:
        for channel in channels:
            sample = board.adc.read(channel)
            print(
                f"AIN{channel}: raw={sample.raw} adc={sample.adc_volts:.6f}V "
                f"input={sample.input_volts:.6f}V"
            )
    return 0


def cmd_button_watch(args: argparse.Namespace) -> int:
    with ExpansionBoard.open(args.config) as board:
        buttons = board.buttons
        for name in ("key0", "key1", "key2"):
            button = getattr(buttons, name)
            button.when_pressed = lambda _button, n=name: print(f"{n} pressed")
        deadline = time.monotonic() + args.seconds
        while time.monotonic() < deadline:
            time.sleep(0.05)
    return 0


def cmd_buzzer(args: argparse.Namespace) -> int:
    with ExpansionBoard.open(args.config) as board:
        board.buzzer.beep(args.seconds)
    return 0


def cmd_relay(args: argparse.Namespace) -> int:
    with ExpansionBoard.open(args.config) as board:
        relay = board.relays[args.channel]
        relay.on() if args.state == "on" else relay.off()
        print(f"relay {args.channel}: {args.state}")
        if args.hold > 0:
            time.sleep(args.hold)
    return 0


def cmd_servo(args: argparse.Namespace) -> int:
    with ExpansionBoard.open(args.config) as board:
        servo = board.servos[args.channel]
        if args.disable:
            servo.disable()
            print(f"servo {args.channel}: disabled")
        elif args.pulse_us is not None:
            servo.set_pulse_us(args.pulse_us)
            print(f"servo {args.channel}: {args.pulse_us}us")
            if args.hold > 0:
                time.sleep(args.hold)
        else:
            servo.set_angle(args.angle)
            print(f"servo {args.channel}: {args.angle}deg")
            if args.hold > 0:
                time.sleep(args.hold)
    return 0


def cmd_uart_loopback(args: argparse.Namespace) -> int:
    pattern = bytes(index % 251 for index in range(args.bytes))
    with ExpansionBoard.open(args.config) as board:
        serial_port = board.open_uart("uart1", baudrate=args.baud, timeout=args.timeout)
        try:
            serial_port.reset_input_buffer()
            serial_port.write(pattern)
            serial_port.flush()
            received = serial_port.read(len(pattern))
        finally:
            serial_port.close()
    if received != pattern:
        print(f"FAIL: sent={len(pattern)} received={len(received)}")
        return 1
    print(f"PASS: {len(pattern)} bytes at {args.baud} baud")
    return 0


def cmd_spi_transfer(args: argparse.Namespace) -> int:
    payload = [int(token, 16) for token in args.hex_bytes]
    with ExpansionBoard.open(args.config) as board:
        with board.open_spi(
            args.port, max_speed_hz=args.speed, mode=args.mode
        ) as spi:
            received = spi.xfer2(payload)
    print(" ".join(f"{byte:02x}" for byte in received))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rdk-expansion")
    parser.add_argument("--config", help="explicit TOML configuration")
    commands = parser.add_subparsers(dest="command", required=True)

    doctor = commands.add_parser("doctor")
    doctor.add_argument("--json", action="store_true")
    doctor.set_defaults(func=cmd_doctor)

    pinout = commands.add_parser("pinout")
    pinout.set_defaults(func=cmd_pinout)

    self_test = commands.add_parser("self-test")
    self_test.add_argument("--actuate", action="store_true")
    self_test.set_defaults(func=cmd_self_test)

    monitor = commands.add_parser("monitor")
    monitor.add_argument("--count", type=int, default=1)
    monitor.add_argument("--interval", type=float, default=1.0)
    monitor.set_defaults(func=cmd_monitor)

    adc = commands.add_parser("adc")
    adc_group = adc.add_mutually_exclusive_group(required=True)
    adc_group.add_argument("--channel", type=int, choices=range(4))
    adc_group.add_argument("--all", action="store_true")
    adc.set_defaults(func=cmd_adc)

    buttons = commands.add_parser("button-watch")
    buttons.add_argument("--seconds", type=float, default=30.0)
    buttons.set_defaults(func=cmd_button_watch)

    buzzer = commands.add_parser("buzzer")
    buzzer.add_argument("--seconds", type=float, default=0.2)
    buzzer.set_defaults(func=cmd_buzzer)

    relay = commands.add_parser("relay")
    relay.add_argument("channel", type=int, choices=(0, 1))
    relay.add_argument("state", choices=("on", "off"))
    relay.add_argument("--hold", type=float, default=0.0)
    relay.set_defaults(func=cmd_relay)

    servo = commands.add_parser("servo")
    servo.add_argument("channel", type=int, choices=(0, 1))
    servo_group = servo.add_mutually_exclusive_group(required=True)
    servo_group.add_argument("--pulse-us", type=int)
    servo_group.add_argument("--angle", type=float)
    servo_group.add_argument("--disable", action="store_true")
    servo.add_argument("--hold", type=float, default=0.0)
    servo.set_defaults(func=cmd_servo)

    uart = commands.add_parser("uart-loopback")
    uart.add_argument("--bytes", type=int, default=4096)
    uart.add_argument("--baud", type=int, default=115200)
    uart.add_argument("--timeout", type=float, default=5.0)
    uart.set_defaults(func=cmd_uart_loopback)

    spi = commands.add_parser("spi-transfer")
    spi.add_argument("port", choices=("spi1a.cs0", "spi1a.cs1", "spi1b.cs0", "spi1b.cs2"))
    spi.add_argument("hex_bytes", nargs="+")
    spi.add_argument("--speed", type=int, default=1_000_000)
    spi.add_argument("--mode", type=int, choices=(0, 1, 2, 3), default=0)
    spi.set_defaults(func=cmd_spi_transfer)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (RdkExpansionError, OSError, TimeoutError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
