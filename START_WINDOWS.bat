@echo off
cd /d "%~dp0"
title RSS2027 Research Workbench 1.2
where py >nul 2>nul
if errorlevel 1 (
    python app.py
) else (
    py app.py
)
pause
