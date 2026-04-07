"""浏览器工厂 — 自动检测 + 优先级创建"""
from __future__ import annotations
from typing import Optional
from .base import BaseBrowser, BrowserType
from .chrome import ChromeBrowser
from .edge import EdgeBrowser
from .safari import SafariBrowser

# 优先级：Chrome > Edge > Safari
_BROWSERS: list[BaseBrowser] = [
    ChromeBrowser(),
    EdgeBrowser(),
    SafariBrowser(),
]


def detect_browser() -> tuple[BaseBrowser, str]:
    """
    自动检测可用浏览器。
    返回 (browser_instance, version_string)。
    若均不可用，抛出 RuntimeError。
    """
    for browser in _BROWSERS:
        version = browser.get_version()
        if version:
            return browser, version
    raise RuntimeError(
        "未检测到任何支持的浏览器（Chrome/Edge/Safari）。\n"
        "请安装 Google Chrome 或 Microsoft Edge 后重试。"
    )


def create_driver(
    browser_type: Optional[str] = None,
    driver_path=None,
    headless: bool = True,
):
    """
    创建 WebDriver 实例。

    Args:
        browser_type: 指定浏览器 ("chrome"/"edge"/"safari")，None 则自动检测
        driver_path:   WebDriver 可执行文件路径
        headless:      是否无头模式

    Returns:
        selenium WebDriver 实例（Chrome/Edge/Safari）
    """
    if browser_type:
        browser_map = {
            BrowserType.CHROME: ChromeBrowser(),
            BrowserType.EDGE: EdgeBrowser(),
            BrowserType.SAFARI: SafariBrowser(),
        }
        browser = browser_map.get(browser_type.lower())
        if not browser:
            raise ValueError(f"未知浏览器类型: {browser_type}，可用值: chrome, edge, safari")
        return browser.create_driver(driver_path, headless)

    # 自动检测
    detected, version = detect_browser()
    print(f"[Browser] 自动选择 {detected.name} {version}")
    return detected.create_driver(driver_path, headless)


class DriverPool:
    """浏览器实例池 — 支持多浏览器混用"""

    def __init__(self, max_size: int = 2, browser_type: Optional[str] = None):
        self._pool: list = []
        self._max = max_size
        self._browser_type = browser_type  # None = auto
        self._browser_instance: Optional[BaseBrowser] = None

    def _ensure_browser(self):
        if self._browser_instance is None:
            if self._browser_type:
                browser_map = {
                    BrowserType.CHROME: ChromeBrowser(),
                    BrowserType.EDGE: EdgeBrowser(),
                    BrowserType.SAFARI: SafariBrowser(),
                }
                self._browser_instance = browser_map.get(self._browser_type.lower())
                if not self._browser_instance:
                    raise ValueError(f"未知浏览器: {self._browser_type}")
            else:
                self._browser_instance, _ = detect_browser()
                print(f"[DriverPool] 自动使用 {self._browser_instance.name}")

    def acquire(self):
        self._ensure_browser()
        if self._pool:
            return self._pool.pop()
        return self._browser_instance.create_driver()

    def release(self, driver):
        if len(self._pool) < self._max:
            self._pool.append(driver)
        else:
            try:
                driver.quit()
            except Exception:
                pass

    def close_all(self):
        for d in self._pool:
            try:
                d.quit()
            except Exception:
                pass
        self._pool.clear()
