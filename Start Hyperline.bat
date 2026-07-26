@echo off
cd /d "%~dp0"
title Hyperline AI

REM Always launch detached so this bat/terminal window closes immediately.
REM The app hard-exits its own Python process on window close (os._exit).

where pythonw >nul 2>&1
if %ERRORLEVEL%==0 (
    start "" pythonw "%~dp0gamers_chat_helper.py" %*
    exit /b 0
)

where python >nul 2>&1
if %ERRORLEVEL%==0 (
    start "" python "%~dp0gamers_chat_helper.py" %*
    exit /b 0
)

echo.
echo Python not found on PATH.
echo Install Python 3.10+ and ensure "python" or "pythonw" works in a terminal.
echo.
pause
exit /b 1
