@echo off
REM Nostr AI Swarm - Startup Script for Windows

echo Starting Nostr AI Swarm...
echo.

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed. Please install Python 3.8 or higher.
    pause
    exit /b 1
)

echo Python found

REM Check if virtual environment exists
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Install/upgrade dependencies
echo Installing dependencies...
pip install -q --upgrade pip
pip install -q -r requirements.txt

echo.
echo Setup complete!
echo.
echo Starting web server on http://localhost:8000
echo    Press Ctrl+C to stop
echo.

REM Start the server
python backend.py

pause
