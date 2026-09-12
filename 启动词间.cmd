@echo off
setlocal
cd /d "%~dp0vocab-web"

if not exist "dist\client\index.html" (
  echo Built website is missing. Run npm run build in vocab-web first.
  pause
  exit /b 1
)

netstat -an | findstr /c:"127.0.0.1:8765" | findstr /i "listen" >nul
if not errorlevel 1 (
  start "" "http://127.0.0.1:8765/"
  exit /b 0
)

set PYW=runtime\pythonw.exe
if not exist "%PYW%" (
  where pythonw.exe >nul 2>nul || (
    echo Bundled pythonw.exe is missing and no pythonw.exe was found on PATH.
    pause
    exit /b 1
  )
  set PYW=pythonw.exe
)

start "" "%PYW%" "server.py"

for /l %%i in (1,1,20) do (
  >nul ping -n 2 127.0.0.1
  netstat -an | findstr /c:"127.0.0.1:8765" | findstr /i "listen" >nul
  if not errorlevel 1 (
    start "" "http://127.0.0.1:8765/"
    exit /b 0
  )
)

echo The local service did not start.
echo Close this window and try again.
echo To see the error, run this in the same folder: runtime\python.exe server.py
pause
