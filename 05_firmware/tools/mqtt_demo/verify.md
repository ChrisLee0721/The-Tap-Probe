# 实时分析后端验证记录（verify.md，第二版）

本文件记录 `05_firmware/tools/mqtt_demo/` 下 Web 分析后端的真实运行证据。第二版对应
「相对/差分分级」这一层：固定信号带、测量点 `pt`、基准点、rho 两级阈值、第二条件一致性检查、
bootstrap 置信度、排序、`/api/points` 与网页主面板。固件侧（`05_firmware/main/`）不在本文件范围内。

- 验证日期：2026-11-20
- 机器：Windows 11 / Python 3.13.14 / 局域网 192.168.3.12
- 相关文件：`analyzer.py`（2155 行）、`dashboard.html`（991 行）、`PROTOCOL.md`（450 行）、
  `FIRMWARE.md`（146 行）；`simulator.py`、`start_demo.bat` 本轮未改

---

## 0. 本版改了什么

| 项 | 第二版的行为 |
|---|---|
| 信号带 | **固定** `[30, 1000] Hz`、交叉点 300 Hz，每条报文按 `band_hi <= 0.45*fs` 做 Nyquist 保护（被夹紧时 `band_clamped=true`）；不再按 `0.45*fs` 每拍重算 |
| 测点 | 报文 `pt` 字段（P0..P5）分组；缺字段归 `P?`；每点至少 3 次有效敲击才评级 |
| 基准点 | `POST /api/reference`，手动 `{"point":"P3"}`、自动 `{"point":"auto"}`（选基准 band_ratio 最高的 ≥3 拍点）、清除 `{"point":"clear"}`；无基准时全部 `NODATA/NO_REFERENCE` |
| 分级 | `grade_mode`：默认 **rank**（名次分位数 q<=1/3→G2、<=2/3→G1、其余 G0；n==1 用 CI 对基准）；`threshold` 保留旧 T1/T2 规则（占位值） |
| 第二条件 | 方向无关的一致性检查：`d_f=f_peak/f_ref`，`fpeak_mode` 默认 `either`，`fpeak_tol` 默认 0.15；不一致则 grade 最高 G1、confidence ×0.5 |
| 置信度 | 2000 次固定种子 bootstrap：`grade_confidence`、`p_debond`、`rho` 的 5–95% 区间 |
| 质量门 | `contact_ok` 优先固件布尔值，其次固件 `pkg`（0.05–8.0 g），最后才用后端启发式；点级返回 `contact_source` |
| 仿真隔离 | 分组键 (dev, pt)；`sp:true` 的点 `simulated:true`，`rank:null`，不进排序与结论；基准不能取仿真点；页面红条 + 红行 + 「仿真」徽章 |
| 会话重置 | `POST /api/reset` 清空 taps/points/reference/stats/counters，保留仪器配置；页面「清空本次测量」按钮（二次确认） |
| 基准行 | rho 固定 1.0（定义值），另报 `ref_drift` / `ref_drift_pct`；G0、置信度「—」；参考点不参与评级 |
| 可比性 | `comparable` = 真实非基准且 n_valid≥3；`n_comparable==0` 时 `most_likely_debonded=null`、verdict 明确提示去测第二个点；非可比行页面显示「待对比」 |
| 切换测点 | `POST /api/point`（`point`/`delta`）、`GET /api/point`；`current_point*` 字段；网页 P0..P5 按钮 + 当前测点高亮；设备 ack 带 pt |
| 页面 | 置顶「相对分级（双面差分测量）」主面板；单次判定改标题「单次敲击（绝对判定，仅参考）」；注释块去掉左侧竖线；模值面板无数据时有坐标框与提示 |

---

## 1. 环境

```bash
$ python --version
$ python -c "import numpy,scipy,pandas,paho.mqtt,amqtt,websockets; ..."
```

```text
Python 3.13.14
numpy 2.4.3
scipy 1.18.0
pandas 3.0.5
paho-mqtt 2.2.0
websockets 15.0.1
```

---

## 2. 启动整套栈

旧的一整套服务（broker 1883/8080、analyzer 8082、http 8081）先停掉，再按 `start_demo.bat` 的
同样三条命令重起：

```bash
$ python broker.py                                # tcp/1883 + ws/8080
$ python analyzer.py                              # http/8082 + ws/8082/api/stream
$ python -m http.server 8081 --bind 0.0.0.0       # 页面
```

真实启动输出：

```text
broker listening: tcp/1883 and ws/8080
[analyzer] template: F:\Internet_of_thinks\06_analyze_tap.py
[analyzer] template sha256: 1bbacd73670b29d23c24c9e538fa0cadcb5cf057873b6d5d19ec64dcf13e2620
[analyzer] band parameterisation: source-level: the three hard-coded band literals in the template function are bound to arguments band_lo_hz / band_hi_hz / crossover_hz; the function body is otherwise executed verbatim from the template source and its helpers are the template's own
[analyzer] template equivalence at default band: True (max|diff|=0 over 9 features)
[analyzer] MQTT connected to 127.0.0.1:1883
[analyzer] HTTP API on http://0.0.0.0:8082 (ws://<host>:8082/api/stream)
[analyzer] subscribed: probe/+/waveform probe/+/measurement probe/+/status probe/+/event
[analyzer] analysis band: fixed [30, 1000] Hz, crossover 300 Hz (Nyquist guard: band_hi <= 0.45*fs)
```

---

## 3. 静态自检：特征仍来自 06_analyze_tap.py，波段只是实参

```bash
$ python analyzer.py --check-band
```

```text
[analyzer] template equivalence at default band: True (max|diff|=0 over 9 features)
{
  "equivalence": {"max_abs_diff": 0.0, "n_features_compared": 9, "identical": true},
  "meta": {
    "template": "06_analyze_tap.py",
    "template_sha256": "1bbacd73670b29d23c24c9e538fa0cadcb5cf057873b6d5d19ec64dcf13e2620",
    "function": "extract_features_from_waveform",
    "source": "06_analyze_tap.extract_features_from_waveform",
    "band_parameterisation": "source-level: the three hard-coded band literals ... bound to arguments band_lo_hz / band_hi_hz / crossover_hz ...",
    "band_defaults": {"band_lo_hz": 300.0, "band_hi_hz": 15000.0, "crossover_hz": 1000.0}
  }
}
```

9 个特征在模板默认波段下逐位相同（max|diff|=0），说明实时链路用的就是报告那套特征算法，
换波段只是把三个字面量换成实参。

---

## 4. HTTP 端点总览

```bash
$ for ep in /api/health /api/latest /api/history?limit=3 /api/stats /api/config /api/points /api/point; do
    curl -s -o /dev/null -w "$ep -> %{http_code}\n" "http://127.0.0.1:8082$ep"; done
```

```text
/api/health -> 200
/api/latest -> 200
/api/history?limit=3 -> 200
/api/stats -> 200
/api/config -> 200
/api/points -> 200
/api/point -> 200
```

```bash
$ curl -s http://127.0.0.1:8082/api/health
```

