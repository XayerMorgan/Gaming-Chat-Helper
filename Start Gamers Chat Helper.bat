@echo off
cd /d "%~dp0"
python "%~dp0gamers_chat_helper.py" %*
if errorlevel 1 (
    echo.
    echo App exited with an error.
    pause
)
