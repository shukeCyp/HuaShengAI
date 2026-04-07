@echo off
setlocal EnableExtensions

set "PROJECT_ROOT=%~dp0"
if "%PROJECT_ROOT:~-1%"=="\" set "PROJECT_ROOT=%PROJECT_ROOT:~0,-1%"

if not defined FRONTEND_DIR set "FRONTEND_DIR=%PROJECT_ROOT%\frontend"
if not defined FRONTEND_BUILD_DIR set "FRONTEND_BUILD_DIR=%FRONTEND_DIR%\dist"
if not defined WEB_DIST_DIR set "WEB_DIST_DIR=%PROJECT_ROOT%\app\web_dist"
if not defined PLAYWRIGHT_BROWSERS_PATH set "PLAYWRIGHT_BROWSERS_PATH=%PROJECT_ROOT%\playwright-browsers"
set "PYINSTALLER_WORKPATH=%PROJECT_ROOT%\build\pyinstaller"

call :ensure_uv || exit /b 1
call :require_cmd npm || exit /b 1
call :ensure_directory_target "%PROJECT_ROOT%\build" "build" || exit /b 1
call :ensure_directory_target "%PROJECT_ROOT%\dist" "dist" || exit /b 1

echo =^=> Sync Python dependencies with uv
call :run_uv sync
if errorlevel 1 exit /b %errorlevel%

echo =^=> Install frontend dependencies
call npm --prefix "%FRONTEND_DIR%" ci
if errorlevel 1 exit /b %errorlevel%

echo =^=> Build Vue frontend
call npm --prefix "%FRONTEND_DIR%" run build
if errorlevel 1 exit /b %errorlevel%

echo =^=> Copy built assets into "%WEB_DIST_DIR%"
if exist "%WEB_DIST_DIR%" rmdir /s /q "%WEB_DIST_DIR%"
mkdir "%WEB_DIST_DIR%"
if errorlevel 1 exit /b %errorlevel%
xcopy "%FRONTEND_BUILD_DIR%\*" "%WEB_DIST_DIR%\" /E /I /Y >nul
if errorlevel 1 exit /b %errorlevel%

echo =^=> Install Playwright Chromium into "%PLAYWRIGHT_BROWSERS_PATH%"
call :run_uv run python -m playwright install chromium
if errorlevel 1 exit /b %errorlevel%

echo =^=> Build desktop bundle with PyInstaller
call :run_uv run --with pyinstaller pyinstaller --noconfirm --clean --workpath "%PYINSTALLER_WORKPATH%" "%PROJECT_ROOT%\pyinstaller.spec"
exit /b %errorlevel%

:ensure_uv
call :has_cmd uv
if not errorlevel 1 (
  set "UV_MODE=exe"
  exit /b 0
)

call :resolve_python_launcher || exit /b 1

call %PYTHON_LAUNCHER% -m uv --version >nul 2>nul
if not errorlevel 1 (
  set "UV_MODE=module"
  exit /b 0
)

echo =^=> uv not found, installing with %PYTHON_LAUNCHER% -m pip install --user uv
call %PYTHON_LAUNCHER% -m pip install --user uv
if errorlevel 1 (
  echo Failed to install uv automatically.
  exit /b 1
)

call :has_cmd uv
if not errorlevel 1 (
  set "UV_MODE=exe"
  exit /b 0
)

call %PYTHON_LAUNCHER% -m uv --version >nul 2>nul
if not errorlevel 1 (
  set "UV_MODE=module"
  exit /b 0
)

echo Failed to locate uv after installation.
exit /b 1

:resolve_python_launcher
call :has_cmd py
if not errorlevel 1 (
  set "PYTHON_LAUNCHER=py"
  exit /b 0
)

call :has_cmd python
if not errorlevel 1 (
  set "PYTHON_LAUNCHER=python"
  exit /b 0
)

echo Missing command: py or python
exit /b 1

:run_uv
if /i "%UV_MODE%"=="exe" (
  call uv %*
) else (
  call %PYTHON_LAUNCHER% -m uv %*
)
exit /b %errorlevel%

:has_cmd
where "%~1" >nul 2>nul
exit /b %errorlevel%

:ensure_directory_target
if exist "%~1" (
  if exist "%~1\\" exit /b 0
  echo Path conflict: %~2 exists as a file, not a directory.
  echo Please remove "%~1" and run build_exe.bat again.
  exit /b 1
)
mkdir "%~1"
if errorlevel 1 exit /b %errorlevel%
exit /b 0

:require_cmd
call :has_cmd %1
if errorlevel 1 (
  echo Missing command: %~1
  exit /b 1
)
exit /b 0
