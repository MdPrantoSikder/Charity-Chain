@echo off
echo =========================================
echo    CharityChain - Starting Backend
echo =========================================
echo.
echo Make sure you already ran:
echo    ~/charitychain_start.sh   in WSL
echo.
cd /d "%~dp0backend"
call venv\Scripts\activate
python -m uvicorn main:app --reload
