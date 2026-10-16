@echo off
rem LagSlice crash diagnosis: run with EStats disabled
rem Place next to LagSlice.exe and double-click
set LAGSLICE_NO_ESTATS=1
start "" "%~dp0LagSlice.exe"
