# Git 仓库

## 位置

```
工作副本（脚本实际运行的地方）:
  C:\Users\admin\Documents\deepseek-harness\default-workspace\warrobots-auto

Git 仓库:
  D:\git\warrobots-auto

GitHub 远程:
  https://github.com/miaoxing4/warrobts-auto.git
  （注意：仓库名是 warrobts-auto，用户给的地址就是这样，不是笔误修正过的 warrobots-auto）
```

**已推送**：`main` 分支，与本地 HEAD 一致（`7825a4d`）。

> 为什么分开：工作副本在 DSH 工作区里（网页服务、ADB 工具都在跑），
> Git 仓库放在用户的 Git 目录下，便于统一管理和推送远程。

## 同步方式

```powershell
# 在工作副本目录下双击，或命令行执行
sync_to_git.bat                          # 用默认提交信息
sync_to_git.bat "feat: 增加 xxx 功能"     # 自定义提交信息
```

`sync_to_git.bat` 做的事（**已包含推送**）：

1. `robocopy /MIR` 把工作副本同步到 `D:\git\warrobots-auto`
   （排除 `tools/ logs/ captures/ __pycache__/ .git/ *.pyc`）
2. 若目标还没有 `.git` → `git init` + `git branch -M main`
3. `git add -A` + `git commit -m "<信息>"`
4. 配置 remote + 代理
5. `git push -u origin main` 推送到 GitHub

## 已忽略的内容（`.gitignore`）

| 忽略项 | 原因 |
|---|---|
| `tools/` | adb 二进制约 24MB，可重新下载（见 `.agent/01-environment.md`） |
| `captures/` | 运行截图，36MB+；**回归用的样本已压缩成 JPEG 放 `tests/fixtures/`** |
| `logs/` | 运行日志、分值历史（本地数据） |
| `__pycache__/`、`*.pyc` | Python 字节码 |
| `.tmp/` | adb 的临时目录（`device.py` 会把 TMP 指到这里） |

## 入库的内容

| 内容 | 体积 | 说明 |
|---|---|---|
| `*.py` × 15 | ~200KB | 全部代码 |
| `*.md` × 12+ | ~80KB | README + AGENTS + `.agent/*` |
| `tests/fixtures/*.jpg` × 21 | 5.0MB | 回归测试样本（由 PNG 压成 JPEG） |
| `.agent/screenshots/*.jpg` × 12 | 1.2MB | 关键界面截图（文档用） |
| `templates/digits/*.npy` × 62 | 0.2MB | 数字识别模板 |

仓库总体积约 **12 MB**（含 `.git`）。

## 首次提交记录

```
5a8c7b9 feat: War Robots 手机端自动化工具
127 files changed, 6792 insertions(+)
```

## 推送到远程 —— 必须走代理

**关键**：本机直连 GitHub 会 `Recv failure: Connection was reset`，
**必须使用代理 `http://127.0.0.1:7897`**（Clash 默认端口）。

仓库内已固化代理配置（无需每次加参数）：

```powershell
cd D:\git\warrobots-auto
git config http.proxy http://127.0.0.1:7897
git config https.proxy http://127.0.0.1:7897
```

推送：

```powershell
git push -u origin main
```

只验证连通性（不推送）：

```powershell
git ls-remote --heads origin
# 空输出 = 仓库存在但没有分支；报 Connection reset = 代理没生效
```

### 排查清单

| 现象 | 原因 | 处理 |
|---|---|---|
| `Recv failure: Connection was reset` | 没走代理 | 确认代理端口 7897 在监听；`git config http.proxy` |
| `Authentication failed` | 没有 Token | 生成 GitHub Personal Access Token 作为密码 |
| `Repository not found` | 没建仓库 / 名字不对 | 确认 `miaoxing4/warrobts-auto` 存在 |
| 推送卡住不动 | 交互式提示等待输入 | `set GIT_TERMINAL_PROMPT=0` 让其快速失败 |

> 注：`git push` 的进度信息走 stderr，PowerShell 会显示成红色红字 + exit code 1，
> **这不代表失败**。以 `git ls-remote --heads origin` 能否看到 commit 为准。

## 换行符约定

`.gitattributes` 已设置：
- 通用文件 `eol=lf`
- `*.bat` 保持 `eol=crlf`（Windows 批处理需要）
- `*.jpg /*.png /*.npy /*.exe` 标记为 binary
