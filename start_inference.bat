@echo off
chcp 65001 >nul
title Inference Service - Port 8002

echo Starting Inference Service...
echo.

call conda activate backendJC
cd /d G:\ShuangChuang\ShuangC\backend\inference-service
python main.py

pause
