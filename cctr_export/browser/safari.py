"""Safari 浏览器实现（仅 macOS）"""
from pathlib import Path
from typing import Optional
import sys
from selenium import webdriver
from selenium.webdriver.safari.service import Service as SafariService
from selenium.webdriver.safari.options import Options as SafariOptions
from .base import BaseBrowser, BrowserType


class SafariBrowser(BaseBrowser):
    name = "Safari"
    browser_type = BrowserType.SAFARI

    def get_version(self) -> Optional[str]:
        import subprocess
        if sys.platform != "darwin":
            return None
        try:
            result = subprocess.run(
                ["/usr/bin/pluginkit", "--list", "-m", "com.apple.Safari.WebInspectorExtension.plist"],
                capture_output=True, text=True
            )
            # Safari 版本
            result2 = subprocess.run(
                ["defaults", "read", "/Applications/Safari.app/Contents/Info.plist", "CFBundleShortVersionString"],
                capture_output=True, text=True
            )
            version = result2.stdout.strip()
            if version:
                return version
        except Exception:
            pass
        return None

    def download_driver(self, version: str) -> Path:
        # SafariDriver 随 macOS 系统自带，无需下载
        if sys.platform != "darwin":
            raise RuntimeError("SafariDriver 仅在 macOS 上可用")
        return Path("/usr/bin/safaridriver")

    def get_options(self) -> SafariOptions:
        opts = SafariOptions()
        opts.add_argument("--headless")
        opts.add_argument("--private")
        return opts

    def create_driver(self, driver_path: Optional[Path] = None, headless: bool = True) -> webdriver.Safari:
        if sys.platform != "darwin":
            raise RuntimeError("Safari WebDriver 仅在 macOS 上可用")
        service = SafariService(executable_path=str(driver_path or "/usr/bin/safaridriver"))
        opts = self.get_options()
        driver = webdriver.Safari(service=service, options=opts)
        self._anti_detect(driver)
        return driver
