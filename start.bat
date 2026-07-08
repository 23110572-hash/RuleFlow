@echo off
REM ============================================================
REM  RuleFlow - one-click launcher
REM  Starts the FastAPI backend + Vite React frontend in their
REM  own windows, then opens the app in Chrome.
REM ============================================================
setlocal
set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "FRONTEND=%ROOT%frontend"

echo ============================================
echo    RuleFlow - Agentic Compliance Platform
echo ============================================
echo.

REM ---- Backend: create venv + install deps on first run ----
if not exist "%BACKEND%\.venv\Scripts\python.exe" (
  echo [setup] Creating Python virtual environment ^(first run^)...
  python -m venv "%BACKEND%\.venv"
  "%BACKEND%\.venv\Scripts\python.exe" -m pip install --upgrade pip
  echo [setup] Installing backend dependencies...
  "%BACKEND%\.venv\Scripts\python.exe" -m pip install -r "%BACKEND%\requirements.txt"
)

REM ---- Backend: ensure a .env exists (defaults to zero-infra SQLite) ----
if not exist "%BACKEND%\.env" (
  if exist "%ROOT%.env.example" (
    echo [setup] Creating backend\.env from .env.example ^(add your GROQ_API_KEY^)...
    copy /y "%ROOT%.env.example" "%BACKEND%\.env" >nul
  )
)

REM ---- Frontend: install node deps on first run ----
if not exist "%FRONTEND%\node_modules" (
  echo [setup] Installing frontend dependencies ^(first run^)...
  pushd "%FRONTEND%"
  call npm install
  popd
)

echo.
echo [start] Launching backend API on http://0.0.0.0:8000 ...
start "RuleFlow API" /D "%BACKEND%" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"

echo [start] Launching frontend on http://localhost:5173 ...
start "RuleFlow Web" /D "%FRONTEND%" cmd /k "npm run dev"

echo [wait] Giving the servers a few seconds to boot...
timeout /t 9 /nobreak >nul

echo [open] Opening RuleFlow in Chrome...
start chrome "http://localhost:5173"
if errorlevel 1 (
  echo [open] Chrome not found - opening in default browser instead.
  start "" "http://localhost:5173"
)

echo.
echo  RuleFlow is running:
echo    Frontend : http://localhost:5173
echo    API docs : http://localhost:8000/docs
echo.
echo  Two server windows opened. Close them to stop RuleFlow.
echo  (Set GROQ_API_KEY in backend\.env to enable document extraction.)
endlocal
