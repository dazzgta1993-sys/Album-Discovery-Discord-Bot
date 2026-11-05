@echo off
title Stop Album Discovery Discord Bot
echo Stopping Album Discovery Discord Bot and FFmpeg streams...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { ($_.Name -match 'python' -and $_.CommandLine -match 'bot\.py') -or $_.Name -match 'ffmpeg' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
echo Done! All bot and audio processes have been stopped.
timeout /t 2 >nul
