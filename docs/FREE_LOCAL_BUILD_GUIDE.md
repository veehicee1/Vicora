# VICORA free local test build (Windows)

This builds VICORA on your own PC. It does not use GitHub Actions, paid hosting, a payment card, or production deployment.

## 1. Download the source
While signed in to the GitHub account with access, download the private repository ZIP from:
https://github.com/veehicee1/Vicora
Extract it to a folder such as C:\VICORA\Vicora. Open PowerShell in that folder (the folder containing app.py and package.json).

## 2. Install these free tools
- Python 3.11, with Python Launcher enabled.
- Node.js 22 LTS.
- JDK 17.
- Android Studio. In Android Studio > SDK Manager, install Android SDK Platform 35 and Build-Tools 35.0.0.
- Gradle 8.11.1, with its bin folder added to PATH.
- Inno Setup 6, required for the Windows installer packages: https://jrsoftware.org/isdl.php

Set ANDROID_HOME to your Android SDK folder. Common location: %LOCALAPPDATA%\Android\Sdk. Close and reopen PowerShell after installing the tools.

## 3. Run the build
From the repository root, run these commands:

    Set-ExecutionPolicy -Scope Process Bypass
    .\scripts\build-local.ps1

The first run downloads dependencies and may take some time. It needs internet access for the initial setup.

Android only:

    .\scripts\build-local.ps1 -SkipWindows

Windows only:

    .\scripts\build-local.ps1 -SkipAndroid

## 4. Find the test files
The script places files in local-test-builds:
- VICORA-CBT-Admin-Android-TEST.apk
- VICORA-CBT-Examination-Android-TEST.apk
- VICORA-CBT-Admin-1.0.0-Windows.exe
- VICORA-CBT-Examination-1.0.0-Windows.exe
- Separate Windows installation packages
- VICORA-CBT-Server.exe

Android APKs are debug builds for testing, not signed production releases. Windows files are test builds, not signed releases.

## 5. Test
Android: copy both APKs to your phone, install Admin and Examination separately, and check their app names and VICORA icons.
Windows: run the Admin EXE and Examination EXE separately. Test the installer packages if you want to check their Start Menu and desktop shortcuts.

Use a disposable test school and sample records for first tests. Keep existing GTMC production databases and backups untouched.

## Important
- Builds use your PC, internet connection, CPU and memory, not paid GitHub build minutes.
- Initial setup may download several gigabytes of SDKs and dependencies.
- Do not share signing keys, passwords, .env files, student data, or database files.
- This does not deploy to Vercel or any public server.
- Nothing is installed on your devices automatically.
