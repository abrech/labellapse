@echo off
cd /d "%~dp0"
start "" "%~dp0venv\Scripts\pythonw.exe" "%~dp0record_activity.py"
