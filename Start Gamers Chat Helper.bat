@echo off
cd /d "%~dp0"

REM Prefer pythonw for the GUI (no console pipe — avoids 0x800700E8 / ERROR_NO_DATA)
where pythonw >nul 2>&1
if %ERRORLEVEL%==0 (
    start "" pythonw "%~dp0gamers_chat_helper.py" %*
    exit /b 0
)

REM Fallback: console python (shows errors if import fails)
python "%~dp0gamers_chat_helper.py" %*
if errorlevel 1 (
    echo.
    echo App exited with an error.
    pause
)
