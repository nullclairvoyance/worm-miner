@echo off
REM WORM Multi-Wallet Farmer Setup Script for Windows
REM by Nullclairvoyant
REM Handles lru-dict binary wheel installation

echo.
echo ===================================
echo   WORM Multi-Wallet Farmer Setup
echo ===================================
echo.

REM Check Python installation
echo [1/6] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found!
    echo.
    echo Please install Python 3.9+ from:
    echo https://www.python.org/downloads/
    echo.
    echo Make sure to check "Add Python to PATH" during installation
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo [OK] Python %PYTHON_VERSION% found
echo.

REM Create virtual environment
echo [2/6] Setting up virtual environment...
if exist venv (
    echo [OK] Virtual environment already exists
) else (
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created
)
echo.

REM Activate virtual environment
echo [3/6] Activating virtual environment...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo [ERROR] Failed to activate virtual environment
    pause
    exit /b 1
)
echo [OK] Virtual environment activated
echo.

REM Upgrade pip and setuptools
echo [4/6] Upgrading pip, setuptools, and wheel...
python -m pip install --upgrade pip setuptools wheel --quiet
if errorlevel 1 (
    echo [WARNING] Partial upgrade failure, continuing...
)
echo [OK] Package managers upgraded
echo.

REM Install dependencies
echo [5/6] Installing dependencies...
echo This may take a few minutes...
REM Install web3 first (includes eth-account as dependency)
echo Installing web3...
pip install --only-binary=:all: web3==6.15.0
if errorlevel 1 (
    echo [WARNING] Binary-only failed, trying standard install...
    pip install web3==6.15.0
)
REM Install remaining packages
echo Installing other dependencies...
pip install requests==2.31.0 python-dotenv==1.0.1 rich==13.7.0
if errorlevel 1 (
    echo.
    echo [ERROR] Dependency installation failed!
    echo.
    echo Troubleshooting:
    echo 1. Ensure you have a stable internet connection
    echo 2. Try running this script as Administrator
    echo 3. Install Visual C++ Build Tools if needed:
    echo    https://visualstudio.microsoft.com/visual-cpp-build-tools/
    echo.
    pause
    exit /b 1
)
echo [OK] Dependencies installed
echo.

REM Setup .env file
echo [6/6] Setting up configuration...
if exist .env (
    echo [OK] .env file already exists
) else (
    if exist .env.example (
        copy .env.example .env >nul
        echo [OK] Created .env from template
        echo.
        echo [ACTION REQUIRED] Please edit .env with your settings:
        echo   - RPC_URL (Alchemy/Infura Sepolia endpoint^)
        echo   - PK1 (Your wallet private key^)
        echo.
        echo To edit: notepad .env
    ) else (
        echo [WARNING] .env.example not found, skipping .env creation
    )
)
echo.

REM Verify installation
echo ===================================
echo   Verifying Installation
echo ===================================
echo.
python -c "import web3, requests, dotenv, rich; print('[OK] All dependencies verified')" 2>nul
if errorlevel 1 (
    echo [WARNING] Some dependencies may be missing
    echo Try reinstalling: pip install -r requirements-windows.txt
) else (
    echo [SUCCESS] Installation complete!
)
echo.

REM Check configuration
echo ===================================
echo   Configuration Check
echo ===================================
echo.
if exist .env (
    python main.py --dry-run 2>nul
    if errorlevel 1 (
        echo.
        echo [INFO] Configuration incomplete or invalid
        echo.
        echo Please edit your .env file with:
        echo   notepad .env
        echo.
        echo Required settings:
        echo   RPC_URL=https://eth-sepolia.g.alchemy.com/v2/YOUR_KEY
        echo   PK1=your_private_key_here
        echo   PROVER_URL=https://worm-miner-3.darkube.app
        echo.
        echo Then run: python main.py
    )
) else (
    echo [INFO] No .env file found. Create one from .env.example
)
echo.

echo ===================================
echo   Next Steps
echo ===================================
echo.
echo 1. Edit .env file: notepad .env
echo 2. Run the miner: python main.py
echo 3. Test config: python main.py --dry-run
echo.
echo To reactivate environment later:
echo   venv\Scripts\activate.bat
echo.
pause
