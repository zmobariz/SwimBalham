@echo off
setlocal
title Swim Balham
cd /d "%~dp0"
py -3 app.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Swim Balham could not start. Install Python 3 and the packages in requirements.txt.
    echo.
    echo Press any key to close.
    pause >nul
)
