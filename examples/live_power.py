#!/usr/bin/env python3
"""Live INA226 input-power monitor for the RDK expansion board."""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from collections import deque

from rdk_expansion import ExpansionBoard


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Watch live 12V input power")
    parser.add_argument(
        "--interval",
        type=float,
        default=0.5,
        help="sample interval in seconds (default: 0.5)",
    )
    parser.add_argument(
        "--window",
        type=int,
        default=20,
        help="rolling average window size (default: 20)",
    )
    parser.add_argument(
        "--config",
        help="optional TOML config path",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.interval <= 0:
        print("ERROR: --interval must be > 0", file=sys.stderr)
        return 2
    if args.window < 1:
        print("ERROR: --window must be >= 1", file=sys.stderr)
        return 2

    powers: deque[float] = deque(maxlen=args.window)
    currents: deque[float] = deque(maxlen=args.window)
    print("Live power monitor  Ctrl+C to stop")
    print("-" * 72)

    try:
        with ExpansionBoard.open(args.config) as board:
            while True:
                sample = board.power.read()
                powers.append(sample.power_watts)
                currents.append(sample.current_amps)
                stamp = time.strftime("%H:%M:%S")
                avg_p = statistics.fmean(powers)
                avg_i = statistics.fmean(currents)
                line = (
                    f"\r{stamp}  "
                    f"V={sample.bus_volts:7.3f}V  "
                    f"I={sample.current_amps:7.4f}A  "
                    f"P={sample.power_watts:7.3f}W  "
                    f"avgP={avg_p:7.3f}W  "
                    f"avgI={avg_i:7.4f}A  "
                    f"shunt={sample.shunt_volts * 1000:6.3f}mV"
                    f"{'  OVFL' if sample.math_overflow else '      '}"
                )
                sys.stdout.write(line)
                sys.stdout.flush()
                time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nstopped")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
