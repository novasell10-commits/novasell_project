@echo off
setlocal enabledelayedexpansion

echo.
echo ======================================================================
echo       NovaSell Backend - PostgreSQL Setup (Windows SAFE VERSION)
echo ======================================================================
echo.

REM =========================
REM CONFIG POSTGRES PATH FIX
REM =========================
set PSQL="C:\Program Files\PostgreSQL\18\bin\psql.exe"

REM ========== STEP 1 ==========
echo [STEP 1] Checking PostgreSQL installation...

if exist %PSQL% (
    echo PostgreSQL found locally
    %PSQL% --version
) else (
    where psql >nul 2>&1
    if errorlevel 1 (
        echo ERROR: psql not found!
        echo.
        echo Install PostgreSQL and ensure this path exists:
        echo   C:\Program Files\PostgreSQL\18\bin
        echo.
        pause
        exit /b 1
    )
    echo PostgreSQL found via PATH
    psql --version
)

echo.

REM ========== CONFIG ==========
set DB_NAME=novasell_production
set DB_USER=novasell_app
set DB_PASSWORD=novasell_password_change_in_prod
set DB_HOST=localhost
set DB_PORT=5432

echo [STEP 2] Database Configuration:
echo   DB: %DB_NAME%
echo   USER: %DB_USER%
echo   HOST: %DB_HOST%
echo   PORT: %DB_PORT%
echo.

REM ========== PASSWORD ==========
echo [STEP 3] PostgreSQL password (default: postgres)
set /p POSTGRES_PASSWORD=Password: 

REM ========== SQL FILE ==========
set TEMP_SQL=temp_setup.sql

echo [STEP 4] Creating SQL file...

del %TEMP_SQL% >nul 2>&1

echo CREATE USER %DB_USER% WITH PASSWORD '%DB_PASSWORD%'; >> %TEMP_SQL%
echo CREATE DATABASE %DB_NAME% OWNER %DB_USER%; >> %TEMP_SQL%
echo GRANT ALL PRIVILEGES ON DATABASE %DB_NAME% TO %DB_USER%; >> %TEMP_SQL%
echo \c %DB_NAME% >> %TEMP_SQL%
echo CREATE EXTENSION IF NOT EXISTS "uuid-ossp"; >> %TEMP_SQL%
echo CREATE EXTENSION IF NOT EXISTS "pgcrypto"; >> %TEMP_SQL%
echo CREATE EXTENSION IF NOT EXISTS "pg_trgm"; >> %TEMP_SQL%
echo ALTER USER %DB_USER% CONNECTION LIMIT 50; >> %TEMP_SQL%

REM ========== EXECUTE ==========
echo [STEP 5] Running SQL...

set PGPASSWORD=%POSTGRES_PASSWORD%

%PSQL% -h %DB_HOST% -U postgres -f %TEMP_SQL%

if errorlevel 1 (
    echo.
    echo ERROR: Database setup failed
    echo Check:
    echo - PostgreSQL is running
    echo - Password is correct
    echo - User/database doesn't already exist
    del %TEMP_SQL%
    pause
    exit /b 1
)

del %TEMP_SQL%
echo [OK] Database created successfully
echo.

REM ========== ENV ==========
echo [STEP 6] Updating .env...

if exist ".env" (
    copy .env .env.backup >nul
    echo [OK] Backup created
)

(
echo DATABASE_URL=postgresql://%DB_USER%:%DB_PASSWORD%@%DB_HOST%:%DB_PORT%/%DB_NAME%
echo ENVIRONMENT=development
echo DEBUG=true
echo SECRET_KEY=change-me
echo REDIS_URL=redis://localhost:6379
) > .env

echo [OK] .env updated
echo.

REM ========== DONE ==========
echo ======================================================================
echo                    SETUP COMPLETE
echo ======================================================================
echo.
echo DATABASE READY:
echo   postgresql://%DB_USER%:***@%DB_HOST%:%DB_PORT%/%DB_NAME%
echo.
echo NEXT:
echo   .venv\Scripts\activate
echo   python -m uvicorn app.main:app --reload
echo.
pause