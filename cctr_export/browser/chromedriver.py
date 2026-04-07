"""ChromeDriver 下载管理"""
from __future__ import annotations
import os
import re
import ssl
import sys
import zipfile
import urllib.request
import subprocess
from pathlib import Path

_DRIVER_DIR = Path.home() / ".cctr_export" / "driver"
_DRIVER_DIR.mkdir(parents=True, exist_ok=True)


def get_chrome_version() -> str | None:
    """获取本地 Chrome 版本，优先 registry 后备命令行"""
    # Windows: HKCU/HKLM registry
    for root in [r"HKCU", r"HKLM"]:
        for subkey in [
            r"SOFTWARE\Google\Chrome\BLBeacon",
            r"SOFTWARE\WOW6432Node\Google\Chrome\BLBeacon",
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

    # 搜索 chrome.exe
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
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


def _get_cft_version(chrome_version: str) -> str | None:
    """从 Chrome for Testing 官方 API 获取匹配的大版本号"""
    import json
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        url = "https://googlechromelabs.github.io/chrome-for-testing/known-good-versions-with-downloads.json"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, context=ctx, timeout=20) as r:
            data = json.loads(r.read())

        # Chrome 版本格式: 146.0.7680.178 → 取前三个点分字段匹配
        chrome_prefix = ".".join(chrome_version.split(".")[:3])  # "146.0.7680"

        for d in reversed(data["versions"]):
            if d["version"].startswith(chrome_prefix):
                dl = d.get("downloads", {}).get("chromedriver", [])
                if dl:
                    return d["version"]
    except Exception:
        pass
    return None


def download_chromedriver(version: str) -> Path:
    """从 Chrome for Testing 官方地址下载匹配版本"""
    driver_exe = "chromedriver.exe" if sys.platform == "win32" else "chromedriver"
    driver_path = _DRIVER_DIR / f"chromedriver_{version}" / driver_exe
    if driver_path.exists():
        return driver_path

    target_dir = _DRIVER_DIR / f"chromedriver_{version}"
    target_dir.mkdir(parents=True, exist_ok=True)
    zip_path = target_dir / "driver.zip"

    platform = "win64" if sys.platform == "win32" else ("mac-arm64" if sys.platform == "darwin" and os.uname().machine == "arm64" else "mac64" if sys.platform == "darwin" else "linux64")

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    # 通过 Chrome for Testing API 找精确匹配版本
    cft_version = _get_cft_version(version)
    if cft_version:
        url = f"https://storage.googleapis.com/chrome-for-testing-public/{cft_version}/{platform}/chromedriver-{platform}.zip"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, context=ctx, timeout=120) as resp:
                data = resp.read()
            with open(zip_path, 'wb') as f:
                f.write(data)
            with zipfile.ZipFile(str(zip_path), "r") as z:
                z.extractall(str(target_dir))
            if zip_path.exists():
                zip_path.unlink()

            # Chrome for Testing zip 包含 chromedriver-{platform}/ 子目录
            for root, dirs, files in os.walk(str(target_dir)):
                for fname in files:
                    if fname == driver_exe or fname == "chromedriver":
                        actual = Path(root) / fname
                        # 移动到目标位置
                        target_exe = target_dir / driver_exe
                        if actual != target_exe:
                            import shutil
                            shutil.copy2(str(actual), str(target_exe))
                        print(f"[Driver] Downloaded chromedriver {cft_version} for Chrome {version}")
                        return target_exe
            if driver_path.exists():
                return driver_path
        except Exception as e:
            if zip_path.exists():
                try:
                    zip_path.unlink()
                except Exception:
                    pass
            print(f"[Driver] CFT download failed: {e}, trying chromium.org...")

    # 后备：chromedriver.chromium.org
    urls = [
        f"https://chromedriver.chromium.org/downloads/chromedriver_{'_'.join(version.split('.')[:3])}.zip",
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
            # 搜索exe（子目录情况）
            for root, dirs, files in os.walk(str(target_dir)):
                for fname in files:
                    if fname == driver_exe or fname == "chromedriver.exe":
                        actual = Path(root) / fname
                        target_exe = target_dir / driver_exe
                        if actual != target_exe:
                            import shutil
                            shutil.copy2(str(actual), str(target_exe))
                        return target_exe
            if driver_path.exists():
                return driver_path
        except Exception:
            if zip_path.exists():
                try:
                    zip_path.unlink()
                except Exception:
                    pass
            continue

    raise RuntimeError(f"下载 chromedriver 失败(版本 {version})，请检查网络或手动下载：\nhttps://google.com/chrome → 帮助 → 关于 Google Chrome")
