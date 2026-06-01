@echo off
setlocal
echo === Compare sent vs received (Windows) ===
cd /d "%~dp0.."

REM Find latest mock sent log
set SENT=
for /f "delims=" %%i in ('dir /b /od logs\mock_sent_*.jsonl 2^>nul') do set SENT=%%i

if "%SENT%"=="" (
    echo ERROR: No mock_sent_*.jsonl found in logs\
    echo Run scripts\run_mock.bat first.
    exit /b 1
)

echo Using sent log: logs\%SENT%
python compare.py --sent "logs\%SENT%"

echo.
echo Report saved to logs\test_report_*.md
