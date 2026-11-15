@echo off
REM 单文件便携版构建脚本
REM 前置：将官方原版 CCTRCloudExportRust-v3.exe 与 WebView2Loader.dll 放到仓库根目录
REM 产物：portable\dist\CCTRCloudExportPortable.exe

python -m pip install -r "%~dp0requirements-build.txt"

python -m PyInstaller --onefile --noconfirm --name CCTRCloudExportPortable ^
  --add-binary "%~dp0..\CCTRCloudExportRust-v3.exe;." ^
  --add-binary "%~dp0..\WebView2Loader.dll;." ^
  --collect-all ddddocr ^
  --collect-all onnxruntime ^
  --hidden-import websocket ^
  "%~dp0launcher_portable.py"

echo.
echo 产物: %~dp0dist\CCTRCloudExportPortable.exe
