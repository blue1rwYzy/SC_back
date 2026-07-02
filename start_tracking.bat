@echo off
chcp 65001 >nul
title Vehicle Tracking Service - Port 8003

echo Starting Vehicle Tracking Service...
echo.

call conda activate backendJC
cd /d G:\ShuangChuang\ShuangC\backend\tracking-service
python main.py

pause