```json
{
 "ok": true,
 "service": "tap-probe analyzer",
 "mqtt": {"connected": true, "broker": "127.0.0.1", "port": 1883,
          "subscriptions": ["probe/+/waveform", "probe/+/measurement",
                            "probe/+/status", "probe/+/event"]},
 "counts": {"status": 4, "measurement": 18, "waveform": 25, "tap": 25, "bonded": 25},
 "n_taps": 25,
 "config": {"th_band_ratio": 0.45, "band_lo_hz": 30.0, "band_hi_hz": 1000.0,
            "crossover_hz": 300.0, "window": 200, "grade_mode": "rank",
            "grade_t1": 0.8, "grade_t2": 0.5,
            "fpeak_mode": "either", "fpeak_tol": 0.15},
 "band": {"band_lo_hz": 30.0, "band_hi_hz": 1000.0, "crossover_hz": 300.0,
          "effective_band_hi_hz": 1000.0, "nyquist_guard": 0.45,
          "note": "fixed reduced band; not comparable with the 300..15000 Hz audio-band numbers in the report"}
}
```

```bash
$ curl -s http://127.0.0.1:8082/api/config
```

```json
{"ok": true,
 "data": {"th_band_ratio": 0.45, "band_lo_hz": 30.0, "band_hi_hz": 1000.0,
          "crossover_hz": 300.0, "window": 200, "grade_mode": "rank",
          "grade_t1": 0.8, "grade_t2": 0.5,
          "fpeak_mode": "either", "fpeak_tol": 0.15},
 "limits": {"th_band_ratio": [0.0, 2.0], "band_lo_hz": [1.0, 2000.0],
            "band_hi_hz": [50.0, 5000.0], "crossover_hz": [10.0, 4000.0],
            "window": [5, 2000], "grade_mode": ["rank", "threshold"],
             "grade_t1": [0.3, 1.2],
            "grade_t2": [0.05, "T1-0.05"],
            "fpeak_mode": ["either", "up", "down"], "fpeak_tol": [0.02, 0.6]}}
```

```bash
$ curl -s 'http://127.0.0.1:8082/api/history?limit=3'
```

```text
columns: ['t_ms','dev','pt','tap','seq','fs','band_lo_hz','band_hi_hz','crossover_hz',
          'f_peak_hz','f_centroid_hz','band_ratio_lh','decay_tau_ms','peak_au','rms_au',
          'crest_factor','kurtosis','impulse_norm','contact_ok','band_clamped','verdict']
P4 probe-01 23 ratio=7.308 contact_ok True clamped False BONDED
P4 probe-01 24 ratio=7.276 contact_ok True clamped False BONDED
P4 probe-01 25 ratio=9.917 contact_ok True clamped False BONDED
```

（注意 `verdict` 是**单次敲击的绝对判定**，仅参考；分级看 `/api/points`。）

---

## 5. 测试数据：5 个测点，rho 目标 1.0 / 0.9 / 0.7 / 0.45 / 0.3

没有真实探头时，用一段一次性合成驱动按 PROTOCOL 第 1 节格式发报文（脚本见附录 A，不随交付）。
做法：fs=2567、n=512、scale=8192；每个点 5 拍，用「固定频率阻尼音 + 300 Hz 以上高通噪声」合成，
先离线用 06 的**同一个重参数化函数**算出 band_ratio，再按噪信比把 5 拍的中位数校准到目标 rho；
每拍带 `pt`，正常拍带 `pkg=0.45`（等价于固件 PEAK 字段）。

### 5.1 还没有基准点时

```bash
$ curl -s http://127.0.0.1:8082/api/points
```

```text
grades: [('P0','NODATA','NO_REFERENCE'), ('P1','NODATA','NO_REFERENCE'),
         ('P2','NODATA','NO_REFERENCE'), ('P3','NODATA','NO_REFERENCE'),
         ('P4','NODATA','NO_REFERENCE')]
verdict: 尚未建立基准点：差分测量必须先测一个已知粘接良好的区域，再开始逐点比较。
```

没有退回绝对阈值冒充分级，符合 PROTOCOL §7.2。

### 5.2 建立基准点（自动）

```bash
$ curl -s -X POST -H 'Content-Type: application/json' -d '{"point":"auto"}' \
    http://127.0.0.1:8082/api/reference
```

```json
{"ok": true,
 "reference": {"point": "P0", "r_ref": 24.25172388248314, "f_ref": 280.765625,
               "set_ms": 1795190091447, "source": "auto", "n_taps": 5},
 "data": {"reference": {...}, "points": [...], "grade_rule": {...}, ...}}
```

### 5.3 五个测点的结果

```text
rule: {'t1': 0.8, 't2': 0.5, 'fpeak_mode': 'either', 'fpeak_tol': 0.15}
verdict: P4 最可能空鼓：rho=0.30（G2，分级稳定度 100%，空鼓概率 100%），相对基准 P0 下降 70%
most_likely_debonded: P4

pt  rank  grade  rho_grade  rho    rho_ci            d_f    incons  grade_conf  p_debond  conf    contact_source
P0  0     G0     G0         1.000  [0.904, 1.118]    1.000  False   1.000       0.000     100.0%  firmware
P4  1     G2     G2         0.301  [0.292, 0.409]    0.750  False   1.000       1.000     100.0%  firmware
P3  2     G2     G2         0.452  [0.434, 0.603]    0.821  False   0.949       1.000     94.8%   firmware
P2  3     G1     G1         0.703  [0.666, 0.892]    0.893  True    0.949       0.949     47.4%   firmware
P1  4     G0     G0         0.904  [0.841, 1.082]    0.929  False   1.000       0.000     100.0%  firmware
```

完整 `/api/points` 的顶层结构（P2 为例，原始 JSON）：

```json
{
 "ok": true,
 "reference": {"point": "P0", "r_ref": 24.25172388248314, "f_ref": 280.765625,
               "set_ms": 1795190091447, "source": "auto", "n_taps": 5},
 "grade_rule": {"t1": 0.8, "t2": 0.5, "fpeak_mode": "either", "fpeak_tol": 0.15},
 "most_likely_debonded": "P4",
 "verdict": "P4 最可能空鼓：rho=0.30（G2，分级稳定度 100%，空鼓概率 100%），相对基准 P0 下降 70%",
 "points": [
   {"point": "P0", "n_taps": 5, "n_valid": 5, "median_band_ratio": 24.2517,
    "median_f_peak_hz": 280.77, "median_rms_au": 0.0707,
    "contact_ok_share": 1.0, "contact_source": "firmware", "band_clamped_share": 0.0,
    "rank": 0, "grade": "G0", "rho_grade": "G0", "confidence": 1.0,
    "confidence_pct": 100.0, "grade_confidence": 1.0, "p_debond": 0.0,
    "rho": 1.0, "rho_ci": [0.9038, 1.1177], "d_f": 1.0,
    "inconsistent": false, "poor_contact": false, "is_reference": true, "reason": null},
   {"point": "P2", "n_taps": 5, "n_valid": 5, "median_band_ratio": 17.0549,
    "median_f_peak_hz": 250.684, "median_rms_au": 0.0710,
    "contact_ok_share": 1.0, "contact_source": "firmware", "band_clamped_share": 0.0,
    "rank": 3, "grade": "G1", "rho_grade": "G1", "confidence": 0.474,
    "confidence_pct": 47.4, "grade_confidence": 0.9485, "p_debond": 0.9485,
    "rho": 0.7032, "rho_ci": [0.6659, 0.8925], "d_f": 0.8929,
    "inconsistent": true, "poor_contact": false, "is_reference": false, "reason": null}
 ],
 "ts": 1795190091500,
 "notes": ["阈值 T1=0.80／T2=0.50 是待标定的占位值……",
           "band_ratio_lh 与 f_peak_hz 在固定信号带 [30, 1000] Hz、交叉点 300 Hz 上计算……",
           "分级是相对量：换建筑、换探头或换场次都必须重新建立基准点。",
           "f_peak 的方向还没有标定：报告音频带里脱粘时峰值升高（328→468 Hz），这条加速度计链……默认 fpeak_mode=\"either\"……"]
}
```

