# RDK 40Pin 通用拓展板 V1.0 当前硬件参考

> 本文描述 **2026-07-24 最终导出的实际电路**。  
> `hardware_design_spec.md`、`connector_map.csv`、`preliminary_bom.csv` 是早期设计输入，
> 与最终电路不一致时，以 `hardware/board_v1.yaml`、`.enet` 和原理图为准。

## 1. 权威数据与验证

机器可读真值位于 `hardware/board_v1.yaml`，其中保存了原理图、网表和 PCB PDF 的
SHA256。运行下面的命令可同时检查文件指纹、40Pin、外部连接器和关键芯片：

```bash
python tools/validate_hardware_manifest.py
```

## 2. 电源结构

| 电源域 | 来源 | 用途 | 软件控制 |
|---|---|---|---|
| `12V_IN` | DC007 或 XT30，经 PTC、TVS、Q1 和 R38 | 两路降压、CAN_OUT 12V | 无 |
| `5V_SYS` | U1 TPS5450，约 5.08V | 主机 40Pin 2/4、通信口、蜂鸣器、继电器模块 | 无 |
| `5V_SERVO` | U9 TPS5450，约 5.08V | 舵机、风扇、辅助输出 | 无 |
| `3.3V` | 主机 40Pin 1/17 | 数字逻辑、ADS1115、INA226 | 无 |

DC007 与 XT30 在当前版本中接到同一输入节点，不具备双电源 OR-ing；只能连接一个电源。
`5V_SYS` 直接连接主机 40Pin 2/4，也没有断开跳帽。

## 3. 40Pin 实际信号

| 物理针 | 板上网络 | Pi 4 BCM/功能 | V1 驱动 |
|---:|---|---|---|
| 1/17 | 3.3V | 3.3V | 电源 |
| 2/4 | 5V_SYS | 5V | 电源，注意倒灌 |
| 3/5 | I2C5_SDA/SCL | BCM2/3，I2C1 | `/dev/i2c-1` |
| 8/10 | UART1_TX/RX | BCM14/15 | `/dev/serial0` |
| 11/13 | UART7_TX/RX_SW | BCM17/27 | 不支持硬件 UART |
| 15/22 | UART2_TX/RX | BCM22/25 | 不支持硬件 UART |
| 16/36 | UART6_TX/RX | BCM23/16 | 不支持硬件 UART |
| 18 | SPI1_CS2 | BCM24 | 手动 SPI 片选 |
| 19/21/23 | SPI1_MOSI/MISO/SCL | BCM10/9/11，SPI0 | 支持 |
| 24/26 | SPI1_CS0/CS1 | BCM8/7，SPI0 CE0/CE1 | 支持 |
| 27/28 | I2C0_SDA/SCL | BCM0/1，HAT ID EEPROM | 默认禁用 |
| 29/31/37 | KEY2/KEY1/KEY0 | BCM5/6/26 | 输入，高有效 |
| 32/33 | PWM32/PWM33 | BCM12/13 | 舵机 0/1 |
| 35 | BUZZ | BCM19 | 输出，高有效 |
| 38/40 | RELAY1/RELAY2 | BCM20/21 | 主机控制低有效 |

所有未列出的 40Pin 脚为 GND 或未连接，完整逐针数据见 YAML。

## 4. 外部连接器

### UART 和 RC

连接器针序均以 PCB 丝印 pin 1 为起点：

| 接口 | pin 1 | pin 2 | pin 3 | pin 4 | 说明 |
|---|---|---|---|---|---|
| UART1 | 5V_SYS | TX | RX | GND | Pi 4 唯一正式支持的硬件 UART |
| UART7 | 5V_SYS | TX | RX | GND | Pi 4 仅保留映射 |
| UART2 | 5V_SYS | TX | RX | GND | Pi 4 仅保留映射 |
| UART6 | 5V_SYS | TX | RX | GND | Pi 4 仅保留映射 |
| RC接收 | 5V_SYS | RC 输入 | GND | GND | Q4 反相后输出到 `RC` |

三针跳帽 `RC与串口切换` 的 pin 2 是 `UART7_RX_SW`，短接 1-2 选择反相 RC，
短接 2-3 选择 UART7_RX。Pi 4 首版驱动不实现这一路软串口。

