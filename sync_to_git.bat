@echo off
REM ============================================================
REM  把当前工作目录同步到 Git 仓库并提交 + 推送到 GitHub
REM  工作目录 : 本项目所在目录（脚本自己所在位置）
REM  Git 仓库 : D:\git\warrobots-auto
REM  远程     : https://github.com/miaoxing4/warrobts-auto.git
REM ============================================================
chcp 65001 >nul
setlocal

set SRC=%~dp0
set DST=D:\git\warrobots-auto
set REMOTE_URL=https://github.com/miaoxing4/warrobts-auto.git
set PROXY=http://127.0.0.1:7897

echo ============================================================
echo  同步到 Git 仓库并推送
echo    源   : %SRC%
echo    目标 : %DST%
echo    远程 : %REMOTE_URL%
echo ============================================================
echo.

if not exist "%DST%" (
  echo [1/5] 创建仓库目录
  mkdir "%DST%"
) else (
  echo [1/5] 仓库目录已存在
)

echo [2/5] 复制文件（排除 tools / logs / captures / __pycache__ / .git）
robocopy "%SRC%" "%DST%" /MIR /XD tools logs captures __pycache__ .tmp .git /XF *.pyc /NFL /NDL /NJH /NJS >nul
if errorlevel 8 (
  echo [错误] robocopy 失败，code=%errorlevel%
  pause
  exit /b 1
)

cd /d "%DST%"

if not exist ".git" (
  echo [3/5] 初始化 git 仓库
  git init -q
  git branch -M main
) else (
  echo [3/5] 已有 git 仓库
)

REM 确保远程与代理就绪（GitHub 直连会 Connection reset，必须走代理）
git remote remove origin >nul 2>&1
git remote add origin %REMOTE_URL%
git config http.proxy %PROXY%
git config https.proxy %PROXY%

git add -A
set MSG=%~1
if "%MSG%"=="" set MSG=update: sync from working copy

git diff --cached --quiet
if errorlevel 1 (
  git commit -q -m "%MSG%"
  echo [4/5] 已提交: %MSG%
) else (
  echo [4/5] 没有变更需要提交
)

echo [5/5] 推送到 GitHub
git push -u origin main
if errorlevel 1 (
  echo.
  echo [提示] 推送失败。常见原因：
  echo   1. 代理没开 —— 本项目需要 %PROXY% 才能访问 GitHub
  echo   2. 没有凭据 —— 需要用 GitHub Personal Access Token 认证
  echo.
) else (
  echo.
  echo ✔ 已推送到 %REMOTE_URL%
)

echo.
echo ------------------------------------------------------------
echo  仓库: %DST%
echo  历史: cd /d "%DST%" ^&^& git log --oneline
echo  网页: https://github.com/miaoxing4/warrobts-auto
echo ------------------------------------------------------------
echo.
pause
