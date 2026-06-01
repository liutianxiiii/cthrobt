@echo off
setlocal
echo === cthrobt setup (Windows) ===
cd /d "%~dp0.."
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo If pip fails due to corporate proxy, run:
    echo   pip config set global.proxy http://PROXY_HOST:PORT
    echo   pip config set global.trusted-host "pypi.org pypi.python.org files.pythonhosted.org"
    exit /b 1
)
echo.
echo Setup complete. You can now run:
echo   scripts\run_mock.bat       -- send random gamepad packets to STM32
echo   scripts\run_simulator.bat  -- start standalone debug simulator
echo   scripts\compare.bat        -- generate test report
