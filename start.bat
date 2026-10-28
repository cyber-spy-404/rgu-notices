@echo off
title Raiganj University Notice & SMTP Dispatcher
echo ==============================================================
echo    Raiganj University Notice & SMTP Dispatcher Launcher
echo ==============================================================
echo.

setlocal enabledelayedexpansion
cd /d "%~dp0"

:: 1. Check if virtualenv exists and works
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe -c "import sys" >nul 2>&1
    if !errorlevel! equ 0 (
        echo [*] Using local virtual environment (.venv)...
        .venv\Scripts\python.exe run.py
        goto done
    ) else (
        echo [!] Detected existing .venv is broken (created on another PC/user path).
        echo [*] Checking system Python to recreate environment...
    )
)

:: 2. Check system Python via 'py' launcher or 'python'
set PYTHON_BIN=
where py >nul 2>&1
if !errorlevel! equ 0 (
    set PYTHON_BIN=py
) else (
    where python >nul 2>&1
    if !errorlevel! equ 0 (
        python -c "import sys" >nul 2>&1
        if !errorlevel! equ 0 (
            set PYTHON_BIN=python
        )
    )
)

:: 3. If Python is available, fix .venv or run directly
if defined PYTHON_BIN (
    echo [*] Found system Python: %PYTHON_BIN%
    if exist ".venv" (
        echo [*] Re-creating virtual environment for this machine...
        rmdir /s /q .venv
        %PYTHON_BIN% -m venv .venv
        if exist ".venv\Scripts\python.exe" (
            echo [*] Installing dependencies from requirements.txt...
            .venv\Scripts\python.exe -m pip install --upgrade pip
            .venv\Scripts\python.exe -m pip install -r requirements.txt
            echo [*] Starting application...
            .venv\Scripts\python.exe run.py
            goto done
        )
    )
    %PYTHON_BIN% run.py
    goto done
)

:: 4. If no Python was found at all
echo.
echo ==============================================================
echo [ERROR] Python is not installed or not in your system PATH!
echo ==============================================================
echo.
echo To run this application, please install Python:
echo 1. Download Python (3.11 or 3.12 recommended) from:
echo    https://www.python.org/downloads/
echo 2. Run the installer and CRITICALLY check the box:
echo    "[X] Add python.exe to PATH"
echo 3. Once installed, double-click start.bat again!
echo ==============================================================
echo.

:done
pause
