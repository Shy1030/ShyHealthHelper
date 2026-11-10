@echo off
setlocal
cd /d "%~dp0"

set "TOOLS=%~dp0..\..\2\tools"
set "JAVA_HOME=%TOOLS%\jdk"
set "ANDROID_HOME=%TOOLS%\android-sdk"
set "ANDROID_SDK_ROOT=%ANDROID_HOME%"
set "GRADLE_USER_HOME=%TOOLS%\gradle-home"

if not exist "%JAVA_HOME%\bin\java.exe" (
  echo [ShyHealthHelper] 未找到本地 JDK，请检查 %JAVA_HOME%
  pause
  exit /b 1
)
if not exist "%ANDROID_HOME%\platforms\android-35" (
  echo [ShyHealthHelper] 未找到 Android SDK，请检查 %ANDROID_HOME%
  pause
  exit /b 1
)

call "%TOOLS%\gradle\bin\gradle.bat" assembleDebug --no-daemon
if errorlevel 1 (
  echo [ShyHealthHelper] 构建失败
  pause
  exit /b 1
)

copy /y "app\build\outputs\apk\debug\app-debug.apk" "ShyHealthHelper-debug.apk" >nul
echo.
echo [ShyHealthHelper] APK 已生成: %~dp0ShyHealthHelper-debug.apk
pause
