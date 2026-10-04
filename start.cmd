@echo off
rem Double-click or run from a terminal: starts the API and the web app (see start.ps1 for options).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
if errorlevel 1 pause
