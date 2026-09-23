@echo off
rem 공개 페이지(GitHub Pages) 스냅샷 갱신: docs/ 내보내기 -> commit -> push
cd /d "%~dp0"
python -m app.publish %*
pause
