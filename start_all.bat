@echo off
chcp 65001 >nul
REM Start all microservices with conda environment

echo ========================================
echo Highway Defect Detection System - Services Starting
echo ========================================

REM Activate conda environment
echo.
echo [0/3] Activating conda environment: backendJC...
call conda activate backendJC
if %errorlevel% neq 0 (
    echo [ERROR] Failed to activate conda environment: backendJC
    echo Please run: conda activate backendJC
    pause
    exit /b 1
)

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Please install Python 3.8+
    pause
    exit /b 1
)

echo.
echo [1/3] Starting Business Service (Port 8001)...
start "Business Service" cmd /k "conda activate backendJC && cd business-service && python main.py"
timeout /t 3 >nul

echo [2/3] Starting Inference Service (Port 8002)...
start "Inference Service" cmd /k "conda activate backendJC && cd inference-service && python main.py"
timeout /t 3 >nul

echo [3/3] Starting Vehicle Tracking Service (Port 8003)...
start "Vehicle Tracking Service" cmd /k "conda activate backendJC && cd tracking-service && python main.py"
timeout /t 3 >nul

echo All 3 services started successfully!
echo.
echo ========================================
echo Access URLs:
echo   - Business Service: http://localhost:8001/docs
echo   - Inference Service: http://localhost:8002/docs
echo   - Vehicle Tracking Service: http://localhost:8003/docs
echo ========================================
echo.
echo Note: If using Nginx, start Nginx manually and access http://localhost:8000
echo.
pause
