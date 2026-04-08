@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_PATH=%SCRIPT_DIR%speech2text.py"
set "PYTHONUTF8=1"

if defined S2T_PYTHON_EXE (
  set "PYTHON_EXE=%S2T_PYTHON_EXE%"
) else if exist "F:\DevTools\Python311\python.exe" (
  set "PYTHON_EXE=F:\DevTools\Python311\python.exe"
) else (
  set "PYTHON_EXE=python"
)

"%PYTHON_EXE%" "%SCRIPT_PATH%" %*
exit /b %ERRORLEVEL%
