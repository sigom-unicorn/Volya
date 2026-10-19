@echo off
chcp 65001 > nul
cd /d "%~dp0"
python -m portal_volya.ui_desktop.run
pause
