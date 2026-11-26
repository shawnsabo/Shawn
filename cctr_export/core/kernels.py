"""浏览器/渲染内核自动检测、自选偏好与自动下载管理"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .http_utils import make_http_client

def _resolve_default_export_dir() -> Path:
    import sys

    if sys.platform == "win32":
        try:
            import ctypes

            buf = ctypes.create_unicode_buffer(260)
            # CSIDL_PERSONAL = 5：兼容 Windows OneDrive 文档重定向或自定义“文档”目录
            if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0 and buf.value:
                return Path(buf.value) / "CCTRExport"
        except Exception:
            pass
    return Path.home() / "Documents" / "CCTRExport"


SETTINGS_FILE = Path.home() / ".cctr_export" / "settings.json"
RUNTIMES_DIR = Path.home() / ".cctr_export" / "runtimes"
DEFAULT_EXPORT_DIR = _resolve_default_export_dir()

KERNEL_LABELS: list[tuple[str, str]] = [
    ("auto", "自动优选（自动检测本地 / 内置内核）"),
    ("edge", "Microsoft Edge（系统内核 / 自动安装）"),
    ("chrome", "Google Chrome（系统内核 / 自动安装）"),
    ("chromium", "便携 Chromium 内核（自动下载 · 免安装）"),
    ("builtin", "内置 QtWebEngine（离线集成内核）"),
]


@dataclass
class KernelInfo:
    kind: str
    name: str
    installed: bool
    path: str = ""
    version: str = ""
    source: str = ""
    can_download: bool = False


def load_settings() -> dict:
    try:
        if SETTINGS_FILE.exists():
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def save_settings(updates: dict) -> dict:
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = load_settings()
    data.update(updates)
    SETTINGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def get_preferred_kernel() -> str:
    val = str(load_settings().get("kernel_mode") or "auto").strip().lower()
    valid = {k for k, _ in KERNEL_LABELS}
    return val if val in valid else "auto"


def set_preferred_kernel(kind: str) -> str:
    k = str(kind or "auto").strip().lower()
    valid = {x for x, _ in KERNEL_LABELS}
    if k not in valid:
        k = "auto"
    save_settings({"kernel_mode": k})
    return k


def get_export_dir() -> Path:
    raw = str(load_settings().get("export_dir") or "").strip()
    candidates = [Path(raw).expanduser()] if raw else []
    candidates.extend([DEFAULT_EXPORT_DIR, Path.home() / "Documents" / "CCTRExport", Path.home() / "CCTRExport"])
    for p in candidates:
        try:
            p.mkdir(parents=True, exist_ok=True)
            return p
        except OSError:
            continue
    fallback = Path.home() / ".cctr_export" / "exports"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def set_export_dir(path: str | Path) -> Path:
    p = Path(path).expanduser().resolve()
    p.mkdir(parents=True, exist_ok=True)
    save_settings({"export_dir": str(p)})
    return p


def cleanup_empty_legacy_output_dirs() -> int:
    """清理旧版遗留在 ~/.cctr_export/output/<id>/ 中的空数字目录。"""
    legacy_root = Path.home() / ".cctr_export" / "output"
    removed = 0
    if not legacy_root.exists():
        return 0
    try:
        for child in legacy_root.iterdir():
            if child.is_dir() and child.name.isdigit():
                try:
                    if not any(child.iterdir()):
                        child.rmdir()
                        removed += 1
                except OSError:
                    pass
    except OSError:
        pass
    return removed


def _read_reg_app_path(exe_name: str) -> Optional[str]:
    if os.name != "nt":
        return None
    try:
        import winreg

        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(root, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe_name}") as k:
                    val, _ = winreg.QueryValueEx(k, "")
                    if val and os.path.isfile(val):
                        return val
            except OSError:
                continue
    except Exception:
        pass
    return None


def _read_version_from_dir(exe_path: str) -> str:
    """不启动浏览器进程，快速从安装目录版本子文件夹或 Windows 注册表读取版本号。"""
    p = Path(exe_path)
    if p.parent.exists():
        for sub in sorted(p.parent.iterdir(), reverse=True):
            if sub.is_dir() and re.match(r"^\d+\.\d+\.\d+(?:\.\d+)?$", sub.name):
                return sub.name
    if p.parent.parent.exists() and re.match(r"^\d+\.\d+\.\d+", p.parent.name):
        return p.parent.name
    if os.name == "nt":
        try:
            import winreg

            low = exe_path.lower()
            reg_keys = []
            if "msedge" in low:
                reg_keys = [
                    (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Edge\BLBeacon"),
                    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Edge\BLBeacon"),
                ]
            elif "chrome" in low:
                reg_keys = [
                    (winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon"),
                    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Google\Chrome\BLBeacon"),
                ]
            for root, subkey in reg_keys:
                try:
                    with winreg.OpenKey(root, subkey) as k:
                        ver, _ = winreg.QueryValueEx(k, "version")
                        if ver:
                            return str(ver)
                except OSError:
                    continue
        except Exception:
            pass
    return "已安装"


def _find_edge_exe() -> Optional[str]:
    candidates = [
        _read_reg_app_path("msedge.exe"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
        shutil.which("msedge"),
        shutil.which("microsoft-edge"),
    ]
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return None


def _find_chrome_exe() -> Optional[str]:
    portable_chrome = _find_portable_exe(RUNTIMES_DIR / "chrome")
    candidates = [
        _read_reg_app_path("chrome.exe"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        shutil.which("chrome"),
        shutil.which("google-chrome"),
        portable_chrome,
    ]
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return None


def _find_portable_exe(base_dir: Path) -> Optional[str]:
    if not base_dir.exists():
        return None
    for target in ("chrome-headless-shell.exe", "chrome.exe"):
        for match in sorted(base_dir.rglob(target)):
            if match.is_file():
                return str(match)
    return None


def _detect_builtin() -> KernelInfo:
    try:
        import PySide6
        from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
        from PySide6.QtWidgets import QApplication

        ver = getattr(PySide6, "__version__", "") or "QtWebEngine"
        # 在独立线程或无 QApplication 时也可识别，实际使用由 exporter 判断是否在 GUI 线程/QApp
        qapp_ok = QApplication.instance() is not None
        note = f"PySide6 {ver}" + ("" if qapp_ok else " (仅界面模式)")
        return KernelInfo("builtin", "内置 QtWebEngine", True, path="builtin://qtwebengine", version=note, source="随包集成", can_download=False)
    except Exception:
        return KernelInfo("builtin", "内置 QtWebEngine", False, version="未安装", source="", can_download=False)


def detect_kernel(kind: str) -> KernelInfo:
    k = (kind or "auto").strip().lower()
    if k == "edge":
        exe = _find_edge_exe()
        if exe:
            return KernelInfo("edge", "Microsoft Edge", True, path=exe, version=_read_version_from_dir(exe), source="系统已安装", can_download=True)
        return KernelInfo("edge", "Microsoft Edge", False, version="未检测到，可自动下载安装", can_download=True)

    if k == "chrome":
        exe = _find_chrome_exe()
        if exe:
            src = "便携安装" if str(RUNTIMES_DIR) in exe else "系统已安装"
            return KernelInfo("chrome", "Google Chrome", True, path=exe, version=_read_version_from_dir(exe), source=src, can_download=True)
        return KernelInfo("chrome", "Google Chrome", False, version="未检测到，可自动下载便携版", can_download=True)

    if k == "chromium":
        exe = _find_portable_exe(RUNTIMES_DIR / "chromium") or shutil.which("chromium")
        if exe and os.path.isfile(exe):
            ver = _read_version_from_dir(exe)
            ver_file = RUNTIMES_DIR / "chromium" / "VERSION.txt"
            if ver_file.exists():
                ver = ver_file.read_text(encoding="utf-8").strip() or ver
            return KernelInfo("chromium", "便携 Chromium", True, path=exe, version=ver, source="本地运行时", can_download=True)
        return KernelInfo("chromium", "便携 Chromium", False, version="未下载（点击可一键下载约 90MB）", can_download=True)

    if k == "builtin":
        return _detect_builtin()

    # auto: 优先系统 Edge -> 系统 Chrome -> 本地便携 Chromium -> 内置 QtWebEngine
    for sub in ("edge", "chrome", "chromium", "builtin"):
        info = detect_kernel(sub)
        if info.installed:
            return info
    return KernelInfo("auto", "未检测到可用内核", False, version="请下载便携 Chromium 或安装 Edge/Chrome", can_download=True)


def detect_all_kernels() -> dict[str, KernelInfo]:
    return {k: detect_kernel(k) for k, _ in KERNEL_LABELS}


def resolve_render_backend(kernel_mode: Optional[str] = None) -> tuple[str, Optional[str], str]:
    """根据用户自选策略解析本次实际渲染后端，返回 (backend_type, binary_path, display_label)。

    backend_type: 'qtwebengine' 或 'cdp'
    """
    mode = (kernel_mode or get_preferred_kernel() or "auto").strip().lower()
    if mode == "builtin":
        b = _detect_builtin()
        if not b.installed:
            raise RuntimeError("当前未安装 PySide6-WebEngine 内置内核，请切换为 Edge / Chrome / 便携 Chromium")
        return "qtwebengine", None, f"内置 QtWebEngine ({b.version})"

    if mode in ("edge", "chrome", "chromium"):
        info = detect_kernel(mode)
        if not info.installed or not info.path:
            raise RuntimeError(f"未检测到 {info.name} 内核，请在左侧栏点击「下载 / 修复内核」或切换其它内核")
        return "cdp", info.path, f"{info.name} {info.version}"

    # auto: 优先本机或已下载 Chromium 家族，再回退 QtWebEngine（均严格执行 A4 边距与完整性校验）
    for sub in ("edge", "chrome", "chromium"):
        info = detect_kernel(sub)
        if info.installed and info.path:
            return "cdp", info.path, f"{info.name} {info.version}"
    b = _detect_builtin()
    if b.installed:
        return "qtwebengine", None, f"内置 QtWebEngine ({b.version})"
    raise RuntimeError("未找到任何可用的 PDF 渲染内核，请在左侧点击「下载便携 Chromium」")


def _fetch_cft_download_url(flavor: str = "chrome-headless-shell") -> tuple[str, list[str]]:
    """查询 Chrome for Testing 最新稳定 win64 版本及候选镜像下载地址。"""
    # 1. 国内高速镜像 npmmirror 优先，失败再用 Google 官方 JSON
    mirrors_meta = [
        "https://registry.npmmirror.com/-/binary/chrome-for-testing/",
        "https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json",
    ]
    with make_http_client(timeout=20.0, prefer_direct=True) as client:
        # 先试 npmmirror 目录索引找最新版本号
        try:
            r = client.get(mirrors_meta[0])
            if r.status_code == 200:
                items = r.json()
                vers = []
                for it in items:
                    name = str(it.get("name") or "").strip("/")
                    if re.match(r"^\d+\.\d+\.\d+\.\d+$", name):
                        vers.append((tuple(int(p) for p in name.split(".")), name))
                if vers:
                    vers.sort()
                    latest_ver = vers[-1][1]
                    pkg = f"{flavor}-win64.zip"
                    urls = [
                        f"https://cdn.npmmirror.com/binaries/chrome-for-testing/{latest_ver}/win64/{pkg}",
                        f"https://storage.googleapis.com/chrome-for-testing-public/{latest_ver}/win64/{pkg}",
                    ]
                    return latest_ver, urls
        except Exception:
            pass

        # 回退到 Google 官方清单
        r = client.get(mirrors_meta[1])
        r.raise_for_status()
        stable = r.json()["channels"]["Stable"]
        ver = stable["version"]
        downloads = stable["downloads"].get(flavor, [])
        urls = [d["url"] for d in downloads if d.get("platform") == "win64" and d.get("url")]
        if not urls:
            raise RuntimeError(f"未找到 win64 平台 {flavor} 下载地址")
        return ver, urls


def download_and_install_kernel(
    kind: str,
    progress_cb: Optional[Callable[[int, str], None]] = None,
) -> KernelInfo:
    """自动检测并在缺失时下载安装指定渲染内核，返回更新后的 KernelInfo。"""
    k = (kind or "chromium").strip().lower()
    if k == "auto":
        existing = detect_kernel("auto")
        if existing.installed:
            return existing
        k = "chromium"

    if k == "builtin":
        return detect_kernel("builtin")

    if k == "edge":
        info = detect_kernel("edge")
        if info.installed:
            return info
        if progress_cb:
            progress_cb(5, "正在下载 Microsoft Edge 安装引导程序...")
        RUNTIMES_DIR.mkdir(parents=True, exist_ok=True)
        installer = RUNTIMES_DIR / "MicrosoftEdgeSetup.exe"
        url = "https://go.microsoft.com/fwlink/?linkid=2108834&Channel=Stable&language=zh-cn"
        with make_http_client(timeout=60.0, prefer_direct=True) as client:
            with client.stream("GET", url) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("content-length") or 0)
                done = 0
                with installer.open("wb") as f:
                    for chunk in resp.iter_bytes(65536):
                        f.write(chunk)
                        done += len(chunk)
                        if total and progress_cb:
                            progress_cb(min(70, int(done * 70 / total)), f"下载 Edge 安装包 {done // 1024} KB")
        if progress_cb:
            progress_cb(75, "正在安装 Microsoft Edge，请稍候...")
        res = subprocess.run([str(installer), "/silent", "/install"], timeout=240)
        if res.returncode != 0:
            subprocess.Popen([str(installer)])
            raise RuntimeError("已下载 Edge 安装程序并启动安装向导，请完成安装后点击「重新检测」")
        updated = detect_kernel("edge")
        if not updated.installed:
            raise RuntimeError("Edge 安装后暂未检测到路径，请稍后重试检测")
        if progress_cb:
            progress_cb(100, f"✓ Microsoft Edge {updated.version} 就绪")
        return updated

    if k in ("chromium", "chrome"):
        # chrome 与 chromium 均支持下载官方免安装 Chrome for Testing 运行时，避免管理员权限弹窗
        flavor = "chrome" if k == "chrome" else "chrome-headless-shell"
        target_dir = RUNTIMES_DIR / ("chrome" if k == "chrome" else "chromium")
        if progress_cb:
            progress_cb(2, f"正在查询最新稳定版 {flavor} 内核...")
        ver, urls = _fetch_cft_download_url(flavor)
        tmp_zip = Path(tempfile.mkstemp(suffix=".zip", prefix="cctr_kernel_")[1])
        last_err: Optional[Exception] = None
        downloaded = False
        try:
            for url in urls:
                try:
                    if progress_cb:
                        host = url.split("/")[2]
                        progress_cb(5, f"正在从 {host} 下载 v{ver}...")
                    with make_http_client(timeout=180.0, prefer_direct=True) as client:
                        with client.stream("GET", url) as resp:
                            resp.raise_for_status()
                            total = int(resp.headers.get("content-length") or 0)
                            done = 0
                            with tmp_zip.open("wb") as f:
                                for chunk in resp.iter_bytes(131072):
                                    f.write(chunk)
                                    done += len(chunk)
                                    if total and progress_cb:
                                        pct = 5 + int(done * 80 / total)
                                        progress_cb(min(85, pct), f"下载内核 v{ver}: {done / 1048576:.1f} / {total / 1048576:.1f} MB")
                    downloaded = True
                    break
                except Exception as exc:
                    last_err = exc
            if not downloaded:
                raise RuntimeError(f"内核下载失败：{last_err}")

            if progress_cb:
                progress_cb(88, "正在解压并校验内核文件...")
            staging = RUNTIMES_DIR / f"_staging_{k}"
            shutil.rmtree(staging, ignore_errors=True)
            staging.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(tmp_zip, "r") as zf:
                zf.extractall(staging)
            (staging / "VERSION.txt").write_text(ver, encoding="utf-8")

            shutil.rmtree(target_dir, ignore_errors=True)
            staging.rename(target_dir)
            updated = detect_kernel(k)
            if not updated.installed:
                raise RuntimeError("解压完成但未找到可执行文件")
            if progress_cb:
                progress_cb(100, f"✓ {updated.name} {updated.version} 下载并部署成功")
            return updated
        finally:
            tmp_zip.unlink(missing_ok=True)

    raise ValueError(f"不支持的内核类型: {kind}")
