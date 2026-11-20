@echo off
rem stop.bat -- free the four ports this stack uses (1883 8080 8081 8082).
rem Kills whatever python process is listening on them; run start.bat again after.
echo stopping tap-probe stack ...
for %%P in (8081 8082 8080 1883) do (
  for /f "tokens=5" %%a in ('netstat -ano ^| findstr /r /c:":%%P .*LISTENING"') do (
    echo   port %%P  pid %%a
    taskkill /f /pid %%a >nul 2>nul
  )
)
echo done.
%SystemRoot%\System32\timeout.exe /t 2 /nobreak >nul
