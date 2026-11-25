@echo off
chcp 65001 >nul
pushd "%~dp0"
title Creative Motion Lab - kiem tra trinh dung
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
echo Dang chay kiem thu trinh dung, mat khoang 30 giay...
".venv\Scripts\python.exe" -m unittest tests.test_editor -v > kiem-tra-ket-qua.txt 2>&1
echo MA_THOAT=%errorlevel%>> kiem-tra-ket-qua.txt
type kiem-tra-ket-qua.txt
echo.
echo Ket qua da luu vao kiem-tra-ket-qua.txt. Nhan phim bat ky de dong.
pause >nul
