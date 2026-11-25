@echo off
chcp 65001 >nul
pushd "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
> chan-doan.txt (
  echo === Python ===
  ".venv\Scripts\python.exe" --version
  echo === Import may chu ===
  ".venv\Scripts\python.exe" -c "import backend.main as m; print('import OK, so route:', len(m.app.routes))"
  echo === Cong 8000 dang bi dung boi ===
  netstat -ano | findstr ":8000"
  echo === Chay thu may chu 20 giay ===
)
start "" /b ".venv\Scripts\python.exe" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 >> chan-doan.txt 2>&1
timeout /t 8 /nobreak >nul
powershell -NoProfile -Command "try { (Invoke-WebRequest -UseBasicParsing http://localhost:8000/api/health -TimeoutSec 5).StatusCode } catch { 'LOI: ' + $_.Exception.Message }" >> chan-doan.txt 2>&1
echo === Xong. Cua so nay co the dong; may chu van chay. === >> chan-doan.txt
