@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
) else if exist "venv\Scripts\activate.bat" (
    call "venv\Scripts\activate.bat"
) else (
    echo No virtual environment was found.
    echo Recommended setup:
    echo   python -m venv .venv
    echo   .venv\Scripts\activate
    echo   python -m pip install -r requirements.txt
    echo.
    echo Continuing with the active Python environment.
)

python setup_windows.py
if errorlevel 1 (
    echo.
    echo Setup check reported warnings. Review the messages above before using admin/data workflows.
    echo.
)

python -m streamlit run app\main.py --server.headless false
endlocal