每个 `point` 还带 `dev` / `simulated` / `comparable` 字段；顶层还带 `n_simulated_points`、
`n_real_points`、`n_comparable`、`has_simulated`、`current_point`、`current_point_dev`、
`current_point_ms`、`current_point_source`（仿真隔离见 7b；单点场景与切换测点见 7c/7d）。

### 5.4 基准点的其它入口

```text
invalid reference P99 -> (400, {'ok': False, 'error': 'point P99 has no taps in the current window'})
clear reference     -> HTTP 200 | reference: None
                        verdict: 尚未建立基准点：差分测量必须先测一个已知粘接良好的区域，再开始逐点比较。
restore auto        -> P0（r_ref=24.2517）
```

---

## 6. 第二条件：方向无关的一致性检查（`fpeak_mode` / `fpeak_tol`）

规则（PROTOCOL §7.4）：只对 rho 判成 G1/G2 的点生效。

    either: abs(d_f - 1) >= fpeak_tol      -> 一致
    up    : d_f >= 1 + fpeak_tol           -> 一致
    down  : d_f <= 1 - fpeak_tol           -> 一致

一致通过则维持 rho 分级；否则 grade 最高 G1、`inconsistent: true`、confidence ×0.5。
默认 `either / 0.15` 是刻意的保守选择：报告里「脱粘时 f_peak 升高」是麦克风 300–15000 Hz 带内的结论，
不能直接搬到加速度计 30–1000 Hz 链上（当前链路实测 f_peak 210–280 Hz，方向未标定）。

### 6.1 either（默认）

见 5.3：P4（d_f=0.750，|0.25|≥0.15）保持 G2 且不一致标记为 false；
P2（d_f=0.893，|0.107|<0.15）被标不一致、G1 且 confidence 从 94.8% 降到 47.4%。
P1 的 d_f=0.929 也不足 0.15，但它 rho 判成 G0，规则不作用于 G0。

### 6.2 切到 up / down 的实测

```bash
$ curl -s -X POST -H 'Content-Type: application/json' -d '{"fpeak_mode":"up"}'   http://127.0.0.1:8084/api/config
$ curl -s -X POST -H 'Content-Type: application/json' -d '{"fpeak_mode":"down"}' http://127.0.0.1:8084/api/config
$ curl -s -X POST -H 'Content-Type: application/json' -d '{"fpeak_mode":"either","fpeak_tol":0.25}' http://127.0.0.1:8084/api/config
```

```text
== fpeak_mode = up ==
   P4 grade=G1 incons=True  conf=50.0% d_f=0.750
   P3 grade=G1 incons=True  conf=47.4% d_f=0.821
   P2 grade=G1 incons=True  conf=47.4% d_f=0.893
== fpeak_mode = down ==
   P4 grade=G2 incons=False conf=100.0% d_f=0.750
   P3 grade=G2 incons=False conf=94.8% d_f=0.821
   P2 grade=G1 incons=True  conf=47.4% d_f=0.893
== either + tol 0.25 ==
   P4 grade=G2 incons=False conf=100.0% d_f=0.750
   P3 grade=G1 incons=True  conf=47.4% d_f=0.821
   P2 grade=G1 incons=True  conf=47.4% d_f=0.893
```

### 6.3 非法值被拒

```text
POST {"fpeak_mode":"sideways"} -> (400, {'ok': False, 'error': 'fpeak_mode must be one of either, up, down'})
POST {"fpeak_tol":0.9}         -> (400, {'ok': False, 'error': 'fpeak_tol must be within [0.02, 0.60]'})
POST {"fpeak_tol":0.01}        -> (400, {'ok': False, 'error': 'fpeak_tol must be within [0.02, 0.60]'})
```

---

## 7. contact_ok 的三个来源与点级 `contact_source`

优先级（PROTOCOL §7.5）：报文布尔 `contact_ok` → 固件 `pkg`（0.05–8.0 g）→ 后端启发式
（`peak_au>=0.05 g` 且 `crest_factor>=3`）。点级 `contact_source` 取「只要有一拍是猜的就算 heuristic」。

额外测了三个点（同样 5 拍/点）：

```text
P5  rho=0.300 d_f=1.000  rho_grade=G2 -> grade=G1  inconsistent=True  poor=False  conf=50.0%  contact_source=firmware
P?  rho=0.302 d_f=0.821  rho_grade=G2 -> grade=G1  inconsistent=False poor=True   conf=60.0%  contact_source=firmware
P6  rho=0.522 d_f=0.857  rho_grade=G1 -> grade=G1  inconsistent=True  poor=False  conf=47.1%  contact_source=heuristic
```

- **P5**：带 `pkg=0.45`，但合成波形让峰值频率不动（d_f=1.000），被一致性检查压成 G1、半置信度。
- **P?**：没有 `pt` 字段（归 `P?` 桶），`pkg=0.02` 低于 0.05 g → 固件口径判为接触不合格，
  grade 降一级（G2→G1）、confidence ×0.6，点级 `contact_source=firmware`。
- **P6**：报文不带 `pkg`、也不带 `contact_ok`，走后端启发式，因此 `contact_source=heuristic`，
  提示读者这个质量门是猜的。

---

## 7b. 仿真数据隔离（`sp:true`）与会话重置

仿真报文必须一眼可辨，而且不能混进真实测点的分级。分组键是 `(dev, pt)`：
真实探头 `probe-01` 与模拟器 `sim-01` 各自成桶，模拟器每拍带 `sp:true`。
点级字段 `simulated` / `n_simulated`，顶层 `n_simulated_points` / `n_real_points` /
`has_simulated`。模拟测点 `rank:null`，不进入 `most_likely_debonded` 与 `verdict`；
基准点也不能取仿真点。

实测：先发 5 个真实测点并 auto 建基准，再灌入 3 个 `sim-01` 仿真测点。

