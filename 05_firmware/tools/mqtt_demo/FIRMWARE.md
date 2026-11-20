# 固件侧改动与验证（2026-11-20，第二轮：字体 / 面板 / 摇杆）

## 0. 这一轮改了什么（回应三条反馈）

| 反馈 | 改动 |
|---|---|
| 字体糊到一块 | 换掉 3x5 放大 2 倍的做法，改用真正的 5x7 点阵：scale 1 = 7 px 高，scale 2 = 14 px 高，每一级都留 1 px 字距。字模由 tools/gen_font.py 从可读的 ASCII 点阵生成 main/probe_font.h，不再手写十六进制 |
| 另一块屏不需要实时波形 | TFT2 从「滚动波形 + 数字」的调试画面改成仪器读数面板：距离、上一拍峰值、敲击计数、三个链路状态灯 |
| 摇杆上下反了 | 垂直轴方向取反 |

另外做了离线像素预览工具 tools/preview_screens.py，把 C 的排版数学照抄一遍渲染成 PNG，
排版挤了、字被切了在串口日志里是看不出来的。生成图在 docs/screens/。

## 1. 菜单结构（TFT1，128x160）

    y   0..13   标题栏：页面面包屑 + 「当前/总数」
    y  17..121  六个菜单项，5x7 字体 scale 2（10x14 字形，12 px 步进）
    y 123..137  选中项当前的值，或按下去会发生什么
    y 140..159  按键图例

顶层 6 项，WiFi 与 MQTT 都收进子菜单：

| 顶层 | 子菜单项 |
|---|---|
| WIFI LINK | LINK · SCAN AP · JOIN AP · PASSCODE · AUTO JOIN · BACK |
| MQTT LINK | LINK · BROKER · PUBLISH · TAP STREAM · QOS LEVEL · BACK |
| SENSORS | ACCEL · RANGER · ZERO BASE · TAP COUNT · BACK |
| TAP DATA | TAP LEVEL（0.10/0.25/0.50/1.00 g）· SEND RATE（1/2/5/10 s）· SEND NOW · CLEAR CNT · BACK |
| SYSTEM | STATUS · DEVICE ID · RESTART MQ · DROP WIFI · REBOOT · BACK |
| STATUS | 四行数据通路：WIFI ON / BROKER UP / UPLINK ON / TAP SEND，逐行着色 |

导航：UP/DOWN 移动（循环），CLICK 进入/执行，LEFT 返回上一级；
编辑页 UP/DOWN 改字符、LEFT/RIGHT 移光标、CLICK 保存并立即重连。

字号约束（改文案时必须遵守）：scale 2 一行最多 10 个字形（120 px），
scale 1 一行最多 21 个字形。超了会被裁掉，预览脚本能看出来。

## 1b. TFT2 读数面板

    距离      207 MM      （VL53L1X，3 倍字号）
    ─────────────────────
    上一拍     0.42 G      （3 倍字号，没敲过显示 NONE YET）
    敲击计数   TAPS 17
    ■ WIFI   ■ MQTT   ■ TAP STREAM

这里故意不显示 BONDED/DEBOND：脱粘判定是频谱特征的阈值，阈值和整张特征表都在网页端，
在小屏上再算一个口径不同的判定只会有第二个可以互相矛盾的结论。
## 2. 敲击波形上传

- 加速度计 ±4 g、ODR 6.66 kHz；tap_feed() 每次采样减掉慢速重力基线后进 2048 帧环形缓冲。
- 幅值越过 TAP LEVEL（默认 0.25 g）即触发，取触发前 48 帧 + 后 464 帧 = 512 帧，
  交给显示任务在 probe_mqtt_pump() 里 base64 编码，以一条约 4.2 kB 的报文发到
  probe/probe-01/waveform。
- 编码与发送在 core 1 的显示任务上做，core 0 的采集任务永不阻塞在网络写上。

### 已知硬件限制（实测，不是猜测）

LSM6DS3 的 FIFO 在这块模块上不工作：FIFO_CTRL5 回读确实是 0x3E，但 150 ms 后
FIFO_STATUS 的 DIFF_FIFO 一直是 0。固件因此自动回退到直接轮询 OUTX_L_XL，
并用 esp_timer 实测采样率写进报文的 fs 字段（实测 2.4-2.7 kHz）。后端不得假设固定采样率。

## 2b. 测量点编号（pt）：差分分级的前提

网页端的判定依据是报告 §7.7.1 的**双面差分测量**：先把一块判断为粘接良好的区域测成
基准点，其余测点与它比相对比值 rho，所以每一拍都必须带“我在哪个测点”这一信息，
否则这一拍无法参与分级。

固件侧（probe_menu.c）：

