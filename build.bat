@echo off
setlocal
cd /d "%~dp0"
echo ==========================================
echo   GTMC CBT - Electron Desktop Build
echo ==========================================

python -m pip install --upgrade pip
if errorlevel 1 goto :failed
python -m pip install -r requirements.txt
if errorlevel 1 goto :failed
python -m pip check
if errorlevel 1 goto :failed

if not exist dist mkdir dist
echo Building Admin diagnostic utility...
python -m PyInstaller --noconfirm --clean --onefile --console --name CBTAdmin-Diagnostic diagnostics.py
if errorlevel 1 goto :failed

echo Building Examination diagnostic utility...
python -m PyInstaller --noconfirm --clean --onefile --console --name CBTExamination-Diagnostic diagnostics.py
if errorlevel 1 goto :failed

echo Building separate Restore utility...
python -m PyInstaller --noconfirm --clean --onefile --console --name CBTRestore restore_backup.py
if errorlevel 1 goto :failed

powershell -NoProfile -ExecutionPolicy Bypass -Command "$files = @('CBTAdmin-Diagnostic.exe','CBTExamination-Diagnostic.exe','CBTRestore.exe'); foreach ($name in $files) { $path = Join-Path 'dist' $name; if (!(Test-Path $path)) { Write-Error ('Missing support build output: ' + $name); exit 1 }; if ((Get-Item $path).Length -lt 1048576) { Write-Error ('Support build output is unexpectedly small: ' + $name); exit 1 } }"
if errorlevel 1 goto :failed

echo SUCCESS: Diagnostics and Restore support utilities built. Admin and Examination are built with Electron separately.
exit /b 0
:failed
echo ERROR: Windows support utility build failed. Review the error above.
exit /b 1
