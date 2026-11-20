@echo off
rem start.bat -- one-click launcher for the tap-probe demo stack.
rem   1. broker.py    tcp/1883 (board + analyzer) + ws/8080 (browser)
rem   2. analyzer.py  http/8082  feature extraction + grading API
rem   3. http.server  http/8081  serves dashboard.html
rem   4. browser      http://localhost:8081/dashboard.html
rem Keep the three windows open. Ctrl+C in each (or run stop.bat) to shut down.
title tap-probe stack
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo [X] Python was not found in PATH. Install Python 3.10+ and tick "Add to PATH".
  echo     https://www.python.org/downloads/windows/
  pause
  exit /b 1
)

echo [1/5] checking Python packages ...
python -c "import paho.mqtt, amqtt, numpy" >nul 2>nul
if errorlevel 1 (
  echo       installing requirements ^(needs internet once^) ...
  if exist "%~dp0wheels" (
    python -m pip install --disable-pip-version-check --no-index --find-links "%~dp0wheels" -r requirements.txt
  ) else (
    python -m pip install --disable-pip-version-check -r requirements.txt
  )
  if errorlevel 1 (
    echo [X] pip install failed. Copy this folder to a machine with internet, run:
    echo       python -m pip download -d wheels -r requirements.txt
    echo     then carry the "wheels" folder along and run start.bat again.
    pause
    exit /b 1
  )
)

echo [2/5] broker      tcp/1883  ws/8080 ...
start "tap-probe broker" cmd /k python broker.py --host 0.0.0.0 --tcp-port 1883 --ws-port 8080
%SystemRoot%\System32\timeout.exe /t 3 /nobreak >nul

echo [3/5] analyzer    http/8082 ...
start "tap-probe analyzer" cmd /k python analyzer.py --broker 127.0.0.1 --broker-port 1883 --http-port 8082 --template "%~dp006_analyze_tap.py"
%SystemRoot%\System32\timeout.exe /t 4 /nobreak >nul

echo [4/5] dashboard   http/8081 ...
rem no --directory here: the batch already cd'ed into this folder, and a path
rem ending in a backslash would leak a quote into argv.
start "tap-probe dashboard" cmd /k python -m http.server 8081 --bind 0.0.0.0
%SystemRoot%\System32\timeout.exe /t 2 /nobreak >nul

echo [5/5] opening browser ...
start "" "http://localhost:8081/dashboard.html"

echo.
echo ==================================================================
echo   This PC, as seen from the board (type this into the joystick menu
echo   MQTT page, item BROKER URI):
python "%~dp0ip.py"
echo ==================================================================
echo.
echo   Nothing on the page? Windows Firewall is probably blocking python.
echo   Allow it for Private networks, or run in an ADMIN window:
echo     netsh advfirewall firewall add rule name="tap-probe" dir=in action=allow protocol=TCP localport=1883,8080,8081,8082
echo.
echo   No board handy? Publish synthetic taps in another window:
echo     python simulator.py --mode alternate
echo.
pause
