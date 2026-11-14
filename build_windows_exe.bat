@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  set "PY=py -3.12"
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo Khong tim thay Python tren MAY BUILD.
    echo Neu ban chi su dung EXE, khong can chay file nay.
    echo Hay dung GitHub Actions theo BUILD_EXE_ON_GITHUB.md.
    pause
    exit /b 1
  )
  set "PY=python"
)
%PY% -m pip install --upgrade pip
if errorlevel 1 goto fail
%PY% -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto fail
%PY% -m PyInstaller --noconfirm --clean --onefile --windowed --name PDF2Inventor_AI --collect-all PySide6 --collect-all fitz main.py
if errorlevel 1 goto fail
echo.
echo BUILD THANH CONG: dist\PDF2Inventor_AI.exe
echo Copy file EXE sang may su dung. May su dung khong can Python.
pause
exit /b 0
:fail
echo BUILD THAT BAI. Hay kiem tra ket noi Internet va Python tren may BUILD.
pause
exit /b 1
