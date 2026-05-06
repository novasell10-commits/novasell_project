@echo off
REM ============================================================================
REM NovaSell Backend - Windows Setup Script
REM ============================================================================
REM
REM Usage: Double-click setup_windows.bat OR run in PowerShell:
REM        .\setup_windows.bat
REM
REM Requirements:
REM   - Python 3.9+ installed and in PATH
REM   - PostgreSQL 14+ installed locally or accessible
REM   - pip installed


echo.
echo ======================================================================
echo         NovaSell Backend - Windows Setup
echo ======================================================================
echo.

REM ========== COLORS & STYLES ==========
REM Note: Windows CMD doesn't support ANSI colors easily, using simple text

REM ========== STEP 1: Check Python ==========
echo [STEP 1] Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python from https://www.python.org/
    echo Make sure to check "Add Python to PATH" during installation
    echo.
    pause
    exit /b 1
)
python --version
echo [OK] Python found
echo.

REM ========== STEP 2: Create Virtual Environment ==========
echo [STEP 2] Checking virtual environment...

if exist ".venv" (
    echo Virtual environment already exists
) else (
    echo Creating virtual environment...
    python -m venv .venv
)

echo.

REM ========== STEP 3: Activate Virtual Environment ==========
echo [STEP 3] Activating virtual environment...
call .venv\Scripts\activate.bat
echo [OK] Virtual environment activated
echo.

REM ========== STEP 4: Upgrade pip ==========
echo [STEP 4] Upgrading pip...
python -m pip install --upgrade pip setuptools wheel >nul 2>&1
echo [OK] pip upgraded
echo.

REM ========== STEP 5: Install Requirements ==========
echo [STEP 5] Installing dependencies from requirements.txt...
pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo ERROR: Failed to install requirements
    echo Check your requirements.txt file
    echo.
    pause
    exit /b 1
)
echo [OK] Dependencies installed
echo.

REM ========== STEP 6: Create .env file ==========
echo [STEP 6] Creating .env file...
if not exist ".env" (
    if exist ".env.example" (
        copy .env.example .env
        echo [OK] .env file created from .env.example
        echo.
        echo IMPORTANT: Edit .env file with your values:
        echo   - SECRET_KEY
        echo   - DATABASE_URL
        echo   - OPENAI_API_KEY
        echo   - TWILIO settings
        echo   - Other API keys
    ) else (
        echo [WARNING] .env.example not found, creating minimal .env...
        (
            echo # NovaSell Backend Configuration
            echo ENVIRONMENT=development
            echo DEBUG=true
            echo SECRET_KEY=dev-secret-key-change-in-production
            echo DATABASE_URL=postgresql://novasell_app:password@localhost:5432/novasell_production
            echo REDIS_URL=redis://localhost:6379
            echo CORS_ORIGINS=http://localhost:3000,http://localhost:8080
        ) > .env
        echo [OK] Minimal .env created
    )
) else (
    echo [OK] .env already exists
)
echo.

REM ========== STEP 7: Check PostgreSQL ==========
echo [STEP 7] Checking PostgreSQL installation...
where psql >nul 2>&1
if errorlevel 1 (
    echo.
    echo WARNING: PostgreSQL not found in PATH
    echo.
    echo You have two options:
    echo.
    echo Option 1: Install PostgreSQL
    echo   - Download from https://www.postgresql.org/download/
    echo   - During installation, note the password for 'postgres' user
    echo   - Add PostgreSQL bin to PATH (usually C:\Program Files\PostgreSQL\15\bin)
    echo.
    echo Option 2: Use Docker
    echo   - Install Docker Desktop
    echo   - Run: docker run -e POSTGRES_PASSWORD=postgres -p 5432:5432 postgres:15
    echo.
    echo Option 3: Use WSL2 PostgreSQL
    echo   - Much easier on Windows!
    echo.
    echo Once PostgreSQL is installed, run setup_db_windows.bat
    echo.
) else (
    echo [OK] PostgreSQL found: 
    psql --version
    echo.
    echo Do you want to setup the database now? (Y/N)
    set /p choice=
    if /i "!choice!"=="Y" (
        call setup_db_windows.bat
    ) else (
        echo [SKIP] Database setup skipped
        echo Run 'setup_db_windows.bat' later when ready
    )
)
echo.

REM ========== STEP 8: Create directories ==========
echo [STEP 8] Creating required directories...
if not exist "logs" mkdir logs
if not exist "uploads" mkdir uploads
echo [OK] Directories created
echo.

REM ========== SUCCESS MESSAGE ==========
echo.
echo ======================================================================
echo                    SETUP COMPLETE!
echo ======================================================================
echo.
echo Next steps:
echo.
echo 1. EDIT .env FILE
echo    - Open .env and fill in required values
echo    - At minimum: DATABASE_URL, SECRET_KEY
echo.
echo 2. SETUP DATABASE (if not already done)
echo    - Run: setup_db_windows.bat
echo    - OR manually create PostgreSQL database
echo.
echo 3. RUN THE SERVER
echo    - Make sure .venv is activated
echo    - Run: python -m uvicorn app.main:app --reload
echo    - Access: http://localhost:8000
echo    - API Docs: http://localhost:8000/api/v1/docs
echo.
echo 4. TEST THE API
echo    - curl http://localhost:8000/api/v1/health
echo    - Should return: {"status": "healthy", ...}
echo.
echo ======================================================================
echo.

pause