```text
n_sim=3 n_real=5 has_sim=True
most_likely: P4
verdict: P4 最可能空鼓：rho=0.30（G2，分级稳定度 100%，空鼓概率 100%），相对基准 P0 下降 70%
notes[0]: 本面板含 3 个仿真测点（sp:true，P0/sim-01、P1/sim-01、P2/sim-01）：它们不参与排序与结论，不是测量结果；真实测量请接入探头或先清空本次测量。

P0 dev=probe-01 sim=False rank=0    grade=G0 rho=1.000
P4 dev=probe-01 sim=False rank=1    grade=G2 rho=0.301
P3 dev=probe-01 sim=False rank=2    grade=G2 rho=0.452
P2 dev=probe-01 sim=False rank=3    grade=G1 rho=0.703
P1 dev=probe-01 sim=False rank=4    grade=G0 rho=0.904
P0 dev=sim-01   sim=True  rank=None grade=G0 rho=0.951
P1 dev=sim-01   sim=True  rank=None grade=G1 rho=0.603
P2 dev=sim-01   sim=True  rank=None grade=G2 rho=0.201
```

仿真测点样例（原始 JSON 片段）：

```json
{"point": "P0", "dev": "sim-01", "simulated": true, "n_simulated": 5,
 "n_taps": 5, "n_valid": 5, "median_band_ratio": 23.0563,
 "median_f_peak_hz": 275.75, "rank": null, "grade": "G0",
 "rho": 0.9507, "rho_ci": [0.8564, 1.0006], "d_f": 0.9821,
 "inconsistent": false, "poor_contact": false, "confidence_pct": 100.0}
```

基准点拒绝纯仿真会话：

```text
POST /api/reference {"point":"auto"} (simulation-only)
 -> {"ok": false, "error": "only simulated taps (sp:true) are present; a reference must come from a real measurement"}
POST /api/reference {"point":"P0"} (simulation-only)
 -> {"ok": false, "error": "point P0 has only simulated taps (sp:true); a reference must come from a real measurement"}
```

### 7b.1 `POST /api/reset`

```bash
$ curl -s -X POST -H 'Content-Type: application/json' -d '{}' http://127.0.0.1:8084/api/reset
```

```text
HTTP 200 | ok: True
cleared: {'taps': 40, 'reference': 'P0', 'reference_dev': 'probe-01', 'errors': 0, 'counters': True}
data.points: [] | data.reference: None
data.verdict: 尚未建立基准点：差分测量必须先测一个已知粘接良好的区域，再开始逐点比较。

after reset:
  points: []
  history rows: 0
  stats n: 0
  config kept: {'th_band_ratio': 0.45, 'band_lo_hz': 30.0, 'band_hi_hz': 1000.0,
                'crossover_hz': 300.0, 'window': 200, 'grade_t1': 0.8,
                'grade_t2': 0.5, 'fpeak_mode': 'either', 'fpeak_tol': 0.15}
```

清空的是测量数据（taps/points/reference/errors/counters），仪器配置保留；网页上对应
红色「清空本次测量」按钮，点击有 confirm 二次确认，清空后主面板回到「尚未建立基准点」。

## 7c. 单点场景：基准行定义值、基准漂移、可比性

现场反馈「只有一个 P0、74 拍，页面却给 G0 88% 12% 和排名 0」。规则：

- 基准行 `rho` 固定 1.0（定义值），另报 `ref_drift` / `ref_drift_pct`；`grade="G0"`，
  `confidence=null`，`rank=0`，`is_reference=true`。
- `comparable` = 真实、非基准、`n_valid>=3` 的测点数；`/api/points` 顶层给 `n_comparable`，
  点级给 `comparable`。`n_comparable==0` 时 `most_likely_debonded=null`，verdict 明确说
  「只测到基准点 … 还没有第二个可比测点」。
- 非可比点 `grade` 仍保留在 JSON 里，但页面分级列显示「待对比」、置信度/空鼓概率显示「—」。

实测（先 8 拍 P0、rho≈1.0 建基准，再灌 12 拍让 median 漂到 0.84）：

```text
n_real=1 n_comparable=0 n_sim=0 most_likely=None
current_point=P0 dev=probe-01 source=tap
verdict: 只测到基准点 P0（20 拍），还没有第二个可比测点——请在菜单 TAP DATA→POINT ID 换到 P1 再测，或用页面上的 P0..P5 按钮切换。差分分级至少需要两个测点。
 P0 rank=0 comparable=False grade=G0 rho=1.000 ref_drift=0.889 conf=None p_deb=None
```

对应原始 JSON 片段：

```json
{
 "reference": {"point": "P0", "dev": "probe-01", "r_ref": 24.5866,
               "f_ref": 280.77, "source": "auto", "n_taps": 8},
 "n_real_points": 1, "n_comparable": 0, "most_likely_debonded": null,
 "verdict": "只测到基准点 P0（20 拍），还没有第二个可比测点——请在菜单 TAP DATA→POINT ID 换到 P1 再测，或用页面上的 P0..P5 按钮切换。差分分级至少需要两个测点。",
 "current_point": "P0", "current_point_dev": "probe-01", "current_point_source": "tap",
 "points": [{"point": "P0", "rank": 0, "grade": "G0", "rho": 1.0,
             "confidence": null, "p_debond": null, "is_reference": true,
             "comparable": false, "ref_drift": 0.8890, "ref_drift_pct": -11.095,
             "n_taps": 20, "median_band_ratio": 21.8586, "median_f_peak_hz": 270.74}]
}
```

加第二个测点 P2（4 拍，rho≈0.62）之后：

```text
n_real=2 n_comparable=1 n_sim=0 most_likely=P2
 P0 rank=0 comparable=False grade=G0 rho=1.000 ref_drift=0.889 conf=None p_deb=None
 P2 rank=1 comparable=True  grade=G1 rho=0.614 ref_drift=—     conf=50.0 p_deb=1.0
verdict: P2 最可能空鼓：rho=0.61（G1，分级稳定度 50%，空鼓概率 100%），相对基准 P0 下降 39%；峰值频率没有随 band_ratio 明显移动，两个条件未互相印证
```

页面：单点态 `F:/_webtmp/r4_single.png`（当前测点 P0 高亮、基准行「1.00（定义值）」+「基准漂移 -11.1%」、
G0、稳定度/空鼓概率「—」、表格上方蓝色提示条）；双点态 `F:/_webtmp/r4_two.png`
（P0 基准 + P2 可比，P2 行带误差棒与 G1 结果）。

## 7d. 网页切换测点：`POST /api/point` / `GET /api/point`

```bash
$ curl -s -X POST -H 'Content-Type: application/json' -d '{"point":"P2"}'    http://127.0.0.1:8084/api/point
$ curl -s http://127.0.0.1:8084/api/point
$ curl -s -X POST -H 'Content-Type: application/json' -d '{"delta":1}'       http://127.0.0.1:8084/api/point
$ curl -s -X POST -H 'Content-Type: application/json' -d '{"point":"P7"}'    http://127.0.0.1:8084/api/point
$ curl -s -X POST -H 'Content-Type: application/json' -d '{"delta":9}'       http://127.0.0.1:8084/api/point
$ curl -s -X POST -H 'Content-Type: application/json' -d '{}'                http://127.0.0.1:8084/api/point
```

