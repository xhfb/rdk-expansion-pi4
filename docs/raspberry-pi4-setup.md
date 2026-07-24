# Raspberry Pi 4 部署与真机验收

正式基线：

```text
Raspberry Pi 4
aarch64
Linux 6.12.47+rpt-rpi-v8
Python 3.11+
```

## 1. 电气准备

1. 将 ADS1115 ADDR 接 GND。
2. 只选择一种主机供电方式：
   - 由拓展板 5V_SYS 通过 40Pin 给 Pi 供电；或
   - 断开 5V_SYS→40Pin，再由 Pi USB-C 供电。
3. DC007 与 XT30 只能连接一个电源。
4. 首次上电前检查 12V_IN、5V_SYS、5V_SERVO、3.3V 和 GND 是否短路。

## 2. 启用 Linux 接口

使用 `sudo raspi-config`：

- 启用 I2C。
- 启用 SPI。
- 启用串口硬件。
- 禁用串口登录控制台。

重启后应存在：

```bash
ls -l /dev/i2c-1 /dev/spidev0.0 /dev/spidev0.1 /dev/serial0
```

不要为本板启用 GPIO0/1 上的 I2C0，除非明确接受占用 HAT ID EEPROM 总线。

接口启用、UART 硬件与串口控制台的配置方式以
[Raspberry Pi 官方配置文档](https://www.raspberrypi.com/documentation/configuration/computers/raspberry-pi.html)
为准。本项目不硬编码 `ttyAMA*`，始终使用稳定别名 `/dev/serial0`。

## 3. 安装

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip python3-dev build-essential \
  i2c-tools
./scripts/install_pi4.sh
source .venv/bin/activate
```

将运行用户加入设备组后重新登录：

```bash
sudo usermod -aG i2c,spi,dialout,gpio "$USER"
```

本项目不会自动修改 `/boot/firmware/config.txt`。

### 3.1 pigpiod（GPIO / 蜂鸣器 / 继电器 / 舵机）

Debian（含 Trixie）通常 **只提供 pigpio 客户端库**，`apt` 中没有可用的
`pigpio` / `pigpiod` 守护进程包（官方说明：服务端与 Debian 内核不兼容）。
Raspberry Pi 4 上需要从源码编译安装：

```bash
curl -sL -o /tmp/pigpio.tar.gz \
  https://api.github.com/repos/joan2937/pigpio/tarball/refs/tags/v79
mkdir -p /tmp/pigpio-src
tar -xzf /tmp/pigpio.tar.gz -C /tmp/pigpio-src --strip-components=1
make -C /tmp/pigpio-src -j"$(nproc)"
sudo make -C /tmp/pigpio-src install
sudo ldconfig
```

建议用 systemd 开机自启：

```bash
sudo tee /etc/systemd/system/pigpiod.service >/dev/null <<'EOF'
[Unit]
Description=pigpio daemon
After=network.target

[Service]
Type=forking
ExecStart=/usr/local/bin/pigpiod
ExecStop=/bin/kill -TERM $MAINPID
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now pigpiod
```

若启动失败并提示无法锁定 `/var/run/pigpio.pid`，先结束已有进程再重试：

```bash
sudo killall pigpiod 2>/dev/null || true
sudo rm -f /var/run/pigpio.pid
sudo systemctl reset-failed pigpiod
sudo systemctl start pigpiod
```

没有 `pigpiod` 时，I²C（INA226 / ADS1115）、SPI、UART 仍可使用；
按键、蜂鸣器、继电器、舵机不可用。

## 4. 安全诊断

```bash
rdk-expansion doctor
rdk-expansion pinout
rdk-expansion self-test
```

`self-test` 默认只读。只有确认无危险负载后才执行：

```bash
rdk-expansion self-test --actuate
```

## 5. 分项验收

```bash
rdk-expansion adc --all
rdk-expansion monitor --count 10
rdk-expansion button-watch --seconds 30
rdk-expansion buzzer --seconds 0.2
rdk-expansion relay 0 on --hold 2
rdk-expansion relay 0 off
rdk-expansion servo 0 --pulse-us 1500 --hold 2
rdk-expansion servo 0 --disable
rdk-expansion uart-loopback --bytes 1048576 --baud 115200
```

`relay` 和 `servo` 命令退出时总会恢复安全状态；需要保持动作以便测量时使用
`--hold 秒数`。这不是常驻控制接口，长期控制请使用 Python API 中的上下文管理器。

验收目标：

- 舵机脉冲误差不超过 ±10µs。
- ADC 四点标定后误差不超过 ±2% 或 ±50mV。
- INA226 母线电压误差不超过 ±1%，标定后电流误差不超过 ±3%。
- UART1 115200 波特率、1MiB 回环无错误。
- 进程退出后蜂鸣器关闭、继电器输出关闭、舵机停止脉冲。
