@echo off
REM Run SpendWise on Windows (after scripts\setup_windows.bat has been run once).
cd /d "%~dp0\.."

if not exist .venv\Scripts\activate.bat (
  echo [ERROR] Virtual environment not found.
  echo Please run scripts\setup_windows.bat first, before this file.
  pause
  exit /b 1
)

call .venv\Scripts\activate.bat
streamlit run app.py

echo.
echo App closed.
pause
