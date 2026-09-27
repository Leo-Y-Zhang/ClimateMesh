@echo off
title Climate Mesh - Decentralised Climate Early-Warning Mesh
echo ============================================
echo   Climate Mesh - Decentralised Monitor
echo ============================================
echo.
echo Installing dependencies (first run only)...
python -m pip install -r "%~dp0requirements.txt" -q
if errorlevel 1 (
  echo.
  echo Could not install the requirements. Is Python 3.11+ installed and on PATH?
  echo Download it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
  pause
  exit /b 1
)
echo.
echo Starting the mesh (deterministic demo: simulation + risk engine)...
start "" cmd /k "cd /d "%~dp0" && python run.py --mode demo"
echo.
echo Waiting 3 seconds for the backend to initialise...
timeout /t 3 /nobreak >nul
echo Starting the Streamlit dashboard...
start "" cmd /k "cd /d "%~dp0" && python -m streamlit run dashboard/app.py"
REM .streamlit/config.toml sets headless = true for the Raspberry Pi, so
REM Streamlit never opens a browser itself: open it from here instead.
echo Waiting 8 seconds for the dashboard to start...
timeout /t 8 /nobreak >nul
start "" http://127.0.0.1:8501
echo.
echo The dashboard is at http://127.0.0.1:8501 in your browser. If the page is
echo still loading, give it a few seconds and refresh. Pick scenarios from the sidebar.
echo Close both terminal windows to stop the system.
