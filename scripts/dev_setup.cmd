@echo off
setlocal

if not exist .venv (
    py -3 -m venv .venv
)

call .venv\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 exit /b 1
call .venv\Scripts\python.exe -m pip install -e .
if errorlevel 1 exit /b 1

echo Environment ready.
echo Activate with: .venv\Scripts\activate.bat
echo Then use: lumentp ping --host 127.0.0.1 --port 8091
