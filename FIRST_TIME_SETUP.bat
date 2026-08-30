@echo off
echo =========================================
echo    CharityChain - First Time Setup
echo =========================================
echo.
echo This will:
echo  - Connect to your PostgreSQL database
echo  - Create charitychain database
echo  - Install Python dependencies
echo  - Seed 30 validator nodes
echo  - Create default user accounts
echo.

set /p PGPASSWORD=Enter your PostgreSQL password: 
echo.

echo [1/5] Updating database password in .env...
powershell -Command "(Get-Content 'backend\.env') -replace 'postgres:[^@]*@', 'postgres:%PGPASSWORD%@' | Set-Content 'backend\.env'"
echo     Done

echo [2/5] Creating database...
set PGPASSWORD=%PGPASSWORD%
for %%v in (17 16 15 14) do (
    if exist "C:\Program Files\PostgreSQL\%%v\bin\psql.exe" (
        "C:\Program Files\PostgreSQL\%%v\bin\psql.exe" -U postgres -c "CREATE DATABASE charitychain;" 2>nul
        echo     Database created using PostgreSQL %%v
        goto :deps
    )
)
echo     WARNING: psql.exe not found. Create database manually in pgAdmin.

:deps
echo [3/5] Installing Python dependencies...
cd backend
call venv\Scripts\activate
pip install -r requirements.txt -q
echo     Done

echo [4/5] Seeding 30 validator nodes...
python seed_data.py
echo     Done

echo [5/5] Creating default user accounts...
python create_admin.py
echo     Done

echo.
echo =========================================
echo    SETUP COMPLETE!
echo.
echo    Default Login Accounts:
echo    -------------------------
echo    Admin:   admin@charitychain.com   / Admin@1234
echo    Donor:   donor@charitychain.com   / 12345678
echo    Needy:   needy@charitychain.com   / 12345678
echo    Trustee: trustee@charitychain.com / 12345678
echo.
echo    Next Steps:
echo    1. Open WSL and run: ~/charitychain_start.sh
echo    2. Then run START_CHARITYCHAIN.bat
echo =========================================
pause
