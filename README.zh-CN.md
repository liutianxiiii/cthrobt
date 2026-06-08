# cthrobt — Nintendo 手柄控制器（PC 端）

PC 端 Python 程序套件，读取 Nintendo Switch Pro 手柄的输入状态，并通过 TCP 将其流式发送给 STM32 开发板（真实硬件或 Renode 模拟）。

> [English README](README.md)

## 架构

```
┌─────────────────────────────────────────────┐
│               cthrobt (PC 端)                │
│                                             │
│  controller.py ──TCP JSON──► bridge.py      │
│     (手柄 / mock 模式)        (STM32 端)     │
│                                             │
│  simulator.py ◄──TCP JSON── controller.py  │
│     (调试用，无需 Renode)                    │
│                                             │
│  compare.py                                 │
│     发送日志 ──► 比对 ──► test_report.md    │
└─────────────────────────────────────────────┘
```

### 文件说明

| 文件 | 作用 |
|------|------|
| `controller.py` | 通过 pygame 读取 Nintendo 手柄，将状态以 JSON 通过 TCP 发送。支持 `--mock` 模式，无需真实硬件即可测试 |
| `simulator.py` | 独立 TCP 服务端 —— 接收数据包并打印。作为 Renode 的调试替代方案 |
| `compare.py` | 比对发送的 JSONL 日志与 STM32 UART3 输出，生成 Markdown 测试报告 |
| `config.ini` | 所有运行时配置：主机/端口、协议、死区、按钮/轴映射 |

## 通信协议

### JSON 格式（默认）
```json
{"buttons":{"A":true,"B":false,...},"axes":{"LX":0.5,"LY":0.0,"RX":-0.3,"RY":0.0},"hat":[0,1]}
```
以换行分隔的 ASCII 文本通过 TCP 发送。

### 二进制格式（14 字节，可选）
```
[0xAA][uint16 btn_mask][int8 hat_x][int8 hat_y][int16 LX][int16 LY][int16 RX][int16 RY][XOR 校验和]
```
在 `config.ini` 中设置 `protocol = binary` 即可启用。

## 快速开始

### 环境要求
- Python 3.9+
- `pip install -r requirements.txt`（Python 3.14+ 请使用 pygame-ce）

### 安装
```bash
# macOS / Linux
bash scripts/setup.sh

# Windows
scripts\setup.bat
```

### 使用真实硬件运行
```bash
# 终端 1（STM32 端）—— 启动 bridge.py 或烧录到真实开发板
# 终端 2
python controller.py                  # 真实手柄
python controller.py --config my.ini  # 自定义配置文件
```

### Mock 模式（无需真实手柄）
```bash
# macOS / Linux
bash scripts/run_mock.sh [count] [interval_sec]

# Windows
scripts\run_mock.bat [count] [interval_sec]
```
默认：发送 20 个数据包，间隔 0.5 秒。
发送的数据包会记录到 `logs/mock_sent_<timestamp>.jsonl`。

### 独立调试模式（无需 STM32/Renode）
```bash
# 终端 1
bash scripts/run_simulator.sh   # 或 scripts\run_simulator.bat

# 终端 2
bash scripts/run_mock.sh
```

### 生成测试报告
```bash
bash scripts/compare.sh         # macOS / Linux
scripts\compare.bat             # Windows
```
报告保存到 `logs/test_report_<timestamp>.md`。

## 配置说明（`config.ini`）

| 分区 | 键 | 默认值 | 说明 |
|---------|-----|---------|-------------|
| `[network]` | `host` | `127.0.0.1` | 目标 IP（STM32 或本地模拟器） |
| `[network]` | `port` | `7777` | 目标端口 |
| `[network]` | `protocol` | `json` | `json` 或 `binary` |
| `[network]` | `only_on_change` | `true` | 仅在状态变化时发送 |
| `[gamepad]` | `deadzone` | `0.05` | 摇杆死区（0–1） |
| `[gamepad]` | `poll_hz` | `100` | 手柄轮询频率 |

