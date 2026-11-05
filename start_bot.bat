@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"
title Album Discovery - Discord Music Bot

:: 1. Detect Python
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
    echo ==========================================================
    echo [ERROR] Python not detected!
    echo Please install Python 3.10+ from https://www.python.org
    echo Make sure to check "Add Python to PATH" during installation.
    echo ==========================================================
    pause
    exit /b 1
)

:: 2. Check FFmpeg (required for Discord voice streaming)
where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo ==========================================================
    echo [WARNING] FFmpeg was not detected in PATH.
    echo Discord audio streaming requires FFmpeg to be installed.
    echo Quick install via Windows Terminal / PowerShell:
    echo    winget install Gyan.FFmpeg
    echo ==========================================================
    echo.
)

:: 3. Auto-install Python dependencies if not yet installed
"%PY_EXE%" -c "import discord, aiohttp, yt_dlp, ytmusicapi, dotenv" >nul 2>&1
if errorlevel 1 (
    echo [INFO] First-time setup: Installing required dependencies from requirements.txt...
    "%PY_EXE%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Failed to install dependencies.
        pause
        exit /b 1
    )
    echo [SUCCESS] Dependencies installed!
    echo.
)

:: 4. Ensure .env exists with user's bot token
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo [SETUP] Created .env file from template.
    ) else (
        echo DISCORD_BOT_TOKEN=your_token_here > ".env"
    )
)

findstr /C:"your_token_here" ".env" >nul 2>&1
if not errorlevel 1 (
    echo ==========================================================
    echo [ACTION REQUIRED] Please enter your DISCORD_BOT_TOKEN in .env
    echo Opening .env in Notepad...
    echo ==========================================================
    notepad ".env"
    echo After saving your token in .env, press any key to launch...
    pause >nul
)

cls
"%PY_EXE%" -u bot.py
if errorlevel 1 pause