```text
point P2 -> (200, {'ok': True, 'dev': 'probe-01', 'point': 'P2', 'cmd_mid': 4})
GET /api/point -> {'ok': True, 'current_point': 'P2', 'current_point_dev': 'probe-01',
                   'current_point_ms': 1795191717946, 'current_point_source': 'ack'}
delta 1 -> (200, {'ok': True, 'dev': 'probe-01', 'point': 'P3', 'cmd_mid': 5})
GET /api/point -> {'ok': True, 'current_point': 'P3', 'current_point_dev': 'probe-01',
                   'current_point_ms': 1795191718654, 'current_point_source': 'ack'}
invalid P7 -> (400, {'ok': False, 'error': 'point must be P0..P5 (or 0..5)'})
invalid delta 9 -> (400, {'ok': False, 'error': 'delta would leave P0..P5'})
bad body -> (400, {'ok': False, 'error': 'body needs {"point": "P3"} or {"delta": 1}'})
```

没有真实设备时（后端按「最近一次 sp 不为 true 的拍」找 dev）：

```text
point before any device: (409, {'ok': False, 'error': 'no real device seen yet'})
```

设备 ack（本次用临时固件桩模拟 Lead 将实现的 ack：`{"ev":"ack","cmd":"point","pt":"P4"}`）
经 WebSocket 推送：

```text
hello current_point: P3
WS point_ack: {'type': 'point_ack', 'current_point': 'P4',
               'current_point_dev': 'probe-01', 'current_point_ms': 1795191719410}
```

网页上 P0..P5 一排按钮，当前测点高亮；点一下发 `POST /api/point`，收到 `point_ack` 后自动刷新
「当前测点」。操作流程因此是：点 P0 → 敲 3 次 → 设为基准 → 点 P1 → 敲 3 次 → … 全程不用碰摇杆。

## 7e. 相对排名分级（grade_mode=rank，默认）

用户反馈「不能所有点都在固定阈值内就全判 G0，相对阈值下两个里总有一个更像空鼓」。
因此默认改为 **rank 模式**：分级由本场可比测点的 rho 名次分位数决定，而不是拿 rho 去碰常数。

规则（PROTOCOL §7.3/§7.6）：

- 可比点按 rho 升序，名次 k=1..n；q=(k-1)/(n-1)；q<=1/3→G2、<=2/3→G1、其余 G0。
  n=5 得 G2,G2,G1,G0,G0；n=3 得 G2,G1,G0；n=2 得 G2,G0。
- 基准点永远 rank=0/G0，不参与排名。
- n==1 时退回「对基准」的 CI 判据：rho 的 95% CI 上界<1.0→G2、下界>1.0→G0、跨 1.0→G1（reason "CI straddles reference"）。
- 置信度改为**联合 bootstrap**（1000 次固定种子）：每轮对每个点重采样并重新排序定档；
  `grade_confidence`=同档比例、`rank_confidence`=名次完全一致比例、`p_debond`=落在最可疑三分之一（G2）的比例（`p_debond_meaning="relative_top_third"`）。
- 顶层给 `p_order_significant`（整场名次完全保持的比例）与 `spread`（rank1 / 其余中位），
  verdict 只在 `p_order_significant >= 0.9` 时才宣称「相对最可疑」。

### 7e.1 现场那组 rho（0.82/0.84/0.89/0.96/2.44）在 rank 模式下

（基准 P0 合成 8 拍；每个测点 8 拍；rho 由合成功率和基准比值校准到目标）

```text
mode=rank n_real=6 n_comparable=5 most_likely=P1
p_order_significant=0.319  spread=0.877  p_debond_meaning=relative_top_third
verdict: 本场各点差异未超出噪声（排序置信度 32%）：P1 的 rho 最低（0.81 vs 其余中位 0.92）但不可据此判缺陷，建议对该点复测或换基准后重比。
 P0 rank=0 grade=G0 rho=1.000   gconf=—    rconf=—    p_deb=—
 P1 rank=1 grade=G2 rho=0.808   gconf=0.829 rconf=0.506 p_deb=0.829
 P4 rank=2 grade=G2 rho=0.830   gconf=0.747 rconf=0.459 p_deb=0.747
 P5 rank=3 grade=G1 rho=0.889   gconf=0.496 rconf=0.496 p_deb=0.359
 P3 rank=4 grade=G0 rho=0.954   gconf=0.752 rconf=0.752 p_deb=0.065
 P2 rank=5 grade=G0 rho=2.358   gconf=1.000 rconf=1.000 p_deb=0.000
```

分级 P1=G2、P4=G2、P5=G1、P3=G0、P2=G0，与要求一致。注意这组 rho 彼此太近，8 拍下名次在
bootstrap 里翻来翻去（p_order 只有 0.32），所以 verdict 走「差异未超出噪声」分支——这正是
用户需要看到的诚实结论：排序永远有，但没分离就不能判缺陷。

JSON 片段（顶层指标与 P1）：

```json
{"grade_mode": "rank", "n_comparable": 5,
 "p_order_significant": 0.319, "spread": 0.877,
 "p_debond_meaning": "relative_top_third",
 "fpeak_resolution_limited": false,
 "most_likely_debonded": "P1",
 "points": [
   {"point": "P1", "rank": 1, "grade": "G2", "rho_grade": "G2", "rho": 0.808,
    "rho_ci": [0.631, 0.974], "grade_confidence": 0.829,
    "rank_confidence": 0.506, "p_debond": 0.829, "confidence_pct": 82.9},
   {"point": "P2", "rank": 5, "grade": "G0", "rho": 2.358, "p_debond": 0.0}
 ]}
```

### 7e.2 把 P4 改成 0.99 后应掉到 G0

```text
mode=rank n_comparable=5
 P1 rank=1 grade=G2 rho=0.808
 P5 rank=2 grade=G2 rho=0.889
 P3 rank=3 grade=G1 rho=0.954
 P4 rank=4 grade=G0 rho=0.973   <-- 从 G2 掉到 G0（名次从 2 变 4）
 P2 rank=5 grade=G0 rho=2.358
verdict: 本场各点差异未超出噪声（排序置信度 32%）：P1 的 rho 最低（0.81 vs 其余中位 0.96）但不可据此判缺陷…
```

### 7e.3 同样的数据切到 threshold 模式：全 G0（用户看到的那个问题）

```bash
$ curl -s -X POST -H 'Content-Type: application/json' -d '{"grade_mode":"threshold"}' http://127.0.0.1:8082/api/config
```

```text
mode=threshold n_comparable=5
 P0 G0 rho=1.000  P1 G0 0.808  P4 G0 0.830  P5 G0 0.889  P3 G0 0.954  P2 G0 2.358
verdict: 各测点与基准 P0 无明显差异：最接近空鼓的 P1 rho=0.81（G0，分级稳定度 56%，空鼓概率 43%），相对基准下降 19%
p_debond_meaning = prob_rho_below_t1（T1=0.80：全部 rho 都高于它 -> 全 G0）
```

这说明固定阈值模式把「相对量 rho」又碰了一个绝对阈值，现场这样的分布会退化成全 G0；
rank 模式才有区分度。页面切换见 `F:/_webtmp/r5_threshold.png`（T1/T2 可编辑、列名「空鼓概率」）
与 `F:/_webtmp/r5_rank.png`（T1/T2 灰掉、列名「相对可疑度」）。

### 7e.4 只有 1 个可比点（n==1）的退回规则

