@echo off
setlocal
echo === Nintendo Gamepad Controller (Windows) ===
echo Reads real gamepad input and streams to STM32 (or bridge.py on port 7777).
echo Target: see [network] host/port in config.ini
echo.
echo Controls:
echo   Ctrl+C  -- stop
echo.
cd /d "%~dp0.."
python controller.py %*
