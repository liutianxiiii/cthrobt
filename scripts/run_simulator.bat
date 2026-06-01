@echo off
setlocal
echo === Standalone Simulator (Windows) ===
echo Listens on 127.0.0.1:7777 -- use instead of bridge.py for debug without Renode
echo.
cd /d "%~dp0.."
python simulator.py
