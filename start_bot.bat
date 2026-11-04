@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"
title Album Discovery - Discord Music Bot

:: Detect Python 3.12
set "PY_EXE="
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set "PY_EXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
) else (
    where py >nul 2>nul && set "PY_EXE=py"
    if not defined PY_EXE (
        where python >nul 2>nul && set "PY_EXE=python"
    )
)

if not defined PY_EXE (
    echo [ERROR] Python 3.12 not detected.
    pause
    exit /b 1
)

:: Ensure .env exists
if not exist ".env" (
    if exist ".env.example" copy ".env.example" ".env" >nul
)

findstr /C:"DISCORD_BOT_TOKEN=your_token_here" ".env" >nul 2>&1
if not errorlevel 1 (
    echo [!] Please paste your DISCORD_BOT_TOKEN into .env
    notepad ".env"
    pause
)

cls
"%PY_EXE%" -u bot.py
if errorlevel 1 pause
