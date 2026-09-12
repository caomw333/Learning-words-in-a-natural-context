@echo off
cd /d "%~dp0"

echo.
echo  ==========================================
echo    词间 · 本地四级阅读练习室
echo    http://127.0.0.1:8765
echo  ==========================================
echo.

rem ========== 1. 定位 Python ==========
set "PYEXE="
if exist "runtime\python.exe" set "PYEXE=runtime\python.exe"
if defined PYEXE goto pychk
where py >nul 2>nul
if not errorlevel 1 set "PYEXE=py"
if defined PYEXE goto pychk
where python >nul 2>nul
if not errorlevel 1 set "PYEXE=python"

:pychk
if not defined PYEXE goto nopy
%PYEXE% -c "import sys" >nul 2>nul
if errorlevel 1 goto nopy
goto pyok

:nopy
echo  [错误] 没有找到可用的 Python。
echo.
echo         任选一种解决办法：
echo         1. 安装 Python 3，安装时务必勾选 "Add python.exe to PATH"
echo            https://www.python.org/downloads/
echo         2. 改用免安装版（自带 Python，不需要装任何环境）
echo            见 GitHub 仓库的 Releases 页面
echo.
pause
exit /b 1

:pyok
echo  [Python] 使用 %PYEXE%
echo.

rem ========== 2. 前端界面缺失时自动构建 ==========
if exist "dist\client\index.html" goto run

echo  [提示] 尚未构建前端界面，需要先构建一次。
echo.

where npm >nul 2>nul
if errorlevel 1 goto nonpm
if exist "node_modules" goto build

echo  [1/2] 安装依赖，首次可能要几分钟...
call npm install
if errorlevel 1 goto npmfail

:build
echo  [2/2] 构建前端界面...
call npm run build
if errorlevel 1 goto buildfail
echo.
echo  [完成] 构建成功。
echo.
goto run

:nonpm
echo  [错误] 构建需要 Node.js 22 或更高版本，但没有找到 npm。
echo         下载: https://nodejs.org/
echo         或者改用免安装版，无需 Node。
echo.
pause
exit /b 1

:npmfail
echo.
echo  [错误] 依赖安装失败，请检查网络后重试。
echo.
pause
exit /b 1

:buildfail
echo.
echo  [错误] 构建失败，请把上面的报错发给我。
echo.
pause
exit /b 1

rem ========== 3. 启动本地服务 ==========
:run
echo  正在启动本地服务，浏览器会自动打开...
echo  关闭本窗口不会停止服务；要停止请用任务管理器结束 python.exe。
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
