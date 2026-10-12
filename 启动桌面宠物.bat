@echo off
rem 直接用源码启动（不打包），会弹一个控制台窗口，便于看报错
cd /d "%~dp0"
set "PY=python"
where python >nul 2>nul || set "PY=py -3"
%PY% "%~dp0desktop_pet.py"
pause
