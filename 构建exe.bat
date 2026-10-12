@echo off
rem 重新打包 exe（需要 Python 3 + Pillow + pystray + PyInstaller）
cd /d "%~dp0"
set "PY=python"
where python >nul 2>nul || set "PY=py -3"

%PY% make_icon.py
%PY% -m PyInstaller --noconfirm --onefile --noconsole --name CodexDeepSeekPet ^
  --icon "%~dp0pet.ico" ^
  --collect-submodules pystray ^
  --exclude-module numpy --exclude-module pandas --exclude-module matplotlib ^
  --exclude-module scipy --exclude-module PyQt5 --exclude-module PySide2 ^
  "%~dp0desktop_pet.py"

echo.
echo 输出：%~dp0dist\CodexDeepSeekPet.exe
pause
