@echo off
setlocal
if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" "%~dp0scripts\start.py"
) else (
    where py >nul 2>nul
    if not errorlevel 1 (
        py -3 "%~dp0scripts\start.py"
    ) else (
        where python >nul 2>nul
        if errorlevel 1 (
            echo Instala Python 3.11 o superior para Windows y vuelve a intentarlo.
            pause
            exit /b 1
        )
        python "%~dp0scripts\start.py"
    )
)
if errorlevel 1 (
    echo.
    echo No se pudo iniciar. Revisa el error anterior.
    pause
    exit /b 1
)
exit /b 0
