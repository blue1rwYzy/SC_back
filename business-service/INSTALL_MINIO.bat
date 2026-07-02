@echo off
echo 正在安装 MinIO Python 客户端...
call conda activate backendJC
pip install minio
pip install python-dotenv
echo.
echo 安装完成! 请运行此命令手动安装:
echo conda activate backendJC
echo pip install minio python-dotenv
pause
