@echo off
REM WORM Multi-Wallet Farmer - Start Script
REM by Nullclairvoyant

echo.
echo ===================================
echo   WORM Multi-Wallet Farmer
echo ===================================
echo.

REM Check if venv exists
if not exist venv (
    echo [ERROR] Virtual environment not found!
    echo.
    echo Please run setup-windows.bat first.
    echo.
    pause
    exit /b 1
)

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Check if .env exists
if not exist .env (
    echo [ERROR] Configuration file .env not found!
    echo.
    echo Please copy .env.example to .env and edit your settings:
    echo   copy .env.example .env
    echo   notepad .env
    echo.
    pause
    exit /b 1
)

REM Start the miner
echo Starting WORM Miner...
echo.
echo Press Ctrl+C to stop the miner.
echo.
python main.py

REM Keep window open if miner exits
echo.
echo Miner stopped.
pause
