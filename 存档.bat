@echo off
chcp 65001 >nul
cd /d "%~dp0"

set MSG=%*
if "%MSG%"=="" set MSG=存档

echo.
echo   存档：%MSG%
echo.

git add -A
git -c core.quotepath=false commit -m "%MSG%"
if errorlevel 1 (
  echo   没有改动，跳过提交。
)

echo.
echo   推到 GitHub……
git push -q origin HEAD:main
if errorlevel 1 (
  echo   [注意] 推送失败。可能是断网或 GitHub 抽了。
  echo          本地已经存好了，联网后双击再跑一次就行。
) else (
  echo   已推送。
)

echo.
echo   最近五次存档：
git log --oneline -5

echo.
echo   按任意键关闭。
pause >nul
