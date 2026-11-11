@echo off
cd /d "%~dp0"
python -m pip install -q -r requirements.txt pyinstaller
python build.py %*
pause
