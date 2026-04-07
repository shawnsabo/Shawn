"""Edge WebDriver 管理（兼容层 — 委托给 browser/ 包）"""
from __future__ import annotations
from pathlib import Path
from selenium import webdriver

# 委托给 browser/ 包
from ..browser.factory import create_driver as _create_driver, DriverPool as _DriverPool
from ..browser.edge import EdgeBrowser, get_edge_version as _get_edge_version
from ..browser.chromedriver import download_chromedriver as _download_edgedriver


def get_edge_version() -> str:
    """获取本地 Edge 浏览器版本（兼容旧 API）"""
    return _get_edge_version()


def download_edgedriver(version: str) -> Path:
    """下载匹配版本的 msedgedriver（兼容旧 API）"""
    return _download_edgedriver(version)


def create_driver(driver_path: Path | None = None) -> webdriver.Edge:
    """创建 Edge WebDriver 实例（强制 Edge，兼容旧 API）"""
    return _create_driver(browser_type="edge", driver_path=driver_path, headless=True)


class DriverPool:
    """浏览器实例池（Edge专用，兼容旧 API）"""
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
