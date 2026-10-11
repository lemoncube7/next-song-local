@echo off
setlocal
cd /d "%~dp0"
set "KARAOKE_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%KARAOKE_PYTHON%" goto bundled
where py >nul 2>nul
if not errorlevel 1 goto launcher
where python >nul 2>nul
if not errorlevel 1 goto systempython
echo Python 3.10 or newer is required.
pause
exit /b 1
:bundled
"%KARAOKE_PYTHON%" -X utf8 launch.py
goto end
:launcher
py -3 -X utf8 launch.py
goto end
:systempython
python -X utf8 launch.py
:end
if errorlevel 1 pause
endlocal
