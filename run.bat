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

rem Local accounts live in a separate, git-ignored database copy.
if not defined SNP_DATABASE_PATH set "SNP_DATABASE_PATH=database\snp_platform.local.db"

python -m streamlit run app\main.py --server.headless false --server.port 8510
endlocal
