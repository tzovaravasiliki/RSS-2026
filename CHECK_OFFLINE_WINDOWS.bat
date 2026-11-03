@echo off
cd /d "%~dp0"
title RSS2027 v1.1 - FREE OFFLINE CHECK
where py >nul 2>nul
if errorlevel 1 (
    set "RSS2027_PY=python"
) else (
    set "RSS2027_PY=py"
)
%RSS2027_PY% -m unittest -v
if errorlevel 1 goto failed
%RSS2027_PY% replay_audit.py
if errorlevel 1 goto failed
start "" "%~dp0offline_audit\report.html"
echo Offline check complete. No new model API calls were made.
pause
exit /b 0
:failed
echo Check failed. Copy the error text; do not start a live experiment yet.
pause
exit /b 1
