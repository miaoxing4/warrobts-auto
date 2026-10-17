# 无线 ADB（实测）

## 结论：可以用，比 USB 慢约 2.5 倍，日常够用

| 指标 | USB | 无线（Wi-Fi 5G） |
|---|---|---|
| `detect()` 一次 | ~0.8s | **~2.0~2.2s** |
| 截图（PNG 方式） | ~1.0s | 2.84s |
| **截图（RAW 方式，现用）** | ~0.7s | **2.07s** |
| 传输带宽 | — | 12.3 MB/s |
| 一局战斗流程 | ~150s | ~150~170s（计时靠 sleep，不受影响） |

> 战斗的 1 分钟规则是**基于 sleep 的墙钟时间**，不依赖截图频率，
> 所以无线下依然安全；只是"状态变化被感知"会晚 1~2 秒。

## 为什么 RAW 比 PNG 快

实测拆分（无线）：

```
PNG  exec-out  ：编码+传输 2.84s   （设备端 PNG 编码本身就是 ~1.1s）
RAW  exec-out  ：编码+传输 2.07s   （无需编码，直接传 10MB，带宽 12MB/s 吃得下）
PNG | gzip -1  ：2.58s
RAW | gzip -1  ：3.28s             （设备端 gzip 比省下的带宽更贵）
```

→ 所以 `device.screenshot()` 现在**优先用 raw**（16 字节头 + RGBA），失败才回退 PNG。

## 三种连接方式

### 方式 A：无线调试 + mDNS 自动发现（推荐，Android 11+）

手机：设置 → 开发者选项 → **无线调试** 打开。

```powershell
wireless.bat
```

脚本会 `adb mdns services` 找到 `_adb-tls-connect._tcp`，
自动 `adb connect`，并把串号写入 `.device_serial`。

实测发现结果：
```
adb-16569970-OuYTFO  _adb-tls-connect._tcp  192.168.1.9:39365
```

> 端口是**随机的**（39365），手机重启/重开无线调试后会变，重跑脚本即可。

### 方式 B：首次配对（未配对过时）

手机上「无线调试 → 使用配对码配对设备」会显示 `IP:端口` 和 6 位码：

```powershell
wireless.bat pair 192.168.1.9:41234 123456
```

配对成功后再跑一次 `wireless.bat` 建立连接。

### 方式 C：tcpip 固定端口（最简单，但需插一次 USB）

```powershell
wireless.bat tcpip          # 等价于 adb tcpip 5555 + connect
```

之后可以拔掉 USB，串号为 `IP:5555`。
**缺点**：手机重启后失效，需要再插一次 USB。

## 串号选择逻辑（device.py）

```
优先级：环境变量 WR_SERIAL > 文件 .device_serial > 自动
```

- `resolve_serial()` 在 `ensure_server()` 时校验：
  配置的串号不在线时，若恰好只有 1 台设备 → **自动改用那一台**
  （这样 USB/无线来回切换不用手动改配置）
- `.device_serial` 已加入 `.gitignore`（每台机器不同）

常用命令：

```powershell
wireless.bat status     # 看当前串号与设备
wireless.bat forget     # 清除串号，回到自动选择
python wr_wireless.py --ip 192.168.1.9   # 手动指定 IP（端口默认 5555）
```

## 截图缓存（进一步提速）

高频 `detect()` 会造成"截图风暴"。可用环境变量开启短缓存：

```powershell
$env:WR_SHOT_TTL = "0.8"     # 0.8 秒内的重复截图直接复用
```

- 默认 `0` = 不缓存（保持原行为）
- 任何输入动作（tap / swipe / back / keyevent）都会**自动清空缓存**，
  所以不会出现"点了没生效又看到旧画面"的问题

## 无线下的建议

1. **USB 优先**：做战斗循环（`loop`）时用 USB，速度更稳。
2. **无线适合**：广告/礼包/抽奖这类"等待多、截图少"的流程。
3. 手机 Wi-Fi 建议 5GHz；2.4GHz 下传输会明显变慢。
4. 无线调试开着会略微增加耗电。
5. 如果 `adb connect` 失败，先试 `wireless.bat forget` 再重跑。
