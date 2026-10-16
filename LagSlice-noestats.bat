@echo off
rem LagSlice crash diagnosis: run with EStats disabled
rem Place next to LagSlice.exe, right-click -> "Run as administrator"
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo This diagnostic launcher needs administrator rights.
    echo Right-click this file and choose "Run as administrator".
    pause
    exit /b 1
)
set LAGSLICE_NO_ESTATS=1
start "" "%~dp0LagSlice.exe"
