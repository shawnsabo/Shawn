"""Edge 浏览器实现"""
from pathlib import Path
from typing import Optional
from selenium import webdriver
from selenium.webdriver.edge.service import Service
from selenium.webdriver.edge.options import Options as EdgeOptions
from .base import BaseBrowser, BrowserType


class EdgeBrowser(BaseBrowser):
    name = "Edge"
    browser_type = BrowserType.EDGE

    def get_version(self) -> Optional[str]:
        import subprocess, re, os
        # registry 优先
        for root in [r"HKCU", r"HKLM"]:
            for subkey in [
                r"SOFTWARE\Microsoft\Edge\BLBeacon",
                r"SOFTWARE\WOW6432Node\Microsoft\Edge\BLBeacon",
            ]:
                try:
                    result = subprocess.run(
                        ["reg", "query", f"{root}\\{subkey}", "/v", "version"],
                        capture_output=True, text=True, encoding='utf-8', errors='replace'
                    )
                    m = re.search(r"(\d+\.\d+\.\d+\.\d+)", result.stdout)
                    if m:
                        return m.group(1)
                except Exception:
                    pass
        # 文件搜索后备
        candidates = [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            os.path.expanduser(r"~\AppData\Local\Microsoft\Edge\Application\msedge.exe"),
        ]
        for p in candidates:
            if os.path.exists(p):
                try:
                    result = subprocess.run(
                        [p, "--version"],
                        capture_output=True, text=True, encoding='utf-8', errors='replace'
                    )
                    m = re.search(r"(\d+\.\d+\.\d+\.\d+)", result.stdout)
                    if m:
                        return m.group(1)
                except Exception:
                    pass
        return None

    def download_driver(self, version: str) -> Path:
        import ssl, sys, zipfile, urllib.request
        from pathlib import Path

        _DRIVER_DIR = Path.home() / ".cctr_export" / "driver"
        _DRIVER_DIR.mkdir(parents=True, exist_ok=True)

        driver_exe = "msedgedriver.exe" if sys.platform == "win32" else "msedgedriver"
        driver_path = _DRIVER_DIR / f"msedgedriver_{version}" / driver_exe
        if driver_path.exists():
            return driver_path

        target_dir = _DRIVER_DIR / f"msedgedriver_{version}"
        target_dir.mkdir(parents=True, exist_ok=True)
        zip_path = target_dir / "driver.zip"

        platform = "win64" if sys.platform == "win32" else ("mac64" if sys.platform == "darwin" else "linux64")

        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        urls = [
            f"https://msedgewebdriverstorage.blob.core.windows.net/edgewebdriver/{version}/edgedriver_{platform}.zip",
            f"https://msedgedriver.azureedge.net/{version}/edgedriver_{platform}.zip",
        ]

        for url in urls:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, context=ctx, timeout=60) as resp:
                    data = resp.read()
                with open(zip_path, 'wb') as f:
                    f.write(data)
                with zipfile.ZipFile(str(zip_path), "r") as z:
                    z.extractall(str(target_dir))
                if zip_path.exists():
                    zip_path.unlink()
                if driver_path.exists():
                    return driver_path
            except Exception:
                if zip_path.exists():
                    try:
                        zip_path.unlink()
                    except Exception:
                        pass
                continue

        raise RuntimeError(f"下载 msedgedriver 失败(版本 {version})，请检查网络")

    def get_options(self) -> EdgeOptions:
        opts = EdgeOptions()
        opts.add_argument("--headless=new")
        opts.add_argument("--disable-extensions")
        opts.add_argument("--disable-popup-blocking")
        self._base_options(opts)
        return opts

    def create_driver(self, driver_path: Optional[Path] = None, headless: bool = True) -> webdriver.Edge:
        if driver_path is None:
            version = self.get_version()
            if not version:
                raise RuntimeError(
                    "无法检测 Edge 版本。\n"
                    "请确保已安装 Microsoft Edge：\n"
                    "https://microsoft.com/edge"
                )
            driver_path = self.download_driver(version)
            print(f"[Driver] Using msedgedriver {version}: {driver_path}")

        opts = self.get_options()
        if not headless:
            opts.remove_argument("--headless=new")

        service = Service(executable_path=str(driver_path))
        driver = webdriver.Edge(service=service, options=opts)
        self._anti_detect(driver)
        return driver


# ── 模块级兼容函数（供 core/driver.py 导入） ──────────────────────────

def get_edge_version() -> str:
    """模块级版本检测（兼容旧 API）"""
    return EdgeBrowser().get_version() or ""


def download_edgedriver(version: str) -> Path:
    """模块级下载（兼容旧 API）"""
    return EdgeBrowser().download_driver(version)
