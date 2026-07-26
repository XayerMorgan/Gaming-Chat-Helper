@echo off
cd /d "%~dp0"
title Hyperline AI

REM Always launch detached so this bat/terminal window closes immediately.
REM Validate the interpreter first: Windows may put a broken/newer Python first
REM on PATH even when a healthy Python with Hyperline's packages is installed.

set "HYPERLINE_IMPORTS=import locale, customtkinter, pyperclip, requests; from PIL import Image"

where pythonw >nul 2>&1
if not errorlevel 1 (
    pythonw -c "%HYPERLINE_IMPORTS%" >nul 2>&1
    if not errorlevel 1 (
        start "" pythonw "%~dp0gamers_chat_helper.py" %*
        exit /b 0
    )
)

where py >nul 2>&1
if not errorlevel 1 (
    for %%V in (3.14 3.13 3.12 3.11 3.10) do (
        py -%%V -c "%HYPERLINE_IMPORTS%" >nul 2>&1
        if not errorlevel 1 (
            start "" pyw -%%V "%~dp0gamers_chat_helper.py" %*
            exit /b 0
        )
    )
)

where python >nul 2>&1
if not errorlevel 1 (
    python -c "%HYPERLINE_IMPORTS%" >nul 2>&1
    if not errorlevel 1 (
        start "" python "%~dp0gamers_chat_helper.py" %*
        exit /b 0
    )
)

echo.
echo Hyperline could not find a healthy Python 3.10+ with its packages.
echo.
echo Install the declared dependencies with a working Python:
echo   python -m pip install -r "%~dp0requirements.txt"
echo.
echo Then run Start Hyperline again.
echo.
pause
exit /b 1
