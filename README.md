# RDK 40Pin 拓展板 · Raspberry Pi 4 驱动程序

面向 **Raspberry Pi 4** 的 RDK 40Pin 通用拓展板驱动包，提供 Python 库
`rdk_expansion` 与命令行工具 `rdk-expansion`。

本仓库是 **树莓派专用驱动**，不是全平台 HAL。其他主机请另行适配。

## 支持平台

| 项目 | 基线 |
|---|---|
| 主机 | Raspberry Pi 4 |
| 架构 | aarch64 |
| 内核 | `6.12.47+rpt-rpi-v8`（已验收） |
| Python | 3.11+（含 3.13） |

板上已对接：

- **INA226**（I²C `0x40`）：12V 输入功率监控
- **ADS1115**（I²C `0x48`）：4 路 ADC（经分压，约 0–16V）
- **GPIO**：按键 / 蜂鸣器 / 继电器 / 舵机 PWM（依赖 `pigpiod`）
- **SPI / UART1**：总线与串口访问

真机已验证：I²C 寻址、功率读取、ADC 读取、板载蜂鸣器。

## 首先阅读

- [Pi 4 部署与验收](docs/raspberry-pi4-setup.md)
- [当前硬件参考](docs/current-hardware-reference.md)
- [硬件修订清单](docs/hardware-revision-checklist.md)
- `hardware/board_v1.yaml`：机器可读硬件清单

## 安装

```bash
# 1. 启用 I2C / SPI / 硬件串口，并禁用串口登录控制台
sudo raspi-config

# 2. 安装驱动
./scripts/install_pi4.sh
source .venv/bin/activate

# 3. 启动 pigpiod（GPIO / 蜂鸣器 / 继电器 / 舵机需要）
sudo systemctl enable --now pigpiod

# 4. 诊断
rdk-expansion doctor
rdk-expansion pinout
rdk-expansion self-test
```

将用户加入设备组后重新登录：

```bash
sudo usermod -aG i2c,spi,dialout,gpio "$USER"
```

### pigpiod 说明

Debian / Raspberry Pi OS（如 Trixie）往往 **只打包 pigpio 客户端**，没有
`pigpiod` 守护进程 apt 包。此时需从源码安装，例如：

```bash
curl -sL -o pigpio.tar.gz \
  https://api.github.com/repos/joan2937/pigpio/tarball/refs/tags/v79
mkdir -p pigpio-src && tar -xzf pigpio.tar.gz -C pigpio-src --strip-components=1
make -C pigpio-src -j"$(nproc)"
sudo make -C pigpio-src install
sudo ldconfig
sudo pigpiod
```

详见 [Pi 4 部署文档](docs/raspberry-pi4-setup.md)。

## 快速使用

```bash
rdk-expansion monitor --count 10          # 功率采样
rdk-expansion adc --all                   # 四路 ADC
rdk-expansion buzzer --seconds 0.3        # 蜂鸣器
python examples/live_power.py             # 实时功率监视
```

Python API：

```python
from rdk_expansion import ExpansionBoard

with ExpansionBoard.open() as board:
    print(board.capabilities())
    print(board.adc.read(0))
    print(board.power.read())
    if board.buttons.key0.is_pressed:
        board.buzzer.beep(0.1)
```

GPIO 和舵机依赖本机 `pigpiod`。守护进程不可用时，I²C、SPI 和 UART 仍可使用；
GPIO/PWM 操作会抛出明确异常。板对象退出时关闭蜂鸣器与继电器，并停止舵机脉冲。

## 上电前警告

- ADS1115 `ADDR` 应接 GND，地址固定为 `0x48`。
- `5V_SYS` 直接接 40Pin 2/4；不得同时从拓展板和 Pi USB-C 给主机供电。
- DC007 与 XT30 不得同时连接两个电源。
- BUZZ 外接口暴露的是原始 GPIO，不得直接连接普通两线 5V 蜂鸣器。

## 仓库结构

```text
src/rdk_expansion/   Python 驱动与 CLI
examples/            示例（含 live_power.py）
docs/                硬件与部署文档
hardware/            board_v1.yaml
scripts/             Pi 4 安装与冒烟脚本
```
