@echo off
setlocal
where py >nul 2>&1
if not errorlevel 1 (
  py -3 "%~dp0scripts\c03_windows_launcher.py"
) else (
  python "%~dp0scripts\c03_windows_launcher.py"
)
if errorlevel 1 (
  echo SCRIPTURA canonical workstation could not start.
  pause
  exit /b 1
)
endlocal
