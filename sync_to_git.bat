@echo off
REM ============================================================
REM  把当前工作目录同步到 Git 仓库并提交
REM  工作目录 : 本项目所在目录（脚本自己所在位置）
REM  Git 仓库 : D:\git\warrobots-auto
REM ============================================================
chcp 65001 >nul
setlocal

set SRC=%~dp0
set DST=D:\git\warrobots-auto

echo ============================================================
echo  同步到 Git 仓库
echo    源   : %SRC%
echo    目标 : %DST%
echo ============================================================
echo.

if not exist "%DST%" (
  echo [1/3] 创建仓库目录
  mkdir "%DST%"
) else (
  echo [1/3] 仓库目录已存在
)

echo [2/3] 复制文件（排除 tools / logs / captures / __pycache__ / .git）
robocopy "%SRC%" "%DST%" /MIR /XD tools logs captures __pycache__ .git /XF *.pyc /NFL /NDL /NJH /NJS >nul
if errorlevel 8 (
  echo [错误] robocopy 失败，code=%errorlevel%
  pause
  exit /b 1
)

cd /d "%DST%"

if not exist ".git" (
  echo [3/3] 初始化 git 仓库
  git init -q
  git branch -M main
) else (
  echo [3/3] 已有 git 仓库
)

git add -A
git -c core.quotepath=false status --short

echo.
set MSG=%~1
if "%MSG%"=="" set MSG=update: sync from working copy
git diff --cached --quiet
if errorlevel 1 (
  git commit -q -m "%MSG%"
  echo.
  echo ✔ 已提交: %MSG%
) else (
  echo.
  echo 没有变更需要提交
)

echo.
echo ------------------------------------------------------------
echo  仓库位置: %DST%
echo  查看历史: cd /d "%DST%" ^&^& git log --oneline
echo  添加远程: cd /d "%DST%" ^&^& git remote add origin ^<你的仓库URL^>
echo  推送到远程: git push -u origin main
echo ------------------------------------------------------------
echo.
pause
