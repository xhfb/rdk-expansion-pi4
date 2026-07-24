#!/usr/bin/env bash
set -euo pipefail

bundle_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$bundle_dir"

if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 is not installed" >&2
    exit 1
fi

python3 - <<'PY'
import sys

if sys.version_info < (3, 11):
    raise SystemExit("ERROR: Python 3.11 or newer is required")
print("Using Python", sys.version.split()[0])
PY

python3 -m venv --system-site-packages .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install .

echo
echo "Driver installed in: $bundle_dir/.venv"
echo "Before use, enable I2C, SPI and UART hardware with raspi-config."
echo "Disable the serial login console, then reboot."
echo "Start pigpiod with: sudo systemctl enable --now pigpiod"
echo "Activate with: source '$bundle_dir/.venv/bin/activate'"
echo "Diagnose with: rdk-expansion doctor"
echo
echo "This installer does not modify /boot/firmware/config.txt."
