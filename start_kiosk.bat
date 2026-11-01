@echo off
rem CGC SQUARE: start everything with one command (double-click this file, or run start_kiosk.bat).
rem Options are passed through, for example:  start_kiosk.bat --window     start_kiosk.bat --check
title CGC SQUARE kiosk
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (set "PYCMD=py") else (set "PYCMD=python")

%PYCMD% run_kiosk.py %*
set "CODE=%errorlevel%"

if not "%CODE%"=="0" (
  echo.
  echo The kiosk stopped with an error ^(code %CODE%^). Read the messages above.
  pause
)
exit /b %CODE%