```text
D1: P2 rho=0.587 CI [0.54,0.68] -> G2
    verdict: P2 相对基准显著偏低：rho=0.59（95% CI [0.54, 0.68]），判为 G2（相对档位）；本场只有一个可比测点，没有排序。
    rank_confidence=null；p_debond_meaning=prob_rho_below_reference
D2: P2 rho=1.000 CI [0.91,1.11] -> G1，reason="CI straddles reference"
    verdict: P2 与基准无显著差异（95% CI [0.91, 1.11] 跨过 1.0）：证据不足（CI straddles reference），建议复测或换基准后重比。
```

### 7e.5 分离明显时 verdict 的另一分支

```text
p_order_significant=1.000  spread=0.333
verdict: P1 相对最可疑：rho=0.49，与本场其余点分离（排序置信度 100%），较基准下降 51%；分级 G2 是相对档位，不是绝对严重度。
```

### 7e.6 基准峰贴在带底时自动告警（现场 f_ref=30.4 Hz）

```text
reference f_ref = 30.08 Hz（band_lo=30 Hz）
fpeak_resolution_limited = true
notes[0]: 基准峰 f_ref=30.1 Hz 贴在信号带下沿（band_lo=30 Hz 的 1.2 倍以内）：第二条件（f_peak 一致性）本场无分辨力，判据实际上只剩 rho。
```

该场景下所有点 f_peak 都在 30–36 Hz，d_f 恒约 1；rank 模式本来就不使用第二条件，
但这条 note 告诉用户阈值模式的第二条件也没有分辨力，结论可信度要相应打折。

### 7e.7 配置与模式切换

```text
GET /api/config -> {"grade_mode":"rank", "grade_t1":0.8, "grade_t2":0.5, ...,
                    "limits": {..., "grade_mode":["rank","threshold"], ...}}
POST /api/config {"grade_mode":"threshold"} -> 200，data.grade_mode="threshold"
POST /api/config {"grade_mode":"bogus"}     -> (400, {"ok": false, "error": "grade_mode must be one of rank, threshold"})
```

## 7f. 会话持久化（跨重启保留测量记录）

### 7f.1 为什么必须做

一场测量是一次物理过程：操作者在墙面上敲二十分钟，敲出来的数字就是这次调查唯一的记录。此前这些数据只存在进程内存里，于是**任何一次服务重启——改代码、崩溃、PC 重启——都会把整场测量悄悄丢掉**，而页面重新打开时只是一片空白，看起来像"仪器没工作过"。这不是稳定性问题，是数据完整性问题。

### 7f.2 文件与格式

```text
05_firmware/tools/mqtt_demo/.session/
├── taps.jsonl        一行一拍，完整的 tap 记录（含 features、pt、fs、band 等）
└── reference.json    当前基准点（r_ref / f_ref / source / n_taps / set_ms）
```

- 追加写，每收到一拍立刻落盘，不做批量缓冲：掉电最多丢最后一拍。
- **只写真实拍**（`sp != true`）。仿真拍不落盘，所以模拟器跑过之后再重启，绝不会把仿真数据当成一次测量重放出来。
- 基准点单独存一个小 JSON，随 `POST /api/reference` / `POST /api/reference {"point":"clear"}` 实时更新。
- `POST /api/reset` 会把这两个文件一起删掉——开新场次必须真的从零开始，否则 rho 会跨场次比较。

### 7f.3 启动行为

进程启动时读取这两个文件，恢复 taps 队列、基准点、`last_real_tap` 与 `last_real_device`，然后照常订阅 MQTT。日志会明确写出恢复了几拍：

```text
[analyzer] session: restored 1 tap(s) from F:\Internet_of_thinks\05_firmware\tools\mqtt_demo\.session\taps.jsonl
[analyzer] session: reference restored (P0)
```

没有文件时静默跳过，等同全新会话；文件损坏时只记一条日志并继续启动（不能因为一个坏行就让仪器起不来）。

### 7f.4 实测

1. 设备复位产生一拍真实敲击 → `.session/taps.jsonl` 立即出现，3355 字节，首行 `{"type": "tap", "pt": "P0", "sp": false, …, "fs": 2623.0}`。
2. 杀掉 analyzer 并重启 → 日志 `session: restored 1 tap(s)`，`/api/points` 仍是 `P0 n_taps=1`。
3. `POST /api/reset` → `{"ok": true, "cleared": {"taps": 1, …}}`，`.session/` 下两个文件同时消失。

## 8. bootstrap 置信度是真实分布

- **P3**：rho=0.452，rho_ci=[0.434, 0.603] 跨过 T2=0.5，所以 `grade_confidence=0.949`（约 5% 的重采样
  落到 G2 之外），`p_debond=1.000`。两个数表达不同问题：分级稳不稳 vs 是否非 G0。
- **P2**：`grade_confidence=0.949`、`p_debond=0.949`；第二条件不一致后 `confidence=0.949×0.5=0.474`（47.4%）。
- **P4**：rho_ci=[0.292, 0.409] 完全在 G2 内，`grade_confidence=1.000`。
- 固定种子 20261120：同一批 tap 重算，数值逐位一致；这是可报告性的前提。

---

## 9. 排序与结论句

```text
rank 1  P4  rho=0.301（G2）
rank 2  P3  rho=0.452（G2）
rank 3  P2  rho=0.703（G1）
rank 4  P1  rho=0.904（G0）
rank 0  P0  基准点 is_reference=true
```

verdict（中文，由后端拼装）：

```text
P4 最可能空鼓：rho=0.30（G2，分级稳定度 100%，空鼓概率 100%），相对基准 P0 下降 70%
```

---

## 10. WebSocket：`/api/stream` 推 `points`

```bash
$ python ws_points.py     # websockets.sync.client 连 ws://127.0.0.1:8084/api/stream
```

```text
hello keys: ['config', 'latest', 'points', 'source', 'stats', 'type'] | points: 5
message: config
message: points
points rule: {'t1': 0.8, 't2': 0.5, 'fpeak_mode': 'either', 'fpeak_tol': 0.15}
points verdict: P4 最可能空鼓：rho=0.30（G2，分级稳定度 100%，空鼓概率 100%），相对基准 P0 下降 70%
```

连接即发 `hello`（含 points 与 current_point），之后每次敲击发 `tap` + `points`；改阈值、设/清基准也会推
`points`；点设备测点的 ack 到达时推 `{"type":"point_ack","current_point":"P4",...}`。

---

## 11. 网页端验证

```bash
$ curl -s -o /dev/null -w 'HTTP %{http_code} %{size_download} bytes\n' http://127.0.0.1:8081/dashboard.html
$ node --check <dashboard.html 内联脚本>.js
```

```text
dashboard HTTP 200 bytes 43005
script blocks: 2
node --check rc= 0
FOUND   相对分级（双面差分测量）
FOUND   id="points-body"
FOUND   id="ref-banner"
FOUND   自动选基准
FOUND   设为基准
FOUND   单次敲击（绝对判定，仅参考）
FOUND   信号带 30–1000 Hz
FOUND   id="grade-verdict"
FOUND   id="gt1"
FOUND   id="gt2"
bytes: 43005
```

用无头 Chrome 实际渲染（不是静态截图拼接）：