UART 信号均为 3.3V，不耐受 5V UART 电平。

### I²C

I2C5A/B 和 I2C0A/B 的针序都是：

```text
1=5V_SYS, 2=SDA, 3=SCL, 4=GND
```

- I2C5A/B 完全并联，在 Pi 4 上是 I2C1。
- I2C0A/B 完全并联，在 Pi 4 上占用 HAT ID EEPROM 的 BCM0/1，驱动默认拒绝打开。
- 两组总线各有 4.7kΩ 上拉到 3.3V；连接器虽然提供 5V，但 SDA/SCL 仍是 3.3V。

### SPI

| 针 | SPI1A | SPI1B |
|---:|---|---|
| 1 | 5V_SYS | 5V_SYS |
| 2 | GND | GND |
| 3 | MOSI | MOSI |
| 4 | MISO | MISO |
| 5 | SCLK（丝印 SCL） | SCLK（丝印 SCL） |
| 6 | CS0 | CS0 |
| 7 | CS1 | CS2 |
| 8 | 3.3V | 3.3V |

两个接口共享总线和 CS0。因此分别安装在 A/B 的两个设备不能同时都使用 CS0。
Pi 4 中这些信号属于 SPI0，不是 SPI1。

### ADC

`ADS1115` 五针接口：

```text
1=AIN0, 2=AIN1, 3=AIN2, 4=AIN3, 5=GND
```

每路外部输入经过 39kΩ/10kΩ 分压、10kΩ/100nF 滤波和 BAT54 钳位。
外部电压换算系数为 4.9，设计量程为 0–16V。U14 使用 3.3V 供电。

当前原理图中 U14 `ADDR` 悬空，硬件修订必须接 GND，地址固定为 `0x48`。

### INA226 输入功率监控

U16 位于 R38 10mΩ 高边分流电阻两端：

- I²C 总线：板上 I2C5，Pi 4 `/dev/i2c-1`
- 地址：A0/A1 接 GND，`0x40`
- VBUS：`12V_IN`
- 默认软件量程：250µA/bit，最大约 8.19A

该器件只监控总 12V 输入；最终板上没有早期文档中的第二、第三颗 INA226。

### 舵机、蜂鸣器、继电器模块

- 舵机0/1：`1=5V_SERVO, 2=PWM, 3=GND`，信号来自 BCM12/13。
- FAN：`1=5V_SERVO, 2=GND`，固定供电，不支持调速或开关。
- 5V_SERVO：`1=5V_SERVO, 2=GND`，固定辅助输出。
- 板载蜂鸣器由 BCM19 高电平驱动 Q8 后导通。
- BUZZ 两针口当前为 `1=原始 BUZZ GPIO, 2=5V_SYS`，不是安全的功率开关输出。
- 继电器1/2：`1=5V_SYS, 2=3.3V控制输出, 3=GND`，用于外部继电器模块。
  主机 RELAY GPIO 拉低时，AO3401A 导通，连接器 pin 2 输出 3.3V。

### CAN

- CAN_IN：`1=CAN_H, 2=CAN_L, 3=GND`
- CAN_OUT：`1=12V_IN, 2=CAN_H, 3=CAN_L, 4=GND`

板上没有 CAN 控制器、收发器、终端电阻或受软件控制的 CAN 信号。树莓派必须另接
CAN 控制器和物理层，才能使用这两个连接器。

## 5. 跨平台适配规则

其他开发板的适配 Agent 应：

1. 保持 `board_v1.yaml` 的连接器和电气网络不变。
2. 新增 host profile，将物理 40Pin 映射为目标 SoC GPIO 和 Linux 设备。
3. 分别判断硬件 UART、I²C、SPI、PWM 是否能路由到现有物理针；不能时明确禁用。
4. 不根据 `I2C5`、`SPI1`、`UART7` 等丝印数字猜测 Linux 总线编号。
5. CAN、固定电源口和风扇不得声明为软件可控。

Raspberry Pi 物理针、BCM、SPI0、I²C 和串口映射依据
[Raspberry Pi 官方硬件文档](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html)；
尤其注意板上名为 `SPI1` 的网络落在 Pi 的 SPI0 引脚上。
