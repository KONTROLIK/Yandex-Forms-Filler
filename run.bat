@echo off
cd /d "%~dp0"
"%~dp0venv\Scripts\python.exe" "%~dp0app.py" %*
if errorlevel 1 pause