```bash
$ chrome --headless=new --disable-gpu --window-size=1500,1120 \
         --virtual-time-budget=9000 --screenshot=F:/_webtmp/dash_v2.png \
         http://127.0.0.1:8081/dashboard.html
```

- 有数据态：主面板显示 verdict、基准 P0 徽章与高亮行、rho 误差棒（含 T1 虚线）、G0/G1/G2 色块、
  分级稳定度/空鼓概率/敲击数、每行「设为基准」；P2 行带「证据不一致」标记。
- 无基准态（`POST /api/reference {"point":"clear"}` 后截图 `dash_v2_noref.png`）：黄色提示条
  「尚未建立基准点：差分测量必须先测一个已知粘接良好的区域（在测点行点「设为基准」，或点「自动选基准」）。」，
  分级列整列灰成「待基准」，rho/稳定度/概率全部显示 —。
- 面板底部注明：「本面板只回答『哪个点更像空鼓』这个相对问题；rho 的方向（越小越疑）沿用报告音频带的结论，
  在这条加速度计链上尚未标定——排序可用，方向待验证。」
- 单次判定卡片改为「单次敲击（绝对判定，仅参考）」并加一行解释；两处都标注
  「信号带 30–1000 Hz（加速度计量程内），与报告 300–15000 Hz 麦克风音频带不可直接比较」。
- 工具行显示当前 f_peak 一致性设置（`f_peak 一致性：either ±0.15`），该 chip 带 `title` 悬停说明：
  「两个条件互相印证：rho 判有异常时，看峰值频率有没有跟基准比明显移动（|f_peak/f_ref−1| ≥ 0.15）。
  either 表示只看是否移动、不预设往哪个方向——方向还没标定。」
- 主面板顶部大字「当前测点 P2」+ 设备名 + 来源（设备确认/最近一拍），旁边 P0..P5 一排按钮，
  当前测点高亮；点按钮即 `POST /api/point`，收到 `point_ack` 后自动刷新。截图
  `F:/_webtmp/r4_single.png`（P0 高亮）与 `F:/_webtmp/r4_two.png`（P2 高亮）。
- 基准行：rho 显示「1.00（定义值）」并在下方小字「基准漂移 −11.1%」，分级 G0、稳定度/空鼓概率「—」。
- 只有基准点一个测点时：verdict 换成「只测到基准点 P0（20 拍），还没有第二个可比测点……差分分级至少需要两个测点。」，
  表格上方同时出现蓝色提示条（同句）；不可比的真实测点分级列显示「待对比」、置信度/空鼓概率「—」。
- 仿真数据：面板顶部红色横幅「本面板含 N 个仿真测点（sp:true），不是测量结果；仿真测点不参与排序与结论。」，
  仿真行整行暗红、测点后带「仿真」徽章、rank 显示「—」；多设备时测点列同时显示 dev。
- 会话重置：工具行红色「清空本次测量」按钮，点击弹 confirm 二次确认，成功后计数归零、面板回到「尚未建立基准点」。
- 注释块去掉了左侧竖线（现在是小圆角提示框），不再有每行开头的 `|`。
- 「加速度模值（原始流 8080）」面板：无数据时也画坐标框并显示「等待 probe/measurement 原始流帧…」提示；
  收到 measurement 帧后画出实时模值曲线（用 CDP 在真实时间下截图，能看到曲线与 1.0014 g 读数）。
- 分级模式行：「分级方式：相对排名（默认）」+「切换为固定阈值」按钮 + 「相对排名模式不使用固定阈值（T1/T2 不生效）」；
  rank 模式下 T1/T2 输入框 disabled，列标题从「空鼓概率」改为「相对可疑度」，并显示「排序置信度 23% ／ 分离度 0.88×」。
- 排名列在名次下方显示「名次置信度 xx%」（rank_confidence）；分级色块带 title 提示
  「相对档位：G2 = 本场最可疑的三分之一，不是绝对判定」。
- 面板底部说明改为后端 notes 动态渲染（模式说明、rank 永远有名次的提醒、band 说明、相对量说明、
  f_peak 方向说明，以及 f_ref 贴带底时的告警）。
- 截图：rank 模式 `F:/_webtmp/r5_rank.png`、同数据 threshold 模式 `F:/_webtmp/r5_threshold.png`。

---

## 12. 复现命令

```bash
cd F:/Internet_of_thinks/05_firmware/tools/mqtt_demo

python broker.py
python analyzer.py
python -m http.server 8081 --bind 0.0.0.0
# 数据源：真实探头，或附录 A 的合成驱动（python drive_points.py main）

curl -s http://127.0.0.1:8082/api/points
curl -s -X POST -H 'Content-Type: application/json' -d '{"point":"auto"}' http://127.0.0.1:8082/api/points \
     || true   # 正确端点是 /api/reference
curl -s -X POST -H 'Content-Type: application/json' -d '{"point":"auto"}' http://127.0.0.1:8082/api/reference
curl -s http://127.0.0.1:8082/api/points
curl -s -X POST -H 'Content-Type: application/json' -d '{"fpeak_mode":"either","fpeak_tol":0.15}' http://127.0.0.1:8082/api/config
curl -s -X POST -H 'Content-Type: application/json' -d '{"grade_mode":"threshold"}' http://127.0.0.1:8082/api/config   # 对照：全 G0
curl -s -X POST -H 'Content-Type: application/json' -d '{"grade_mode":"rank"}'      http://127.0.0.1:8082/api/config
# 网页切换设备测点（全部不用碰摇杆）
curl -s -X POST -H 'Content-Type: application/json' -d '{"point":"P2"}' http://127.0.0.1:8082/api/point
curl -s http://127.0.0.1:8082/api/point
curl -s -X POST -H 'Content-Type: application/json' -d '{"delta":1}'  http://127.0.0.1:8082/api/point
# 新场次：清空 taps/points/reference/stats（配置保留）
curl -s -X POST -H 'Content-Type: application/json' -d '{}' http://127.0.0.1:8082/api/reset
# 打开 http://localhost:8081/dashboard.html
```

（上一段里故意留了错误端点的对照：`/api/points` 只有 GET，设基准是 `POST /api/reference`。）

---

## 13. 已知限制（必须连同结果一起读）

1. **阈值未标定**：T1=0.80 / T2=0.50 没有任何物理依据，是占位值；必须用真实粘接/脱粘样本的
   rho 分布重新确定（报告附录 C.4），页面上也写了这一点。
2. **f_peak 方向未标定**：默认 `either` 只检查「峰值是否移动」，不判断方向；报告音频带的
   「脱粘峰值升高」不能直接搬到本条链。等真实样本再钉 `up`/`down`。
3. **相对量**：rho 是相对基准的比值，换基准会整体平移；换建筑/探头/场次必须重建基准。
4. **band_ratio_lh 只是固定带内的比值**：它与报告 300–15000 Hz 的 0.78/0.19 不可直接比较；
   在 30–1000 Hz 带内它可到 7~24（合成音）甚至更高，所以分级必须用 rho 而不是绝对值。
