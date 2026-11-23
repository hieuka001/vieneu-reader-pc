@echo off
chcp 65001 >nul
cd /d %~dp0
if not exist .venv (
  echo Dang tao moi truong ao Python...
  py -3.12 -m venv .venv || python -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul
pip install -r requirements.txt
python run_app.py
pause
