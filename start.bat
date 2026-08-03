@echo off
title Climate Mesh - Decentralised Climate Early-Warning Mesh
echo ============================================
echo   Climate Mesh - Decentralised Monitor
echo ============================================
echo.
echo Installing dependencies (first run only)...
pip install -r "%~dp0requirements.txt" -q
echo.
echo Starting the mesh (deterministic demo: simulation + risk engine)...
start "" cmd /k "cd /d "%~dp0" && python run.py --mode demo"
echo.
echo Waiting 3 seconds for the backend to initialise...
timeout /t 3 /nobreak >nul
echo Opening the Streamlit dashboard...
start "" cmd /k "cd /d "%~dp0" && python -m streamlit run dashboard/app.py"
echo.
echo The dashboard opens in your browser. Pick scenarios from the sidebar.
echo Close both terminal windows to stop the system.
