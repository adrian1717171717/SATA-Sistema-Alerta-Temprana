@echo off
title S.A.T.A. - Iniciando Sistema Centinela
color 0A

echo ===================================================
echo       Iniciando Sistema Centinela (S.A.T.A.)
echo ===================================================
echo.

:: Comprobar si Python esta instalado
python --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python no esta instalado o no esta en el PATH.
    echo Por favor, instala Python desde https://www.python.org/downloads/
    echo Asegurate de marcar la opcion "Add Python to PATH" durante la instalacion.
    pause
    exit /b
)

:: Comprobar si existe el entorno virtual
IF NOT EXIST ".venv\Scripts\activate" (
    echo [+] Creando entorno virtual aislado para no afectar tu PC...
    python -m venv .venv
    echo [+] Entorno virtual creado exitosamente.
)

:: Activar entorno virtual
echo [+] Activando entorno virtual...
call .venv\Scripts\activate

:: Instalar/Actualizar dependencias
echo [+] Comprobando e instalando librerias necesarias (requirements.txt)...
echo [+] Si es la primera vez o en otra PC, esto tomara unos minutos.
pip install -r requirements.txt --quiet
echo [+] Librerias listas.

:: Iniciar el programa
echo.
echo [+] Lanzando el Sistema Centinela...
python lanzador.py

:: Si el programa se cierra o falla, pausamos para poder leer la terminal
echo.
echo [+] El sistema se ha cerrado.
deactivate
pause