## 按钮映射（Nintendo Switch Pro 手柄）

| 序号 | 名称 | 序号 | 名称 |
|-------|------|-------|------|
| 0 | B | 8 | MINUS |
| 1 | A | 9 | PLUS |
| 2 | Y | 10 | L_STICK |
| 3 | X | 11 | R_STICK |
| 4 | L | 12 | HOME |
| 5 | R | 13 | CAPTURE |
| 6 | ZL | — | — |
| 7 | ZR | — | — |

轴：`LX`、`LY`、`RX`、`RY`（−1.0 ~ +1.0）
方向键（hat）：`[x, y]`，其中 x ∈ {−1, 0, +1}，y ∈ {−1, 0, +1}

## 脚本一览

所有脚本均位于 `scripts/` 目录下，分别提供 `.bat`（Windows）和 `.sh`（macOS/Linux）两个版本。

| 脚本 | Windows | macOS/Linux | 说明 |
|--------|---------|-------------|------|
| **setup** | `scripts\setup.bat` | `bash scripts/setup.sh` | 安装 Python 依赖（`pip install -r requirements.txt`）。克隆仓库后或切换 Python 版本时运行一次即可。 |
| **run_controller** | `scripts\run_controller.bat` | `bash scripts/run_controller.sh` | **正常运行模式。** 连接真实 Nintendo 手柄，将输入流式发送至 STM32（真实开发板或 Renode 模拟）。从 `config.ini` 读取目标主机/端口，断线后自动重连。 |
| **run_mock** | `scripts\run_mock.bat [count] [interval]` | `bash scripts/run_mock.sh [count] [interval]` | 无需真实手柄即可发送随机手柄数据包（用于测试/验证）。默认：20 个数据包，间隔 0.5 秒。发送日志保存到 `logs/mock_sent_<ts>.jsonl`。 |
| **run_simulator** | `scripts\run_simulator.bat` | `bash scripts/run_simulator.sh` | 在 7777 端口启动独立调试模拟器。在没有 Renode 或真实硬件的情况下，用它代替 bridge.py 来测试 controller.py。**请勿与 bridge.py 同时运行。** |
| **compare** | `scripts\compare.bat` | `bash scripts/compare.sh` | 将最新的 `logs/mock_sent_*.jsonl` 与 `../cthrobt_stm/received_signals.txt` 进行比对，并在 `logs/test_report_<ts>.md` 中生成 Markdown 测试报告。请在 mock 运行结束、bridge.py 报告 "Log is ready" 之后再运行。 |

### 典型工作流

**正常运行（真实手柄 → STM32 / Renode）：**
```
[终端 1 — cthrobt_stm]              [终端 2 — cthrobt]
scripts\run_simulation.bat    →      （等待 "Waiting for controller.py"）
                                     scripts\run_controller.bat
```

**通信测试（无需手柄）：**
```
[终端 1 — cthrobt_stm]              [终端 2 — cthrobt]
scripts\run_simulation.bat    →      （等待 "Waiting for controller.py"）
                                     scripts\run_mock.bat
（等待 "Log is ready"）        →      scripts\compare.bat
                                     打开 logs\test_report_*.md
```

**无 STM32/Renode 时调试：**
```
[终端 1 — cthrobt]                  [终端 2 — cthrobt]
scripts\run_simulator.bat     →      scripts\run_controller.bat
                                     （或 scripts\run_mock.bat）
```

## 日志

| 文件 | 生成者 | 内容 |
|------|-----------|---------|
| `logs/ctrl_<ts>.log` | `controller.py` | 完整会话日志 |
| `logs/mock_sent_<ts>.jsonl` | `controller.py --mock` | 每行一个 JSON 状态 |
| `logs/test_report_<ts>.md` | `compare.py` | 通过/失败比对报告 |
