@echo off
chcp 65001 >nul
title Business Service - Port 8001

echo Starting Business Service...
echo.

call conda activate backendJC
cd /d G:\ShuangChuang\ShuangC\backend\business-service
python main.py

pause
