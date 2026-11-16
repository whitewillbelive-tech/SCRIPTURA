@echo off
setlocal
where py >nul 2>&1
if not errorlevel 1 (
  py -3 "%~dp0scripts\c04_windows_acceptance.py"
) else (
  python "%~dp0scripts\c04_windows_acceptance.py"
)
if errorlevel 1 (
  echo SCRIPTURA acceptance was not completed. See the status above.
  pause
  exit /b 1
)
pause
endlocal
