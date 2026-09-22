@echo off
rem 재무 대시보드 실행 (서버 매니저/더블클릭용). 포트는 인자로 변경 가능: run.bat 8000
cd /d "%~dp0"
set PORT=%1
if "%PORT%"=="" set PORT=8000
python -m uvicorn app.main:app --host 127.0.0.1 --port %PORT%
