"""Chrome 浏览器实现"""
from pathlib import Path
from typing import Optional
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options as ChromeOptions
from .base import BaseBrowser, BrowserType
from .chromedriver import get_chrome_version, download_chromedriver


class ChromeBrowser(BaseBrowser):
    name = "Chrome"
    browser_type = BrowserType.CHROME

    def get_version(self) -> Optional[str]:
        return get_chrome_version()

    def download_driver(self, version: str) -> Path:
        return download_chromedriver(version)

    def get_options(self) -> ChromeOptions:
        opts = ChromeOptions()
        opts.add_argument("--headless=new")
        opts.add_argument("--disable-extensions")
        opts.add_argument("--disable-popup-blocking")
        opts.add_argument("--disable-translate")
        self._base_options(opts)
        return opts

    def create_driver(self, driver_path: Optional[Path] = None, headless: bool = True) -> webdriver.Chrome:
        if driver_path is None:
            version = self.get_version()
            if not version:
                raise RuntimeError(
                    "无法检测 Chrome 版本。\n"
                    "请确保已安装 Google Chrome：\n"
                    "https://google.com/chrome"
                )
            driver_path = self.download_driver(version)
            print(f"[Driver] Using chromedriver {version}: {driver_path}")

        opts = self.get_options()
        if not headless:
            opts.remove_argument("--headless=new")

        service = Service(executable_path=str(driver_path))
        driver = webdriver.Chrome(service=service, options=opts)
        self._anti_detect(driver)
        return driver
