@echo off
chcp 65001 >nul
setlocal
echo === 安装/同步桌面版依赖（含 SOCKS5 与完整运行时组件） ===
.\.venv\Scripts\python.exe -m pip install -r requirements.txt pyinstaller

echo === 清理宿主 PATH 干扰后打包纯净单文件桌面端 (PyInstaller Spec) ===
set "PATH=C:\Windows\System32;C:\Windows;C:\Windows\System32\Wbem;C:\Windows\System32\WindowsPowerShell\v1.0"
.\.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm CCTRCloudExportDesktop.spec

if exist dist\CCTRCloudExportDesktop.exe (
    copy /Y dist\CCTRCloudExportDesktop.exe 成品\CCTRCloudExportDesktop.exe >nul
    echo 打包完成: 成品\CCTRCloudExportDesktop.exe
) else (
    echo 打包失败: 未生成 dist\CCTRCloudExportDesktop.exe
    exit /b 1
)
