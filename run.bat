$batContent = @"
@echo off
title Studio AI Passport Maker
echo ---------------------------------------
echo [1/3] Activating AI Environment...
set PATH=%CD%\passport_env\Scripts;%PATH%

echo [2/3] Starting Backend Server...
:: pythonw use karne se peeche kaala box nahi rahega
start "" ".\passport_env\Scripts\pythonw.exe" server.py

echo [3/3] Opening Browser...
timeout /t 4 /nobreak > nul
start http://127.0.0.1:5000

echo ---------------------------------------
echo Done! App is running at http://127.0.0.1:5000
echo You can close this window now.
pause
"@

$batContent | Out-File -FilePath "Run_StudioAI.bat" -Encoding ascii
echo "Success! Run_StudioAI.bat has been created."