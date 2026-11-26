# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

datas = [('cctr_export/ui/web', 'cctr_export/ui/web')]
binaries = []
hiddenimports = ['socksio', 'certifi', 'sqlite3', 'ctypes.wintypes']

for pkg in ('ddddocr', 'onnxruntime', 'socksio', 'certifi'):
    tmp_datas, tmp_bins, tmp_hidden = collect_all(pkg)
    datas += tmp_datas
    binaries += tmp_bins
    hiddenimports += tmp_hidden

# 显式打包独立完整的 VC++ 2022 运行时 DLL（与 PySide6 6.12 / ONNX Runtime 版本严格一致）
# 防止在未安装 VC++ Redistributable 的目标电脑上因缺失 msvcp140_1 / concrt140 / d3dcompiler_47 而报错，
# 并避免打包宿主机 JDK/mise 目录下过旧或冲突的 ucrtbase.dll / msvcp140.dll。
_runtime_dll_names = (
    'concrt140.dll',
    'msvcp140.dll',
    'msvcp140_1.dll',
    'msvcp140_2.dll',
    'msvcp140_codecvt_ids.dll',
    'vccorlib140.dll',
    'vcruntime140.dll',
    'vcruntime140_1.dll',
)
try:
    import PySide6

    _pyside_dir = Path(PySide6.__file__).resolve().parent
    for _dll_name in _runtime_dll_names:
        _src = _pyside_dir / _dll_name
        if _src.is_file():
            binaries.append((str(_src), '.'))
            if _dll_name in ('msvcp140.dll', 'msvcp140_1.dll', 'vcruntime140.dll', 'vcruntime140_1.dll'):
                binaries.append((str(_src), 'onnxruntime/capi'))
except Exception:
    pass

_d3d = Path(r'C:\Windows\System32\d3dcompiler_47.dll')
if _d3d.is_file():
    binaries.append((str(_d3d), '.'))

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'unittest',
        'pypdf',
        'pikepdf',
        'PySide6.Qt3DAnimation',
        'PySide6.Qt3DCore',
        'PySide6.Qt3DExtras',
        'PySide6.Qt3DInput',
        'PySide6.Qt3DLogic',
        'PySide6.Qt3DRender',
        'PySide6.QtCharts',
        'PySide6.QtDataVisualization',
        'PySide6.QtGraphs',
        'PySide6.QtGraphsWidgets',
        'PySide6.QtQuick3D',
        'PySide6.QtSensors',
        'PySide6.QtSpatialAudio',
        'PySide6.QtLocation',
        'PySide6.QtPdf',
        'PySide6.QtPdfWidgets',
    ],
    noarchive=False,
    optimize=0,
)

# 过滤宿主机 mise/Java/Anaconda 混入的 ucrtbase / api-ms-win-* / 旧版 CRT DLL
_managed_runtime_lower = set(_runtime_dll_names) | {'d3dcompiler_47.dll'}
_filtered_binaries = []
_seen_dests = set()
for _dest, _src, _typecode in a.binaries:
    _dest_norm = str(_dest).replace('\\', '/').lower()
    _src_norm = str(_src).replace('\\', '/').lower()
    _base = Path(_dest_norm).name

    # 绝不打包 Java/mise 中的 UCRT 与 API-Set forwarder；Win10/11 原生系统自带 UCRT
    if _base == 'ucrtbase.dll' or _base.startswith('api-ms-win-crt-') or _base.startswith('api-ms-win-core-'):
        continue
    if any(bad in _src_norm for bad in ('/mise/installs/java', '/jdk', '/jre', '/anaconda', '/miniconda')):
        continue
    # 根目录及 onnxruntime/capi 的 VC++ 运行时仅保留 PySide6 同一套一致版本
    if _base in _managed_runtime_lower and ('/' not in _dest_norm or _dest_norm.startswith('onnxruntime/capi/')):
        if '/pyside6/' not in _src_norm and _base != 'd3dcompiler_47.dll':
            continue
    if _dest_norm in _seen_dests:
        continue
    _seen_dests.add(_dest_norm)
    _filtered_binaries.append((_dest, _src, _typecode))

a.binaries = _filtered_binaries

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='CCTRCloudExportDesktop',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