- 菜单 **TAP DATA -> POINT ID**，摇杆左右切换 `P0` 到 `P5`（`POINT_N = 6`），
  当前值显示为 `P2 OF 5`；改完立即生效，无需重启。
- 也接受下行命令 `{"cmd":"point","v":2}`（`v` 取 0..5），用于网页端或脚本远程切点。
- `s_point_idx` 只存在 RAM 里，**重启后回到 P0**；同一次测量里换点必须重新在菜单里选，
  换场次、换建筑则整个基准都要重测。
- 报文里写的是 `"pt":"P%d"` 字符串：`probe/<dev>/waveform` 与
  `probe/<dev>/measurement` 两条主题都带（前者在 JSON 头部，后者紧跟 dev 之后）。

后端约定（见 PROTOCOL.md §7）：

- 缺 `pt` 字段的报文归到 `P?` 桶，不参与基准点选择，也不允许冒充某个测点；
- 每个测点至少 3 次有效敲击才评级，不足给 `NODATA`；
- 基准点没建立时所有测点都是 `NODATA / NO_REFERENCE`，不会退回绝对阈值冒充分级。

注意：固件不在设备上做差分分级，也不做 G0/G1/G2 的最终判定；设备只负责把每一拍
（带 pt）发上来，分级与置信度全部在后端完成，这样阈值改了不用重新烧板。

## 3. 实测证据

    I (549) BRINGUP: FIFO regs 06..0A = 00 00 00 00 3E
    I (699) BRINGUP: FIFO status after 150 ms = 00 60 (diff=0)
    W (6931) BRINGUP: FIFO never filled -> register polling fallback
    I (12062) BRINGUP: capture: fifo=0 frames=13373 fs=2634 Hz
    I (7451) BRINGUP: tap 1 trigger=8934 LSB
    I (6429) MENU: mqtt connected
    I (6435) MENU: subscribed probe/probe-01/cmd mid=8457

MQTT 侧（14 s 窗口，阈值临时降到 0.02 g 制造触发）：

    total: 73  {waveform: 56, measurement: 9, status: 2, cmd: 2, event: 2}
    header: dev=probe-01 seq=58 tap=57 fs=2567 n=512 scale=8192 pre=48 trig=134
    decoded frames: 512, bytes: 3072

后端 /api/latest（真实板子，非模拟器）：

    source: 06_analyze_tap.extract_features_from_waveform
    fs: 2635.0   n: 512   band: [30.0, 1185.75]   crossover: 395.25
    features: f_peak 97.78 Hz, f_centroid 553.2 Hz, band_ratio 0.643,
              crest 3.92, kurtosis 0.261, peak 0.0136 g, rms 0.00346 g
    verdict: BONDED

这一拍是桌面噪声，peak 只有 0.014 g，判定无物理意义；它证明的是链路与算法跑通，
不是脱粘检测本身。真实判定要用手敲传感器所在的那块板。

## 4. 分区表

app 分区从 1 MB 改成 1.5 MB（partitions_large.csv，factory @0x10000 长度 0x180000）。
起始偏移未变，不需要 erase_flash，NVS 保留。改前占用 1 MB 分区的 98.6%，改后 65.9%。

## 5. 怎么用

1. 菜单：摇杆上下选，按下确认，向左返回。
2. 要真实读数：用手敲加速度计所在的那块板，或在 TAP DATA -> TAP LEVEL 把门限降到 0.10 g。
3. 网页：http://localhost:8081/dashboard.html （同网段其他设备用 http://192.168.3.12:8081/dashboard.html）。
4. 串口：pio device monitor，115200，COM4。

## 6. 第三轮：摇杆抗敲击（2026-11-20 夜）

反馈：敲击时摇杆被误触发。根因不是死区大小，是**共壳机械冲击**——摇杆和加速度计在同一块板上，
敲一下外壳，摇杆的 ADC 输出会尖峰几个毫秒，单次采样就足够被判成满偏转。

三层处理，从便宜到贵：

| 层 | 做法 | 代价 |
|---|---|---|
| 1 | 每轴 5 点中值滤波 | 真实偏转最多延迟 2 个采样周期（40 ms） |
| 2 | 方向必须连续 3 个采样一致才「上膛」 | 一次性尖峰永远成不了移动 |
| 3 | 敲击后 400 ms 内丢弃摇杆输入 | 覆盖机械余振，不只是冲击那一下 |

死区保持 ±548 LSB（27% 范围）不变——问题不在死区，加了滤波反而更不该动它。
开关量同样受敲击静默保护。

被静默丢弃的摇杆动作数量记在心跳里：

    I (…) BRINGUP: wf alive, tof_ready=1 mqtt=1 pub=21 taps=1 joymute=0 heap=108084

`joymute` 只增不减，敲一次板子看一眼就知道静默有没有生效；`heap` 用来盯内存泄漏。
