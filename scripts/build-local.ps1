param([switch]$SkipAndroid,[switch]$SkipWindows)
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $root
function Need($name,$help) { if (-not (Get-Command $name -ErrorAction SilentlyContinue)) { throw "$name is missing. $help" } }
Write-Host "VICORA LOCAL TEST BUILDER - no GitHub Actions or paid hosting" -ForegroundColor Cyan
if (-not $SkipAndroid) {
  Need java "Install JDK 17."
  Need gradle "Install Gradle 8.11.1 and add it to PATH."
  if (-not $env:ANDROID_HOME) { throw "Set ANDROID_HOME to your Android SDK folder." }
  if ((& java -version 2>&1 | Out-String) -notmatch 'version "17') { throw "JDK 17 is required." }
  if ((& gradle --version 2>&1 | Out-String) -notmatch 'Gradle 8\.11\.1') { throw "Gradle 8.11.1 is required." }
  foreach ($p in @("platforms\android-35","build-tools\35.0.0")) { if (-not (Test-Path (Join-Path $env:ANDROID_HOME $p))) { throw "Install Android SDK $p using Android Studio SDK Manager." } }
  Push-Location (Join-Path $root "android")
  try { & gradle --no-daemon assembleAdminDebug assembleExaminationDebug; if ($LASTEXITCODE -ne 0) { throw "Android build failed." } } finally { Pop-Location }
}
if (-not $SkipWindows) {
  Need py "Install Python 3.11 and Python Launcher."
  Need node "Install Node.js 22 LTS."
  Need npm "Install Node.js 22 LTS."
  if ((& py -3.11 --version 2>&1 | Out-String) -notmatch "Python 3\.11") { throw "Python 3.11 is required." }
  if ((& node --version).Trim() -notmatch '^v22\.') { throw "Node.js 22 is required." }
  $venv = Join-Path $root ".venv-vicora-build"
  if (-not (Test-Path (Join-Path $venv "Scripts\python.exe"))) { & py -3.11 -m venv $venv; if ($LASTEXITCODE -ne 0) { throw "Could not create Python environment." } }
  $python = Join-Path $venv "Scripts\python.exe"
  $env:PATH = (Join-Path $venv "Scripts") + ";" + $env:PATH
  & $python -m pip install --upgrade pip; if ($LASTEXITCODE -ne 0) { throw "pip setup failed." }
  & $python -m pip install -r requirements.txt; if ($LASTEXITCODE -ne 0) { throw "Python dependencies failed." }
  & $python -m pip check; if ($LASTEXITCODE -ne 0) { throw "Python dependency check failed." }
  & npm install --no-audit --no-fund; if ($LASTEXITCODE -ne 0) { throw "npm install failed." }
  & npm run check; if ($LASTEXITCODE -ne 0) { throw "Examination JS check failed." }
  & npm run check:admin; if ($LASTEXITCODE -ne 0) { throw "Admin JS check failed." }
  & cmd.exe /c build.bat; if ($LASTEXITCODE -ne 0) { throw "Support utilities build failed." }
  & $python -m PyInstaller --noconfirm --clean --onefile --windowed --name VICORA-CBT-Server --add-data "web;web" --collect-all flask --collect-all werkzeug --collect-all waitress --collect-all openpyxl --collect-all docx windows_host.py
  if ($LASTEXITCODE -ne 0) { throw "Windows Host build failed." }
  & npm run dist:win; if ($LASTEXITCODE -ne 0) { throw "Examination desktop build failed." }
  & npm run dist:admin:win; if ($LASTEXITCODE -ne 0) { throw "Admin desktop build failed." }
  $pf86 = [Environment]::GetFolderPath("ProgramFilesX86")
  $iscc = Join-Path $pf86 "Inno Setup 6\ISCC.exe"
  if (-not (Test-Path $iscc)) { throw "Install Inno Setup 6 from https://jrsoftware.org/isdl.php to create installer EXEs." }
  foreach ($iss in @("installer\GTMC-CBT-Admin-Fresh-Installation.iss","installer\GTMC-CBT-Examination-Fresh-Installation.iss","installer\GTMC-CBT-Complete-Update.iss")) {
    & $iscc $iss; if ($LASTEXITCODE -ne 0) { throw "Installer build failed: $iss" }
  }
}
$out = Join-Path $root "local-test-builds"
New-Item -ItemType Directory -Force $out | Out-Null
if (-not $SkipAndroid) {
  Copy-Item "android\app\build\outputs\apk\admin\debug\app-admin-debug.apk" (Join-Path $out "VICORA-CBT-Admin-Android-TEST.apk") -Force
  Copy-Item "android\app\build\outputs\apk\examination\debug\app-examination-debug.apk" (Join-Path $out "VICORA-CBT-Examination-Android-TEST.apk") -Force
}
if (-not $SkipWindows) {
  foreach ($f in @("dist-electron\VICORA-CBT-Examination-1.0.0-Windows.exe","dist-admin-electron\VICORA-CBT-Admin-1.0.0-Windows.exe","dist-installer\VICORA-CBT-Admin-Fresh-Installation-Windows.exe","dist-installer\VICORA-CBT-Examination-Fresh-Installation-Windows.exe","dist-installer\VICORA-CBT-Complete-Update-Windows.exe","dist\VICORA-CBT-Server.exe")) {
    if (Test-Path $f) { Copy-Item $f $out -Force }
  }
}
Write-Host "BUILD COMPLETE. Test files: $out" -ForegroundColor Green
Write-Host "Android APKs are debug test builds, not signed production releases."
Write-Host "Nothing was installed on your phone or PC automatically."
