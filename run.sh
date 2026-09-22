#!/usr/bin/env sh
# 재무 대시보드 실행. 포트는 인자로 변경 가능: ./run.sh 8000
cd "$(dirname "$0")"
exec python3 -m uvicorn app.main:app --host 127.0.0.1 --port "${1:-8000}"
