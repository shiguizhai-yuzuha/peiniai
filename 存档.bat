@echo off
chcp 65001 >nul
cd /d "%~dp0"

set MSG=%*
if "%MSG%"=="" set MSG=存档

echo.
echo   正在存档：%MSG%
echo.

git add -A
git -c core.quotepath=false commit -m "%MSG%"
if errorlevel 1 (
  echo.
  echo   没有改动，或者提交失败。
) else (
  echo.
  echo   已存档。
)

echo.
echo   最近五次存档：
git log --oneline -5

echo.
echo   按任意键关闭窗口。
pause >nul
