@echo off
REM ============================================================
REM  War Robots 自动化 - 网页控制台启动器
REM  双击本文件即可：启动服务 + 自动打开浏览器
REM ============================================================
chcp 65001 >nul
set PY=C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe
set HERE=%~dp0

title War Robots 自动化控制台

if not exist "%PY%" (
  echo [错误] 找不到 Python: %PY%
  echo 请修改本文件里的 PY 变量为正确的 python.exe 路径
  pause
  exit /b 1
)

echo ============================================================
echo  War Robots 自动化控制台
echo  浏览器将自动打开；关闭本窗口即停止服务
echo ============================================================
echo.

"%PY%" "%HERE%webui.py" %*

echo.
echo 服务已停止。
pause
