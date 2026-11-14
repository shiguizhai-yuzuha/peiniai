@echo off
chcp 65001 >nul
cd /d "D:\Python学习\演示"
echo ========================================
echo   陪你AI 本地测试
echo   地址：http://127.0.0.1:7864
echo   账号：XIAO2026 / XIAO2026
echo ========================================
echo.
echo 关闭这个窗口就会停止服务
echo.
python -X utf8 app.py
echo.
echo 服务已停止
pause
