@echo off
rem Resolve the PowerShell launcher relative to this file when started from Explorer.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch_app.ps1" %*
