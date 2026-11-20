@echo off
rem start_demo.bat -- bring the local MQTT + analysis demo stack up on this machine.
rem
rem   1. broker.py     MQTT broker: tcp://0.0.0.0:1883 (the ESP32 / simulator)
rem                    and ws://0.0.0.0:8080/mqtt (the browser raw stream)
rem   2. analyzer.py   subscription + feature extraction + HTTP/WebSocket :8082
rem                    (feature maths comes from 06_analyze_tap.py at repo root)
rem   3. http.server   serves dashboard.html on port 8081
rem   4. browser       opens http://localhost:8081/dashboard.html
rem
rem Keep this window open while the demo is running.  Ctrl+C stops the stack.
rem The dashboard shows two independent links:
rem   raw stream    MQTT over WebSocket, port 8080 (measurement frames, JSON)
rem   analysis      WebSocket, port 8082 (feature vector + BONDED/DEBOND verdict)

title tap-probe demo launcher
cd /d "%~dp0"

echo [1/4] starting broker on tcp/1883 and ws/8080 ...
start "tap-probe broker" cmd /k python broker.py
timeout /t 3 /nobreak >nul

echo [2/4] starting analyzer on http/8082 (loads 06_analyze_tap.py) ...
start "tap-probe analyzer" cmd /k python analyzer.py
timeout /t 4 /nobreak >nul

echo [3/4] starting static file server on http/8081 ...
start "tap-probe dashboard" cmd /k python -m http.server 8081 --bind 0.0.0.0
timeout /t 2 /nobreak >nul

echo [4/4] opening the dashboard ...
start "" "http://localhost:8081/dashboard.html"

echo.
echo   dashboard    http://localhost:8081/dashboard.html
echo   analyzer API http://localhost:8082/api/health
echo   broker       tcp://^<this-pc^>:1883   ws://^<this-pc^>:8080/mqtt
echo.
echo   no board?  publish synthetic taps in another window:
echo       python simulator.py --mode alternate
echo.
echo LAN address of this machine:
ipconfig | findstr /i "IPv4"
echo.
pause
