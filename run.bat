@echo off
REM Inicia o app Streamlit e abre o navegador (Windows).
cd /d "%~dp0"

REM Ativa a virtualenv, se existir.
if exist ".venv\Scripts\activate.bat" call ".venv\Scripts\activate.bat"
if exist "venv\Scripts\activate.bat" call "venv\Scripts\activate.bat"

set PORT=8501

REM Abre o navegador.
start "" "http://localhost:%PORT%"

streamlit run app.py --server.port %PORT% --server.headless true
