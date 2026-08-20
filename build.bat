@echo off
setlocal

echo ============================================
echo   Digimon TCG Lab - Build
echo ============================================

echo.
echo [1/4] Limpando build anterior...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

echo.
echo [2/4] Verificando dados mockados...
if not exist "data\cards.json" (
    echo Gerando dados mockados...
    python data\mock\generate_mock_data.py
    if errorlevel 1 goto :error
)

echo.
echo [3/4] Verificando dependencias...
python -c "import PySide6, pyqtgraph, PIL, pandas, requests, bs4, PyInstaller" 2>nul
if errorlevel 1 (
    echo Instalando dependencias faltantes...
    python -m pip install -r requirements.txt --quiet
    if errorlevel 1 goto :error
) else (
    echo Dependencias ja instaladas, pulando.
)

echo.
echo [4/4] Executando PyInstaller...
python -m PyInstaller digimon_tcg_lab.spec --noconfirm
if errorlevel 1 goto :error

echo.
echo ============================================
echo   Build concluido: dist\DigimonTCGLab.exe
echo ============================================
pause
goto :eof

:error
echo.
echo Build falhou. Verifique os erros acima.
pause
exit /b 1
