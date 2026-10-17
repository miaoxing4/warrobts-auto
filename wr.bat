@echo off
REM War Robots Automation - Launcher
set PY=C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe
set HERE=%~dp0

if "%~1"=="" goto help
if "%~1"=="help" goto help

"%PY%" "%HERE%engine.py" %*
goto end

:help
echo ============================================================
echo  War Robots Automation
echo ============================================================
echo  usage: wr.bat ^<command^> [options]
echo.
echo  BASIC
echo    state                 show current UI state
echo    home                  go back to hangar
echo    claim                 claim activity task rewards only
echo.
echo  ADS / REWARDS
echo    daily                 daily-task ads + claim rewards
echo    lottery               supply-center draw (waits 5min cooldown, 3/day)
echo    lottery --no-wait     draw only now, no cooldown wait
echo    ads --rounds N        all ad sources (daily/activity/black market)
echo    ads --lottery         ads + lottery
echo    ads --replenish N     if ads exhausted, play N battles to refill
echo.
echo  BATTLE / DIFFICULTY
echo    battle                play one battle (stays 70s, then exits)
echo    loop --cycles N       N battles + auto record honor rating
echo    rating                read current honor rating (difficulty)
echo    history               show rating history trend
echo.
echo  FULL DAILY (recommended)
echo    all --replenish 2     claim + ads + lottery + battle refill
echo.
echo  examples:
echo    wr.bat all --replenish 2
echo    wr.bat loop --cycles 6
echo    wr.bat daily
echo ============================================================

:end
