@echo off
setlocal
where py >nul 2>&1
if not errorlevel 1 (
    py -3 "%~dp0scripts\j3_windows_launcher.py"
) else (
    where python >nul 2>&1
    if errorlevel 1 (
        echo Python 3.10 or newer is required. Install Python with Tcl/Tk.
        pause
        exit /b 1
    )
    python "%~dp0scripts\j3_windows_launcher.py"
)
if errorlevel 1 (
    echo SCRIPTURA could not start. Check the message above.
    pause
    exit /b 1
)
endlocal
