# 拍击测试仪 · 网页端部署包

这个文件夹是把 `05_firmware/tools/mqtt_demo/` 那套服务打成可以整包拷走的版本：
MQTT broker、分析后端、网页、以及网页依赖的 MQTT.js（已内置，浏览器不需要联网）。

**固件不用动。** 板子开机后连的 broker 地址可以在摇杆菜单里改，改一次就存在 NVS 里，
换电脑、断电重启都不用再输。

---

## 一、需要什么

| 项 | 说明 |
| --- | --- |
| 系统 | Windows 10/11（启动脚本是 .bat；macOS/Linux 把 `start.bat` 里那三条命令手工跑即可） |
| Python | 3.10 以上，安装时勾选 **Add python.exe to PATH** |
| pip 包 | numpy、paho-mqtt、amqtt（`start.bat` 首次运行自动安装） |
| 网络 | 板子和电脑连同一个路由器（同一网段） |

不需要：Internet、Node.js、数据库、任何编译工具链。

---

## 二、三步起服务

1. 把整个 `tap_probe_deploy` 文件夹拷到新电脑（U 盘、网盘、压缩包都行，路径不要含中文空格也可以）。
2. 双击 `start.bat`。它会：检查 Python → 装依赖 → 起三个窗口 → 自动打开浏览器。
3. 看脚本最后打印的两行，记下形如 `mqtt://192.168.3.12:1883` 的地址。

三个窗口分别是 broker（1883/8080）、analyzer（8082）、dashboard 静态服务（8081），
**全部保持打开**，关掉哪个都断。收工跑 `stop.bat` 一次性关干净。

网页地址：<http://localhost:8081/dashboard.html>

> 别直接双击 `dashboard.html` 打开。file:// 下浏览器取不到同源地址，页面里写死的
> 回退 IP 是旧电脑的，会连不上。一定走 `http://localhost:8081/`。

---

## 三、板子端一次性设置（不用重新烧录）

摇杆菜单（TFT1）：

1. **WiFi**：`SCAN FOR AP` → 选到自家 AP → 输密码 → 确认
2. **MQTT**：`BROKER URI` → 改成 `mqtt://<新电脑的IP>:1883` → 确认

确认后板子会立刻重连。设置写入 NVS（本版固件新增），之后断电、换电脑回来都自动生效。
要恢复出厂地址，重刷固件或擦除 NVS 即可。

---

## 四、端口与防火墙

| 端口 | 协议 | 谁在用 |
| --- | --- | --- |
| 1883 | TCP | broker，板子发布测量帧、analyzer 订阅 |
| 8080 | WebSocket | broker 的 MQTT-over-WS，网页订阅原始流与瀑布图 |
| 8081 | HTTP | 网页静态文件（dashboard.html、mqtt.min.js） |
| 8082 | HTTP/WS | analyzer 的分析 API、分级、网格 |

第一次运行 Windows 会弹防火墙提示，勾选 **专用网络** 允许。
如果页面能开、板子在线的状态却一直不亮，八成是被拦了；管理员窗口执行：

```
netsh advfirewall firewall add rule name="tap-probe" dir=in action=allow protocol=TCP localport=1883,8080,8081,8082
```

---

## 五、数据存在哪

| 路径 | 内容 |
| --- | --- |
| `.session/taps.jsonl` | 本次会话所有测量与特征 |
| `.session/reference.json` | 参考点（网页里选的那个） |
| `.session_archive/` | 归档过的历史会话 |

整个文件夹拷走 = 历史数据一起带走，不需要导出。

---

## 六、没有网时怎么装依赖

在有网的机器上（本文件夹里已经带了 `wheels/` 就不用管这步）：

```
python -m pip download -d wheels -r requirements.txt
```

把 `wheels` 文件夹一起拷过去，`start.bat` 会自动优先本地安装，全程不需要外网。

---

## 七、没有板子时怎么自测

另开一个窗口：

```
python simulator.py --mode alternate
```

会以 `sim-01` 的身份发布合成拍击，网页上应能看到波形与分级结果——
用来确认"网页这套东西本身是通的"，与板子无关。

---

## 八、常见问题

| 现象 | 原因 |
| --- | --- |
| 页面打开但所有数值都是空的 | 板子 MQTT 页的 BROKER URI 还是旧 IP；或防火墙拦了 python |
| 板子状态不亮、TFT 显示 RETRY | 板子和电脑不在同一网段（电脑连了手机热点/有线分到了别的子网） |
| 瀑布图空着 | 没点「开始实时流」；或点数还没攒够一帧（等 2 秒） |
| 换端口后网页连不上 | 网页里 8080/8082 是写死的，改端口要同时改 `dashboard.html` 顶部 `WS_URL`/`MQTT_WS_URL` |
| 三个窗口闪退 | 端口被旧进程占着，先跑 `stop.bat` 再 `start.bat` |

---

## 九、和仓库源码的关系

这个文件夹是**快照**，不是软链接。仓库里改了服务端要重新拷过来：

```
cp 05_firmware/tools/mqtt_demo/{broker.py,analyzer.py,dashboard.html,mqtt.min.js,simulator.py} tap_probe_deploy/
cp 06_analyze_tap.py tap_probe_deploy/
```

文件清单：

| 文件 | 作用 |
| --- | --- |
| `start.bat` / `stop.bat` | 一键起/停 |
| `ip.py` | 打印本机内网 IP 与要填进板子的 broker 地址 |
| `broker.py` | 本地 MQTT broker（amqtt），1883 + 8080 |
| `analyzer.py` | 订阅、特征提取、分级、网格 API，8082 |
| `06_analyze_tap.py` | 特征提取算法本体（analyzer 按路径加载） |
| `dashboard.html` | 网页 |
| `mqtt.min.js` | 浏览器侧 MQTT 客户端（本地文件，不走 CDN） |
| `simulator.py` | 无板子时的合成拍击源 |
| `requirements.txt` | pip 依赖 |
