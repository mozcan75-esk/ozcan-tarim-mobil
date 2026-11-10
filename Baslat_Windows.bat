@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
 echo Python 3 bulunamadi. Python 3.11 veya uzeri kurun.
 pause
 exit /b 1
)
if not exist .venv\Scripts\python.exe py -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install -r requirements.txt
if errorlevel 1 (
 echo Kurulum basarisiz.
 pause
 exit /b 1
)
if "%OZCAN_TARIM_PASSWORD%"=="" (
 echo Web uygulamasi icin bir parola belirleyin.
 set /p OZCAN_TARIM_PASSWORD=Parola: 
)
if "%OZCAN_TARIM_PASSWORD%"=="" (
 echo Bos parola kabul edilmez.
 pause
 exit /b 1
)
set OZCAN_TARIM_LAN=0
start "" http://127.0.0.1:5000
python app.py
pause
