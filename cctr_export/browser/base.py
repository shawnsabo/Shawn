"""抽象 WebDriver 基类 — 统一所有浏览器接口"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.safari.options import Options as SafariOptions


class BrowserType:
    CHROME = "chrome"
    EDGE = "edge"
    SAFARI = "safari"
    NONE = "none"


class BaseBrowser(ABC):
    """浏览器抽象基类"""

    name: str = "base"
    browser_type: str = BrowserType.NONE

    @abstractmethod
    def get_version(self) -> Optional[str]:
        """检测浏览器版本，返回 None 表示未安装"""
        raise NotImplementedError

    @abstractmethod
    def download_driver(self, version: str) -> Path:
        """下载匹配版本的 WebDriver"""
        raise NotImplementedError

    @abstractmethod
    def create_driver(self, driver_path: Optional[Path] = None, headless: bool = True) -> webdriver:
        """创建 WebDriver 实例"""
        raise NotImplementedError

    def get_options(self) -> ChromeOptions | EdgeOptions | SafariOptions:
        """返回标准化选项（被子类覆盖）"""
        raise NotImplementedError

    def _base_options(self, opts) -> None:
        """通用 headless 配置"""
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--window-size=1920,1080")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--log-level=3")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        if hasattr(opts, "add_experimental_option"):
            opts.add_experimental_option("excludeSwitches", ["enable-automation"])

    def _anti_detect(self, driver) -> None:
        """反自动化检测"""
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        })
