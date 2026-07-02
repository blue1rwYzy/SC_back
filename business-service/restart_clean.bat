@echo off
echo ============================================================
echo 清除 Python 缓存并重启服务
echo ============================================================

echo.
echo 1. 停止现有服务 (请手动 Ctrl+C)
echo.
pause

echo.
echo 2. 清除 __pycache__ 目录...
for /d /r . %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d"

echo.
echo 3. 清除 .pyc 文件...
del /s /q *.pyc 2>nul

echo.
echo 4. 清除 .pyo 文件...
del /s /q *.pyo 2>nul

echo.
echo ✅ 缓存清除完成！
echo.
echo 5. 启动服务...
python main.py
