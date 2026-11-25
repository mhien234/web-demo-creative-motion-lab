@echo off
chcp 65001 >nul
pushd "%~dp0"
title Creative Motion Lab - may chu

if not exist ".venv\Scripts\python.exe" (
  echo Dang tao moi truong Python lan dau...
  py -3 -m venv .venv 2>nul || python -m venv .venv
)
if not exist ".venv\Scripts\python.exe" (
  echo.
  echo [!] May chua co Python. Mo PowerShell va chay:  winget install Python.Python.3.12
  echo     Cai xong, dong cua so nay roi nhap dup start.bat lan nua.
  pause
  exit /b 1
)

if not exist ".venv\installed.txt" (
  echo Dang cai thu vien lan dau, mat khoang 1-2 phut...
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt || (pause & exit /b 1)
  echo ok> ".venv\installed.txt"
)

echo.
echo  Creative Motion Lab dang chay tai  http://localhost:8000
echo  Dong cua so nay de tat may chu.
echo.
start "" cmd /c "timeout /t 3 >nul & start http://localhost:8000"
".venv\Scripts\python.exe" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir backend
pause
