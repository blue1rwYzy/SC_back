@echo off
REM 初始化数据库脚本
REM PostgreSQL 路径: G:\ShuangChuang\ShuangC\postgresql
REM 端口: 5432
REM 密码: mm

echo ======================================
echo 初始化高速公路缺陷检测系统数据库
echo ======================================

SET PGPASSWORD=mm
SET PGPATH=G:\ShuangChuang\ShuangC\postgresql\bin

echo.
echo 正在创建数据库和表结构...
"%PGPATH%\psql.exe" -U postgres -h localhost -p 5432 -f database_init.sql

echo.
echo ======================================
echo 数据库初始化完成！
echo ======================================
pause
