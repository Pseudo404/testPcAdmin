@echo off
setlocal

rem This file is launched by Windows Task Scheduler at user logon.
set "BASE_DIR=%~dp0.."
set "BACKEND_DIR=%BASE_DIR%\backend"
set "LOG_DIR=%BASE_DIR%\logs"

if not exist "%BACKEND_DIR%\.venv\Scripts\python.exe" exit /b 1
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

cd /d "%BACKEND_DIR%"
".venv\Scripts\python.exe" -m uvicorn main:app --host 0.0.0.0 --port 8000 >> "%LOG_DIR%\backend.log" 2>&1
