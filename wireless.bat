@echo off
REM ============================================================
REM  无线 ADB 连接助手
REM  手机需已打开「开发者选项 → 无线调试」，且与电脑同一 Wi-Fi
REM ============================================================
chcp 65001 >nul
set PY=C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe
set HERE=%~dp0

if not exist "%PY%" (
  echo [错误] 找不到 Python: %PY%
  pause
  exit /b 1
)

echo ============================================================
echo  无线 ADB 连接
echo ============================================================
echo.

if "%~1"=="" goto auto
if "%~1"=="status" goto status
if "%~1"=="pair" goto pair
if "%~1"=="tcpip" goto tcpip
if "%~1"=="forget" goto forget

"%PY%" "%HERE%wr_wireless.py" %*
goto end

:auto
"%PY%" "%HERE%wr_wireless.py"
goto end

:status
"%PY%" "%HERE%wr_wireless.py" --status
goto end

:pair
shift
"%PY%" "%HERE%wr_wireless.py" --pair %1 %2
goto end

:tcpip
"%PY%" "%HERE%wr_wireless.py" --tcpip 5555
goto end

:forget
"%PY%" "%HERE%wr_wireless.py" --forget
goto end

:end
echo.
pause