5. **一个测点至少要 3 次有效敲击**；不足给 NODATA，不硬评。
6. **固件 `pkg` 字段**：本轮后端已按「有 `contact_ok` 用布尔、有 `pkg` 用 0.05–8.0 g 窗口、
   都没有才启发式」实现；固件侧是否已把 `pkg` 写进 waveform 报文由固件那半边负责，
   接线前真实探头的数据会走启发式（`contact_source="heuristic"`）。
7. **仿真数据必须带 `sp:true`**：后端只认这个字段；没有 `sp` 的合成报文仍会被当成真实测点。
   模拟器（固件/工具那半边）已改为 `dev="sim-01"` 且每拍加 `"sp": true`；分组键是 `(dev, pt)`，
   所以仿真点不会污染真实探头的测点桶。用户看到的旧截图里「全是编出来的分级」正是因为
   当时的模拟报文既没有 `sp` 也没有独立 dev —— 这是必须避免的形态。
8. **会话边界**：换墙、换探头、换基准后必须 `POST /api/reset`（或点页面「清空本次测量」）；
   否则新旧场次的 taps 会一起进 rho 统计，属于跨场次比较，结论无效。
9. **一个测点不构成排名**：只测到基准点时没有可比对象，`most_likely_debonded=null`，
   页面用提示条要求去测第二个点；这不是仪器故障，而是差分测量本身的下限。
10. **基准漂移**：`ref_drift` 是「基准点当前 median / 建立基准时的 median」；它只说明这次测量
    自身稳不稳（现场 -16% 属于偏大，值得检查接触/姿态），不是基准点的分级。
11. **current_point 的两个来源**：设备 point-ack 优先，其次最近一拍真实报文的 pt；两者都有时按时间戳取新的。
    菜单换点没有 ack，所以后端不缓存死值，而是跟着真实拍走。
12. **合成驱动不是交付物**：附录 A 只是本次验证的数据源，不参与部署；真实判定要用手敲传感器所在板的拍。
13. **相对排名永远会给出名次**：rank 模式下即使全部测点都合格也会分出 G2/G1/G0；
    名次只在 `p_order_significant` 高时才有意义，且衡量的是相对可疑程度，不是空鼓绝对概率。
    没分离时 verdict 会明说「差异未超出噪声」，不要读成「某点空鼓」。
14. **threshold 模式是旧逻辑的保留**：T1/T2 仍是占位值；现场 rho 全部高于 T1 时它会退化成全 G0，
    所以默认不用它，等真实粘接/脱粘样本标定完再考虑。
15. **第二条件的盲区**：基准峰贴带底（`f_ref <= band_lo*1.2`）时所有点的 d_f 都≈1，
    后端会置 `fpeak_resolution_limited=true` 并在 notes 首条告警；这种场次实际只剩 rho 一个判据。

---

## 附录 A：本次验证用的一次性合成驱动（不随交付）

放在工程外运行，复用仓库根 06 的重参数化函数做校准，通过 MQTT 发 PROTOCOL §1 报文。
以下是去掉服务器地址等无关代码后的核心逻辑（`pkg` 用于测试固件 contact 口径；
仿真相位用 `dev="sim-01"` 且每拍加 `"sp": true`，用来验证 7b 的隔离规则）：

```python
# drive_points.py — throw-away test data source, NOT part of the deliverable
import base64, json, sys, time
import numpy as np, paho.mqtt.client as mqtt

FS, N, PRE, SCALE = 2567.0, 512, 48, 8192.0
BAND_LO, BAND_HI, CROSS = 30.0, 1000.0, 300.0
GRAV = np.array([0.02, -0.01, 1.0])

def hp_noise(rng, sigma):
    x = rng.normal(0.0, 1.0, N)
    spec = np.fft.rfft(x); f = np.fft.rfftfreq(N, d=1.0 / FS)
    spec[(f < 300.0) | (f > 1150.0)] = 0.0
    y = np.fft.irfft(spec, N)
    return y / y.std() * sigma if y.std() > 0 else y

def synth(f_line, line_amp=0.6, noise_amp=0.0, seed=0, tau_ms=15.0, f_jitter=0.0):
    rng = np.random.default_rng(seed)
    f_line *= 1.0 + f_jitter
    t = np.arange(N) / FS
    acc = np.tile(GRAV, (N, 1)) + rng.normal(0.0, 0.0003, (N, 3))
    loc = t - PRE / FS; on = loc >= 0
    env = np.exp(-np.maximum(loc, 0.0) / (tau_ms / 1000.0))
    ramp = np.zeros(N); ramp[on] = 1.0 - np.exp(-loc[on] / 0.0015)
    osc = np.zeros(N)
    osc[on] = line_amp * env[on] * ramp[on] * np.sin(2 * np.pi * f_line * loc[on])
    acc[:, 2] += osc; acc[:, 0] += 0.35 * osc
    if noise_amp > 0:
        nb = hp_noise(rng, noise_amp) * ramp
        acc[:, 2] += nb; acc[:, 0] += 0.3 * nb
    return np.clip(np.round(acc * SCALE), -32768, 32767).astype("<i2")

# 与 analyzer 完全相同的特征调用（banded = 06 的重参数化版本）
def features(q):
    acc = q.astype(float) / SCALE
    mag = np.linalg.norm(acc, axis=1)
    amp = mag - float(np.median(mag[:PRE]))
    return banded(np.arange(N) / FS, amp, FS, band_lo_hz=BAND_LO,
                  band_hi_hz=BAND_HI, crossover_hz=CROSS)

def tune_noise(f_line, target_ratio, line_amp=0.6):
    lo, hi = 0.0, 0.5
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        r = features(synth(f_line, line_amp, mid))["band_ratio_lh"]
        lo, hi = (mid, hi) if r > target_ratio else (lo, mid)
    return 0.5 * (lo + hi)

def publish_point(pub, pt, rho, f_line, r_ref, taps=5, pkg=0.45):
    target = rho * r_ref
    params = []
    for k in range(taps):
        rng = np.random.default_rng(1000 + k)
        params.append({"f_j": float(rng.normal(0.0, 0.004)),
                       "a_j": 0.6 * float(rng.uniform(0.97, 1.03)),
                       "n_j": float(rng.uniform(0.96, 1.04)), "seed": 1000 + k})
    noise = tune_noise(f_line, target)
    qs = []
    for _ in range(6):
        qs = [synth(f_line, p["a_j"], noise * p["n_j"], seed=p["seed"],
                    f_jitter=p["f_j"]) for p in params]
        med = float(np.median([features(q)["band_ratio_lh"] for q in qs]))
        noise *= (med / target) ** 0.5
    for q in qs:
        pub.publish(pt, q, pkg=pkg)   # 见下：报文带 pt / pkg
```

驱动里的 `pub.publish` 与报文格式：`{"dev","pt","seq","tap","fs":2567,"n":512,
"scale":8192,"pre":48,"trig","pkg"}}{"d":"<base64 int16LE>"}`；主表 P0–P4 的目标 rho 分别是
1.00 / 0.90 / 0.70 / 0.45 / 0.30，额外点 P5（d_f=1.00）、P6（不��� pkg，走启发式）、
`P?`（无 pt + pkg=0.02）用于测一致性、contact_source 与质量门。
