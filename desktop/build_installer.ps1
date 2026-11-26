$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$csc = "C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if (-not (Test-Path $csc)) {
    throw "未找到 .NET Framework x64 编译器: $csc"
}

$desktopExe = Join-Path $root "成品\CCTRCloudExportDesktop.exe"
if (-not (Test-Path $desktopExe)) {
    $desktopExe = Join-Path $root "dist\CCTRCloudExportDesktop.exe"
}
if (-not (Test-Path $desktopExe)) {
    throw "请先构建 CCTRCloudExportDesktop.exe"
}

$stage = Join-Path $root "build\installer_stage"
if (Test-Path $stage) {
    Remove-Item -Recurse -Force $stage
}
New-Item -ItemType Directory -Path $stage | Out-Null

$uninstallCs = Join-Path $root "desktop\installer\UninstallApp.cs"
$setupCs = Join-Path $root "desktop\installer\SetupApp.cs"
$uninstallExe = Join-Path $stage "Uninstall.exe"

Write-Host "=== 1/3 编译轻量独立卸载程序 Uninstall.exe ==="
& $csc /nologo /codepage:65001 /optimize+ /platform:x64 /target:winexe /out:$uninstallExe `
    /reference:System.dll /reference:System.Core.dll /reference:System.Drawing.dll /reference:System.Windows.Forms.dll `
    $uninstallCs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "=== 2/3 压缩内嵌完整桌面端与卸载器载荷 ==="
$appGz = Join-Path $stage "app.gz"
$uninstallGz = Join-Path $stage "uninstall.gz"

& (Join-Path $root ".venv\Scripts\python.exe") -c @"
import gzip, shutil, pathlib
def gz_copy(src, dst):
    with open(src, 'rb') as fi, gzip.open(dst, 'wb', compresslevel=6) as fo:
        shutil.copyfileobj(fi, fo, length=1024*1024)
gz_copy(r'$desktopExe', r'$appGz')
gz_copy(r'$uninstallExe', r'$uninstallGz')
print('app.gz MB:', round(pathlib.Path(r'$appGz').stat().st_size / 1048576, 1))
"@
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "=== 3/3 编译一键安装包 CCTRCloudExportSetup.exe ==="
$setupOut = Join-Path $root "成品\CCTRCloudExportSetup.exe"
& $csc /nologo /codepage:65001 /optimize+ /platform:x64 /target:winexe /out:$setupOut `
    /reference:System.dll /reference:System.Core.dll /reference:System.Drawing.dll /reference:System.Windows.Forms.dll /reference:Microsoft.CSharp.dll `
    "/resource:$appGz,app.gz" "/resource:$uninstallGz,uninstall.gz" `
    $setupCs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Get-Item $setupOut | Select-Object Name, Length, LastWriteTime
