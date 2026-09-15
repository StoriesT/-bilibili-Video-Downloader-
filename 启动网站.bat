@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Bilibili 高清下载器
python app.py
echo.
echo 服务已停止。
pause
