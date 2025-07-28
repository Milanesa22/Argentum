@echo off
REM Activar entorno virtual
call venv\Scripts\activate

REM Iniciar el sistema principal
python -m aurelius.main

REM Mantener ventana abierta si algo falla
pause