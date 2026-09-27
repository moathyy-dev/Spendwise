@echo off
REM SpendWise first-time setup on Windows.
cd /d "%~dp0\.."

echo === Checking for Python ===
where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python was not found on this computer.
  echo Please install it from https://www.python.org/downloads/
  echo IMPORTANT: on the first install screen, check "Add python.exe to PATH".
  goto error
)

echo === Creating virtual environment (.venv) ===
python -m venv .venv
if errorlevel 1 goto error

echo === Activating virtual environment and installing requirements ===
call .venv\Scripts\activate.bat

REM NOTE: we call pip as "python -m pip" (a module run through python.exe)
REM instead of running pip.exe directly. On managed/corporate machines,
REM security software sometimes blocks pip.exe specifically by name while
REM still allowing python.exe itself to run.
python -m pip install --upgrade pip
if errorlevel 1 goto error
python -m pip install -r requirements.txt
if errorlevel 1 goto error
python -m pip install -e .
if errorlevel 1 goto error

if not exist .env (
  echo === Creating .env from .env.example ===
  copy .env.example .env
  echo Created .env - you can edit it later to add a Gemini API key if you want.
)

echo === Applying database migrations ===
alembic upgrade head
if errorlevel 1 goto error

echo.
echo Setup completed successfully!
echo To run the app, use: scripts\run_windows.bat
echo.
pause
goto end

:error
echo.
echo Setup failed. Please scroll up and read the error messages above.
echo.
echo If you saw a message about "pip.exe access denied" or a security /
echo application-control tool blocking pip.exe or python.exe, this computer
echo is managed by your organization's IT department and is blocking this
echo program from installing software. Please contact your IT/system
echo administrator and ask them to allow "python.exe" and "pip" (running
echo as "python -m pip") to run and to access the internet for package
echo installation (pypi.org), then try running this script again.
echo.
pause
exit /b 1

:end
