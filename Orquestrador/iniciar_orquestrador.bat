@echo off
title MANAGER RPA - Orquestrador Central
color 0A

:: Garante que o script rode na pasta Orquestrador, mesmo se aberto como Administrador
cd /d "%~dp0"

echo ====================================================
echo  Iniciando Painel do Orquestrador (Win 2012 R2)...
echo ====================================================
echo.

:: 1. Ativa o ambiente virtual do Python silenciosamente
call ..\.venv\Scripts\activate.bat

:: 2. Abre o navegador do servidor ja na tela do Dashboard
start chrome http://localhost:8080

:: 3. Inicia o servidor liberado na porta 8080 pra receber os Agentes (0.0.0.0)
python -m uvicorn main:app --host 0.0.0.0 --port 8080

echo Servidor foi desligado.
pause
