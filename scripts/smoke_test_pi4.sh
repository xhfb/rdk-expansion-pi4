#!/usr/bin/env bash
set -euo pipefail

bundle_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$bundle_dir"

if [[ ! -x .venv/bin/python ]]; then
    echo "ERROR: run scripts/install_pi4.sh first" >&2
    exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate
python -c "import rdk_expansion; print('rdk_expansion', rdk_expansion.__version__)"
rdk-expansion pinout

echo
echo "Software import and CLI startup passed."
echo "Run 'rdk-expansion doctor' for hardware checks."
