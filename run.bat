@echo off
if not exist .venv (
  echo Creando entorno virtual...
  py -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install -r requirements.txt
python -m app.main
