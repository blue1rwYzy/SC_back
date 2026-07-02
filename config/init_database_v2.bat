@echo off
REM 初始化数据库脚本 V2（使用 Python）
REM 避免 SQL 编码问题

echo ======================================
echo 初始化高速公路缺陷检测系统数据库
echo ======================================

echo.
echo 使用 Python 脚本初始化数据库...
echo.

cd %~dp0
python init_db.py

if %errorlevel% neq 0 (
    echo.
    echo [错误] 数据库初始化失败！
    pause
    exit /b 1
)

echo.
echo ======================================
echo 数据库初始化完成！
echo ======================================
pause
