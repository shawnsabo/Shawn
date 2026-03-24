"""Edge WebDriver 管理"""
from __future__ import annotations
import os
import re
import ssl
import sys
import zipfile
import urllib.request
from pathlib import Path
import subprocess
from selenium import webdriver
from selenium.webdriver.edge.service import Service
from selenium.webdriver.edge.options import Options


_DRIVER_DIR = Path.home() / ".cctr_export" / "driver"
_DRIVER_DIR.mkdir(parents=True, exist_ok=True)


def _search_msedge_exe() -> str | None:
    """在常见位置搜索 msedge.exe，返回版本字符串或 None"""
    candidates = [
        # x86 Edge (最常见)
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        # x64 Edge
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        # 用户本地安装
        os.path.expanduser(r"~\AppData\Local\Microsoft\Edge\Application\msedge.exe"),
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                result = subprocess.run(
                    [p, "--version"],
                    capture_output=True, text=True,
                    encoding='utf-8', errors='replace'
                )
                match = re.search(r"(\d+\.\d+\.\d+\.\d+)", result.stdout)
                if match:
                    return match.group(1)
            except Exception:
                pass
    return None


def get_edge_version() -> str:
    """获取本地 Edge 浏览器版本，优先 registry 后备文件搜索"""
    # 优先从 registry 读（最可靠）
    for root in [r"HKCU", r"HKLM"]:
        for subkey in [
            r"SOFTWARE\Microsoft\Edge\BLBeacon",
            r"SOFTWARE\WOW6432Node\Microsoft\Edge\BLBeacon",
        ]:
            cmd = [r"reg", "query", f"{root}\\{subkey}", "/v", "version"]
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True,
                    encoding='utf-8', errors='replace'
                )
                match = re.search(r"(\d+\.\d+\.\d+\.\d+)", result.stdout)
                if match:
                    return match.group(1)
            except Exception:
                pass

    # 最后后备：直接搜索 msedge.exe
    version = _search_msedge_exe()
    if version:
        return version

    raise RuntimeError(
        "无法检测 Edge 版本。\n"
        "请确保已安装 Microsoft Edge：\n"
        "https://microsoft.com/edge"
    )


def download_edgedriver(version: str) -> Path:
    """下载匹配版本的 msedgedriver（禁用 SSL 验证）"""
    driver_exe = "msedgedriver.exe" if sys.platform == "win32" else "msedgedriver"
    driver_path = _DRIVER_DIR / f"msedgedriver_{version}" / driver_exe
    if driver_path.exists():
        return driver_path

    target_dir = _DRIVER_DIR / f"msedgedriver_{version}"
    target_dir.mkdir(parents=True, exist_ok=True)
    zip_path = target_dir / "driver.zip"

    # SSL context（部分环境需要禁用证书验证）
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    urls = [
        # 优先：msedgewebdriverstorage（微软官方）
        f"https://msedgewebdriverstorage.blob.core.windows.net/edgewebdriver/{version}/edgedriver_{_platform_tag()}.zip",
        # 备用：azureedge（旧版 URL）
        f"https://msedgedriver.azureedge.net/{version}/edgedriver_{_platform_tag()}.zip",
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


def _platform_tag() -> str:
    if sys.platform == "win32":
        return "win64"
    elif sys.platform == "darwin":
        return "mac64"
    return "linux64"


def create_driver(driver_path: Path | None = None) -> webdriver.Edge:
    """创建 Edge WebDriver 实例"""
    if driver_path is None:
        version = get_edge_version()
        driver_path = download_edgedriver(version)
        print(f"[Driver] Using msedgedriver {version}: {driver_path}")

    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--log-level=3")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])

    service = Service(executable_path=str(driver_path))
    driver = webdriver.Edge(service=service, options=opts)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    return driver


class DriverPool:
    """浏览器实例池"""
    def __init__(self, max_size: int = 2):
        self._pool: list[webdriver.Edge] = []
        self._max = max_size

    def acquire(self) -> webdriver.Edge:
        if self._pool:
            return self._pool.pop()
        return create_driver()

    def release(self, driver: webdriver.Edge):
        if len(self._pool) < self._max:
            self._pool.append(driver)
        else:
            driver.quit()

    def close_all(self):
        for d in self._pool:
            try:
                d.quit()
            except Exception:
                pass
        self._pool.clear()
