@echo off
REM 安装 Python 依赖

echo ========================================
echo 安装 Python 依赖包
echo ========================================

echo.
echo 正在安装依赖，这可能需要几分钟...
echo.

pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

if %errorlevel% neq 0 (
    echo.
    echo [错误] 依赖安装失败！
    pause
    exit /b 1
)

echo.
echo ========================================
echo ✅ 依赖安装完成！
echo ========================================
echo.
echo 下一步:
echo   1. 运行 config\init_database.bat 初始化数据库
echo   2. 运行 start_all.bat 启动服务
echo.
pause
