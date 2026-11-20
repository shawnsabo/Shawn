@echo off
REM 统一桌面版单文件打包脚本（PySide6 + WebEngine 无损 A4 PDF + ddddocr 自动识别验证码）
REM 产物：dist\CCTRCloudExportDesktop.exe

python -m pip install -r "%~dp0..\requirements.txt" pyinstaller

python -m PyInstaller --onefile --noconsole --noconfirm --name CCTRCloudExportDesktop ^
  --paths "%~dp0.." ^
  --add-data "%~dp0..\cctr_export\ui\web;cctr_export\ui\web" ^
  --collect-all ddddocr ^
  --collect-all onnxruntime ^
  "%~dp0..\main.py"

if not exist "%~dp0..\成品" mkdir "%~dp0..\成品"
copy /Y "%~dp0..\dist\CCTRCloudExportDesktop.exe" "%~dp0..\成品\CCTRCloudExportDesktop.exe" >nul

echo.
echo 产物: %~dp0..\成品\CCTRCloudExportDesktop.exe
