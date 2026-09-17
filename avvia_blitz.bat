@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
title BLITZ CNC — avvio e test (Windows)

rem Nella root del repository.
rem Doppio click = menu.
rem Prompt:  avvia_blitz.bat avvia ^| test ^| setup ^| tutto

cd /d "%~dp0"
set "ROOT=%CD%"
set "VENV=%ROOT%\.venv"
set "PY=%VENV%\Scripts\python.exe"
set "REQ=%ROOT%\requirements-windows.txt"
set "APP=%ROOT%\qt6_app\main_qt.py"
set "SIMULATION=1"
set "PYTHONPATH=%ROOT%;%ROOT%\qt6_app;%PYTHONPATH%"

if /i "%~1"=="avvia" goto :cmd_avvia
if /i "%~1"=="run" goto :cmd_avvia
if /i "%~1"=="test" goto :cmd_test
if /i "%~1"=="setup" goto :cmd_setup
if /i "%~1"=="install" goto :cmd_setup
if /i "%~1"=="tutto" goto :cmd_tutto
if /i "%~1"=="all" goto :cmd_tutto

:menu
echo.
echo ============================================
echo   BLITZ CNC  —  PC Windows (simulazione)
echo ============================================
echo   Cartella: %ROOT%
echo.
echo   1^) Avvia l'applicazione (SIMULATION=1)
echo   2^) Esegui i test (pytest, no hardware live)
echo   3^) Installa / aggiorna dipendenze (.venv)
echo   4^) Test e poi avvio
echo   0^) Esci
echo.
set /p "SCELTA=Scegli [1-4, 0]: "
if "%SCELTA%"=="1" goto :cmd_avvia
if "%SCELTA%"=="2" goto :cmd_test
if "%SCELTA%"=="3" goto :cmd_setup
if "%SCELTA%"=="4" goto :cmd_tutto
if "%SCELTA%"=="0" goto :fine_ok
echo Scelta non valida.
goto :menu

:cmd_setup
call :setup
if errorlevel 1 goto :fine_errore
if "%~1"=="" goto :menu
goto :fine_ok

:cmd_avvia
call :assicura_venv
if errorlevel 1 goto :fine_errore
if not exist "%APP%" (
    echo ERRORE: manca %APP%
    goto :fine_errore
)
echo.
echo Avvio BLITZ in simulazione (niente hardware reale)...
echo Chiudi la finestra dell'app per tornare qui.
"%PY%" "%APP%"
if errorlevel 1 (
    echo L'app e' uscita con errore.
    goto :fine_errore
)
if "%~1"=="" goto :menu
goto :fine_ok

:cmd_test
call :assicura_venv
if errorlevel 1 goto :fine_errore
echo.
echo Esecuzione test (esclusi test hardware live)...
set "QT_QPA_PLATFORM=offscreen"
"%PY%" -m pytest tests --ignore=tests/hardware/test_encoder_live.py --ignore=tests/hardware/test_motor_driver.py
set "TERR=%ERRORLEVEL%"
set "QT_QPA_PLATFORM="
if not "%TERR%"=="0" (
    echo Test FALLITI (codice %TERR%)
    goto :fine_errore
)
echo Test OK.
if "%~1"=="" goto :menu
goto :fine_ok

:cmd_tutto
call :assicura_venv
if errorlevel 1 goto :fine_errore
echo.
echo Esecuzione test (esclusi test hardware live)...
set "QT_QPA_PLATFORM=offscreen"
"%PY%" -m pytest tests --ignore=tests/hardware/test_encoder_live.py --ignore=tests/hardware/test_motor_driver.py
set "TERR=%ERRORLEVEL%"
set "QT_QPA_PLATFORM="
if not "%TERR%"=="0" (
    echo Test FALLITI (codice %TERR%)
    goto :fine_errore
)
echo Test OK. Avvio applicazione...
"%PY%" "%APP%"
if errorlevel 1 goto :fine_errore
if "%~1"=="" goto :menu
goto :fine_ok

:setup
echo.
echo --- Dipendenze Windows (senza GPIO Raspberry) ---
if not exist "%PY%" (
    call :crea_venv
    if errorlevel 1 exit /b 1
)
"%PY%" -m pip install --upgrade pip
if not exist "%REQ%" (
    echo ERRORE: manca %REQ%
    exit /b 1
)
"%PY%" -m pip install -r "%REQ%"
if errorlevel 1 (
    echo ERRORE: pip install fallito
    exit /b 1
)
"%PY%" -c "from PySide6.QtWidgets import QApplication; print('PySide6 OK')"
if errorlevel 1 (
    echo ERRORE: PySide6 non importabile
    exit /b 1
)
echo Dipendenze pronte.
exit /b 0

:crea_venv
echo Creo ambiente virtuale in .venv ...
where py >nul 2>&1
if not errorlevel 1 (
    py -3 -m venv "%VENV%"
    if not errorlevel 1 exit /b 0
)
where python >nul 2>&1
if not errorlevel 1 (
    python -m venv "%VENV%"
    if not errorlevel 1 exit /b 0
)
echo ERRORE: Python 3 non trovato. Installa da https://www.python.org/
echo e spunta "Add python.exe to PATH".
exit /b 1

:assicura_venv
if not exist "%PY%" (
    echo Ambiente .venv assente: lancio setup...
    call :setup
    exit /b %ERRORLEVEL%
)
"%PY%" -c "import PySide6" >nul 2>&1
if errorlevel 1 (
    echo PySide6 assente nel venv: lancio setup...
    call :setup
    exit /b %ERRORLEVEL%
)
exit /b 0

:fine_ok
echo.
pause
exit /b 0

:fine_errore
echo.
pause
exit /b 1
