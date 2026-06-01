@echo off
setlocal
echo === Mock Controller (Windows) ===
cd /d "%~dp0.."

set COUNT=20
set INTERVAL=0.5
if not "%1"=="" set COUNT=%1
if not "%2"=="" set INTERVAL=%2

echo Sending %COUNT% random packets at %INTERVAL%s interval
echo Target: %HOST% (see config.ini)
echo.
python controller.py --mock --mock-count %COUNT% --mock-interval %INTERVAL%
