# 环境与设备（实测）

## 设备

| 项 | 值 |
|---|---|
| 型号 | realme **RMX3366**（真我 GT 大师探索版） |
| 系统 | Android 12 / SDK 31 / ColorOS |
| 序列号 | `16569970` |
| 屏幕 | 物理 1080×2400 竖屏；游戏横屏逻辑 2400×1080 |
| 密度 | 480 dpi |
| 触控板 | `/dev/input/event1`，范围 X 0..8639 / Y 0..19199（**与屏幕分辨率不同**） |
| root | **无**（`sendevent` 写 `/dev/input/event1` 返回 Permission denied） |

> 触控板范围异常（8639×19199）曾让我误判为模拟器，但 `ro.build.fingerprint`、
> `ro.build.tags=release-keys`、`ro.boot.verifiedbootstate=green` 均表明是**真机**。
> 游戏内左上角那个「模拟器错误」横幅只是它检测到 ADB 调试，不影响自动化。

## 游戏

| 项 | 值 |
|---|---|
| 包名 | `com.pixonic.wwr` |
| 版本 | 12.4.1（versionCode 290461） |
| 引擎 | Unity（`com.unity3d.player.UnityPlayerActivity`） |
| 语言 | 游戏内为简体中文 |

## 工具链

```
Python : C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe
ADB    : <项目>/tools/platform-tools/adb.exe   (v37.0.1)
```

- 依赖仅 `numpy` + `Pillow`（**不需要 opencv，也不需要 easyocr/tesseract**）
- 尝试过 `pip install opencv-python-headless` / `easyocr`：网络极慢、长时间挂起 →
  最终改用 numpy 自研视觉 + 数字模板匹配，**不要再装这些**

### ADB 来源

本机原本**没有 adb**，也无 `ANDROID_HOME`。已从
`https://dl.google.com/android/repository/platform-tools-latest-windows.zip` 下载解压到
`tools/platform-tools/`。

- Windows 的 `curl.exe` 走系统代理会报 `schannel: SEC_E_NO_CREDENTIALS`
- **PowerShell `Invoke-WebRequest` 也失败**（代理 127.0.0.1:7897）
- 可用方案：用 Python `urllib.request` 下载（成功，8 MB）

### 驱动

**无需手动装驱动**。插上 USB 并开启"USB 调试"后，系统自带 WinUSB 已接管
realme 的 ADB Interface（`USB\VID_22D9&PID_2765&MI_01`）。
首次连接手机上会弹「允许 USB 调试吗？」，勾选"始终允许"即可。

排查用命令（比 `Get-PnpDevice` 可靠，后者在本机返回空）：

```powershell
pnputil /enum-devices /connected | Select-String -Pattern "22D9" -Context 0,8
```

## 项目结构

```
warrobots-auto/
├── engine.py            主引擎（CLI 入口，最大的文件）
├── ad_handler.py        广告安全处理（AppLovin + AdMob）
├── task_ui.py           任务页/黑市/供给中心 按钮精确检测
├── ui_state.py          界面状态识别（核心）
├── vision.py            视觉基础（颜色区域、模板匹配、图像差异）
├── device.py            ADB 封装（截图/点击/滑动/Activity/日志）
├── rating_reader.py     荣誉积分读取（数字模板匹配）
├── rating_report.py     分值趋势报告
├── bootstrap_digits.py  数字模板自举
├── localize.py          颜色扫描定位按钮边界（调试工具）
├── collect_refs.py      界面样本采集
├── test_state_offline.py 状态识别回归（17 用例）
├── templates/digits/    62 个数字模板 .npy
├── captures/            运行截图 + 回归样本
├── logs/                运行日志、评分历史、趋势报告
└── .agent/              本经验库
```
