@echo off
echo Terminating old background GUI processes...
taskkill /f /im pythonw.exe >nul 2>&1
cd /d "%~dp0"
start pythonw gui.py
